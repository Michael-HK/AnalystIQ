from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Tuple,
    Optional,
    Sequence,
    Union,
    AsyncIterator,
)
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
    LLMMetadata,
    MessageRole,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
import google.api_core
from llama_index.core.bridge.pydantic import Field, PrivateAttr
from llama_index.core.callbacks import CallbackManager
from llama_index.core.llms.callbacks import llm_chat_callback, llm_completion_callback
from llama_index.core.types import BaseOutputParser, PydanticProgramMode
from llama_index.core.llms.function_calling import FunctionCallingLLM, ToolSelection
from llama_index.core.utilities.gemini_utils import merge_neighboring_same_role_messages
from llama_index.llms.vertex.gemini_utils import create_gemini_client, is_gemini_model
from llama_index.llms.vertex.utils import (
    CHAT_MODELS,
    CODE_CHAT_MODELS,
    CODE_MODELS,
    TEXT_MODELS,
    _parse_chat_history,
    _parse_examples,
    _parse_message,
    acompletion_with_retry,
    completion_with_retry,
    init_vertexai,
    force_single_tool_call,
)
from vertexai.generative_models._generative_models import (
    SafetySettingsType,
    Content,
    Part,
    GenerationConfig,
)
import asyncio
import logging

if TYPE_CHECKING:
    from llama_index.core.tools.types import BaseTool

logger = logging.getLogger(__name__)


class VertexAI(FunctionCallingLLM):
    """
    Vertext LLM.

    Examples:
        `pip install llama-index-llms-vertex`

        ```python
        from llama_index.llms.vertex import Vertex

        # Set up necessary variables
        credentials = {
            "project_id": "INSERT_PROJECT_ID",
            "api_key": "INSERT_API_KEY",
        }

        # Create an instance of the Vertex class
        llm = Vertex(
            model="text-bison",
            project=credentials["project_id"],
            credentials=credentials,
            context_window=4096,
        )

        # Access the complete method from the instance
        response = llm.complete("Hello world!")
        print(str(response))
        ```

    """

    model: str = Field(description="The vertex model to use.")
    temperature: float = Field(description="The temperature to use for sampling.")
    context_window: int = Field(
        default=4096, description="The context window to use for sampling."
    )
    max_tokens: int = Field(description="The maximum number of tokens to generate.")
    examples: Optional[Sequence[ChatMessage]] = Field(
        description="Example messages for the chat model."
    )
    max_retries: int = Field(default=10, description="The maximum number of retries.")
    additional_kwargs: Dict[str, Any] = Field(
        default_factory=dict, description="Additional kwargs for the Vertex."
    )
    iscode: bool = Field(
        default=False, description="Flag to determine if current model is a Code Model"
    )
    _is_gemini: bool = PrivateAttr()
    _is_chat_model: bool = PrivateAttr()
    _client: Any = PrivateAttr()
    _chat_client: Any = PrivateAttr()
    _safety_settings: Dict[str, Any] = PrivateAttr()


    def __init__(
        self,
        model: str = "text-bison",
        project: Optional[str] = None,
        location: Optional[str] = None,
        credentials: Optional[Any] = None,
        examples: Optional[Sequence[ChatMessage]] = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
        context_window: int = 4096,
        max_retries: int = 10,
        iscode: bool = False,
        safety_settings: Optional[SafetySettingsType] = None,
        additional_kwargs: Optional[Dict[str, Any]] = None,
        callback_manager: Optional[CallbackManager] = None,
        system_prompt: Optional[str] = None,
        messages_to_prompt: Optional[Callable[[Sequence[ChatMessage]], str]] = None,
        completion_to_prompt: Optional[Callable[[str], str]] = None,
        pydantic_program_mode: PydanticProgramMode = PydanticProgramMode.DEFAULT,
        output_parser: Optional[BaseOutputParser] = None,
    ) -> None:
        init_vertexai(project=project, location=location, credentials=credentials)

        safety_settings = safety_settings or {}
        additional_kwargs = additional_kwargs or {}
        callback_manager = callback_manager or CallbackManager([])

        super().__init__(
            temperature=temperature,
            context_window=context_window,
            max_tokens=max_tokens,
            additional_kwargs=additional_kwargs,
            max_retries=max_retries,
            model=model,
            examples=examples,
            iscode=iscode,
            callback_manager=callback_manager,
            system_prompt=system_prompt,
            messages_to_prompt=messages_to_prompt,
            completion_to_prompt=completion_to_prompt,
            pydantic_program_mode=pydantic_program_mode,
            output_parser=output_parser,
        )

        self._safety_settings = safety_settings
        self._is_gemini = False
        self._is_chat_model = False


        if model in CHAT_MODELS:
            from vertexai.language_models import ChatModel

            self._chat_client = ChatModel.from_pretrained(model)
            self._is_chat_model = True
        elif model in CODE_CHAT_MODELS:
            from vertexai.language_models import CodeChatModel

            self._chat_client = CodeChatModel.from_pretrained(model)
            iscode = True
            self._is_chat_model = True
        elif model in CODE_MODELS:
            from vertexai.language_models import CodeGenerationModel

            self._client = CodeGenerationModel.from_pretrained(model)
            iscode = True
        elif model in TEXT_MODELS:
            from vertexai.language_models import TextGenerationModel

            self._client = TextGenerationModel.from_pretrained(model)
        elif is_gemini_model(model):
            self._client = create_gemini_client(model, self._safety_settings)
            self._chat_client = self._client
            self._is_gemini = True
            self._is_chat_model = True
        else:
            raise (ValueError(f"Model {model} not found, please verify the model name"))

    @classmethod
    def class_name(cls) -> str:
        return "Vertex"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            num_output=self.max_tokens,
            context_window=self.context_window,
            is_chat_model=self._is_chat_model,
            is_function_calling_model=self._is_gemini,
            model_name=self.model,
            system_role=(
                MessageRole.USER if self._is_gemini else MessageRole.SYSTEM
            ),  # Gemini does not support the default: MessageRole.SYSTEM
        )

    @property
    def _model_kwargs(self) -> Dict[str, Any]:
        base_kwargs = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        return {
            **base_kwargs,
            **self.additional_kwargs,
        }

    def _get_all_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            **self._model_kwargs,
            **kwargs,
        }

    def _get_content_and_tool_calls(self, response: Any) -> Tuple[str, List]:
        tool_calls = []
        if response.candidates[0].function_calls:
            for tool_call in response.candidates[0].function_calls:
                tool_calls.append(tool_call)
        try:
            content = response.text
        except Exception:
            content = ""
        return content, tool_calls
    


    def _convert_llama_role_to_gemini(self, llama_role: MessageRole) -> str:
        if llama_role == MessageRole.USER:
            return "user"
        elif llama_role == MessageRole.ASSISTANT:
            return "model"
        elif llama_role == MessageRole.SYSTEM:
            # Gemini API typically expects system prompts to be part of the 'user' content
            # or handled specifically if the client supports a system_instruction parameter.
            # Given LlamaIndex's merge_neighboring_same_role_messages, a standalone system message
            # passed here might be intended as the first user turn's system context.
            return "user"
        # Add other roles like TOOL, FUNCTION if needed for completeness,
        # but current error is text-based.
        else:
            logger.warning(
                f"Unhandled LlamaIndex MessageRole '{llama_role}' in role conversion. Defaulting to 'user'."
            )
            return "user"

    def _sanitize_parsed_message_to_content(
        self, parsed_item: Any, original_llama_role: MessageRole
    ) -> Content:
        """
        Ensures the item (typically output of _parse_message) is a valid Vertex AI Content object.
        Addresses the case where _parse_message might incorrectly return a list of part-like dicts.
        """
        gemini_role = self._convert_llama_role_to_gemini(original_llama_role)

        if isinstance(parsed_item, Content):
            # If LlamaIndex's _parse_message correctly returned a Content object.
            # We could optionally enforce the role: parsed_item.role = gemini_role
            # However, _parse_message should already set the role on the Content object.
            return parsed_item

        parts = []
        if isinstance(parsed_item, list):
            # This is the core fix for the TypeError: Unexpected item type: [text: "..."]
            # It assumes parsed_item is like [{'text': '...'}, {'text': '...'}]
            for element in parsed_item:
                if isinstance(element, dict) and "text" in element:
                    parts.append(Part.from_text(element["text"]))
                elif isinstance(element, str): # Handle if the list directly contains strings
                    parts.append(Part.from_text(element))
                elif isinstance(element, Part): # Handle if the list already contains Part objects
                    parts.append(element)
                else:
                    logger.warning(
                        f"Sanitizer: Skipped unexpected element of type {type(element)} in list: {element}"
                    )
        elif isinstance(parsed_item, str):
            # If _parse_message returned a raw string (shouldn't happen for Gemini if is_gemini=True)
            parts.append(Part.from_text(parsed_item))
        elif isinstance(parsed_item, dict) and "text" in parsed_item:
            # If _parse_message returned a single part-like dict
            parts.append(Part.from_text(parsed_item["text"]))
        elif isinstance(parsed_item, Part):
             # If _parse_message returned a single Part object
            parts.append(parsed_item)
        else:
            logger.error(
                f"Sanitizer: Unhandled type from LlamaIndex's parsing function: {type(parsed_item)}. "
                f"Data: {str(parsed_item)[:200]}... Attempting to convert to string."
            )
            # Fallback: try to convert the whole thing to a string part.
            parts.append(Part.from_text(str(parsed_item)))

        if not parts:
            logger.warning(
                f"Sanitizer: No parts were extracted for role '{gemini_role}' from item: {str(parsed_item)[:200]}... "
                "Creating an empty text part to avoid API errors."
            )
            parts.append(Part.from_text(""))  # Gemini Content needs at least one part.
        
        return Content(parts=parts, role=gemini_role)

    def _create_retry_decorator(max_retries: int) -> Callable[[Any], Any]:
        min_seconds = 4
        max_seconds = 10

        return retry(
            reraise=True,
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=min_seconds, max=max_seconds),
            retry=(
                retry_if_exception_type(google.api_core.exceptions.ServiceUnavailable)
                | retry_if_exception_type(google.api_core.exceptions.ResourceExhausted)
                | retry_if_exception_type(google.api_core.exceptions.Aborted)
                | retry_if_exception_type(google.api_core.exceptions.DeadlineExceeded)
                | retry_if_exception_type(google.api_core.exceptions.InternalServerError)
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )

    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        merged_messages = (
            merge_neighboring_same_role_messages(messages)
            if self._is_gemini
            else messages
        )
        question = _parse_message(merged_messages[-1], self._is_gemini)
        chat_history = _parse_chat_history(merged_messages[:-1], self._is_gemini)

        chat_params = {**chat_history}

        kwargs = kwargs if kwargs else {}

        params = {**self._model_kwargs, **kwargs}

        if self.iscode and "candidate_count" in params:
            raise (ValueError("candidate_count is not supported by the codey model's"))
        if self.examples and "examples" not in params:
            chat_params["examples"] = _parse_examples(self.examples)
        elif "examples" in params:
            raise (
                ValueError(
                    "examples are not supported in chat generation pass them as a constructor parameter"
                )
            )

        generation = completion_with_retry(
            client=self._chat_client,
            prompt=question,
            chat=True,
            stream=False,
            is_gemini=self._is_gemini,
            params=chat_params,
            max_retries=self.max_retries,
            **params,
        )

        content, tool_calls = self._get_content_and_tool_calls(generation)



        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                additional_kwargs={"tool_calls": tool_calls},
            ),
            raw=generation.__dict__,
        )

    @llm_completion_callback()
    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        kwargs = kwargs if kwargs else {}
        params = {**self._model_kwargs, **kwargs}
        if self.iscode and "candidate_count" in params:
            raise (ValueError("candidate_count is not supported by the codey model's"))

        completion = completion_with_retry(
            self._client,
            prompt,
            max_retries=self.max_retries,
            is_gemini=self._is_gemini,
            **params,
        )

        return CompletionResponse(text=completion.text, raw=completion.__dict__)

    @llm_chat_callback()
    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseGen:
        merged_messages = (
            merge_neighboring_same_role_messages(messages)
            if self._is_gemini
            else messages
        )
        question = _parse_message(merged_messages[-1], self._is_gemini)
        chat_history = _parse_chat_history(merged_messages[:-1], self._is_gemini)
        chat_params = {**chat_history}
        kwargs = kwargs if kwargs else {}
        params = {**self._model_kwargs, **kwargs}
        if self.iscode and "candidate_count" in params:
            raise (ValueError("candidate_count is not supported by the codey model's"))
        if self.examples and "examples" not in params:
            chat_params["examples"] = _parse_examples(self.examples)
        elif "examples" in params:
            raise (
                ValueError(
                    "examples are not supported in chat generation pass them as a constructor parameter"
                )
            )

        response = completion_with_retry(
            client=self._chat_client,
            prompt=question,
            chat=True,
            stream=True,
            is_gemini=self._is_gemini,
            params=chat_params,
            max_retries=self.max_retries,
            **params,
        )

        def gen() -> ChatResponseGen:
            content = ""
            role = MessageRole.ASSISTANT
            for r in response:
                content_delta = r.text
                content += content_delta
                yield ChatResponse(
                    message=ChatMessage(role=role, content=content),
                    delta=content_delta,
                    raw=r.__dict__,
                )
          

        return gen()
    
    max_retries = 10
    retry_decorator = _create_retry_decorator(max_retries=max_retries)

    @retry_decorator
    async def _astream_gemini_responses(
        self,
        messages_for_gemini: List[Content],
        generation_params: Dict[str, Any],
    ) -> AsyncIterator[Any]: # Yields GenerateContentResponse from Vertex SDK
        """Calls Gemini's generate_content_async with stream=True and yields responses."""
        # Ensure GenerationConfig is available (already imported)

        # Prepare GenerationConfig, filtering for known and non-None parameters
        # Explicitly list known GenerationConfig fields to avoid passing unsupported params.
        known_config_keys = [
            "temperature", "max_output_tokens", "top_p", "top_k", 
            "candidate_count", "stop_sequences"
        ]
        config_kwargs = {
            k: generation_params[k]
            for k in known_config_keys
            if k in generation_params and generation_params[k] is not None
        }

        # Handle case where iscode might restrict candidate_count for streaming
        if self.iscode and "candidate_count" in config_kwargs:
            if config_kwargs["candidate_count"] != 1:
                logger.warning(
                    "candidate_count may not be fully supported or is restricted for code models in streaming."
                )

        generation_config_obj = GenerationConfig(**config_kwargs)

        try:
            stream_coroutine = self._chat_client.generate_content_async(
                contents=messages_for_gemini,
                generation_config=generation_config_obj,
                safety_settings=self._safety_settings,
                stream=True,
            )
            async_iterator_response = await stream_coroutine 
            async for resp_chunk in async_iterator_response:
                yield resp_chunk
        except Exception as e:
            logger.error(f"Error during Gemini async streaming: {str(e)}")
            raise

    @llm_chat_callback()
    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseAsyncGen:
        if not self._is_gemini:
            logger.warning(
                "Attempting to use Gemini-optimized astream_chat for a non-Gemini model. "
                "This path is not fully implemented for non-Gemini models and may fail or perform unexpectedly."
            )
            raise NotImplementedError(
                "The current astream_chat implementation is optimized for Gemini models. "
                "Async streaming for other model types is not supported via this path."
            )

        processed_messages_for_gemini: List[Content] = []
        
        # Step 1: Merge LlamaIndex ChatMessage objects.
        # merge_neighboring_same_role_messages handles system prompts correctly if they are part of the sequence.
        # The role conversion to Gemini's 'user' for a LlamaIndex SYSTEM role happens inside _parse_message.
        merged_llama_messages = merge_neighboring_same_role_messages(messages)

        # Step 2: Convert each LlamaIndex ChatMessage to a sanitized Gemini Content object.
        for llama_msg in merged_llama_messages:
            # _parse_message converts ChatMessage to a potential Gemini Content structure (or list of dicts).
            # It also handles role conversion (e.g., LlamaIndex SYSTEM -> Gemini 'user').
            raw_gemini_parts = _parse_message(llama_msg, self._is_gemini)
            
            # _sanitize_parsed_message_to_content ensures the result is a valid Vertex AI Content object.
            # It uses the original LlamaIndex role for context if needed by the sanitizer,
            # though the role on the Content object itself is set by _parse_message via _convert_llama_role_to_gemini.
            gemini_content_obj = self._sanitize_parsed_message_to_content(
                raw_gemini_parts, llama_msg.role
            )
            
            if gemini_content_obj: # Ensure the content object is valid
                processed_messages_for_gemini.append(gemini_content_obj)

        # Handle examples from the constructor
        if self.examples:
            # Examples are typically also ChatMessage sequences
            # For consistency, they should also be merged and then parsed/sanitized
            merged_example_llama_messages = merge_neighboring_same_role_messages(self.examples)
            for example_llama_msg in merged_example_llama_messages:
                raw_example_gemini_parts = _parse_message(example_llama_msg, self._is_gemini)
                example_gemini_content_obj = self._sanitize_parsed_message_to_content(
                    raw_example_gemini_parts, example_llama_msg.role
                )
                if example_gemini_content_obj:
                    # The placement of examples (e.g., before the last user message) can be model-specific.
                    # Appending them here. If a different order is required, this logic would need adjustment.
                    processed_messages_for_gemini.append(example_gemini_content_obj)

        if "examples" in kwargs: # Runtime examples are not supported by this flow
            raise ValueError(
                "Runtime 'examples' are not supported in chat generation for Gemini astream_chat. "
                "Pass examples via the constructor."
            )

        if not processed_messages_for_gemini:
            # This is a final check. If after all processing, the list is empty, it's an error.
            raise ValueError("Cannot send an empty 'contents' list to Gemini. No messages processed.")

        # Prepare generation parameters
        gen_params = {**self._model_kwargs, **kwargs}
        
        if self.iscode and "candidate_count" in gen_params:
            if gen_params.get("candidate_count") is not None and gen_params["candidate_count"] != 1:
                 logger.warning("candidate_count other than 1 might not be supported for streaming with code models.")

        response_iterator = self._astream_gemini_responses(
            messages_for_gemini=processed_messages_for_gemini,
            generation_params=gen_params,
        )

        async def async_gen() -> ChatResponseAsyncGen:
            content = ""
            role = MessageRole.ASSISTANT
            try:
                async for chunk in response_iterator: # chunk is GenerateContentResponse
                    chunk_text = ""
                    # tool_calls_in_chunk = [] # For future tool call streaming

                    if chunk.candidates:
                        candidate = chunk.candidates[0]
                        if candidate.content and candidate.content.parts:
                            for part in candidate.content.parts:
                                if part.text:
                                    chunk_text += part.text
                                # Future: Extract part.function_call if implementing tool streaming
                        
                        # Future: Check candidate.finish_reason and candidate.safety_ratings
                        # E.g., if candidate.finish_reason == "TOOL_CODE":
                        #   parse candidate.function_calls
                        #   yield a ChatResponse reflecting the tool call

                    if chunk_text: # Only yield if there's new text content
                        content += chunk_text
                        yield ChatResponse(
                            message=ChatMessage(
                                role=role, 
                                content=content,
                                additional_kwargs={} # Placeholder for future (e.g., accumulated tool calls)
                            ),
                            delta=chunk_text,
                            raw=chunk.to_dict() if hasattr(chunk, "to_dict") else chunk, 
                        )
                    # elif tool_calls_in_chunk: # Future: yield for tool calls
                    #    pass 

            except Exception as e:
                logger.error(f"Error in async streaming generation: {str(e)}")
                raise
        return async_gen()

    @llm_completion_callback()
    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        kwargs = kwargs if kwargs else {}
        params = {**self._model_kwargs, **kwargs}
        if "candidate_count" in params:
            raise (ValueError("candidate_count is not supported by the streaming"))

        completion = completion_with_retry(
            client=self._client,
            prompt=prompt,
            stream=True,
            is_gemini=self._is_gemini,
            max_retries=self.max_retries,
            **params,
        )

        def gen() -> CompletionResponseGen:
            content = ""
            for r in completion:
                content_delta = r.text
                content += content_delta
                yield CompletionResponse(
                    text=content, delta=content_delta, raw=r.__dict__
                )
      
        return gen()
    

    @llm_chat_callback()
    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        merged_messages = (
            merge_neighboring_same_role_messages(messages)
            if self._is_gemini
            else messages
        )
        question = _parse_message(merged_messages[-1], self._is_gemini)
        chat_history = _parse_chat_history(merged_messages[:-1], self._is_gemini)
        chat_params = {**chat_history}
        kwargs = kwargs if kwargs else {}
        params = {**self._model_kwargs, **kwargs}
        if self.iscode and "candidate_count" in params:
            raise (ValueError("candidate_count is not supported by the codey model's"))
        if self.examples and "examples" not in params:
            chat_params["examples"] = _parse_examples(self.examples)
        elif "examples" in params:
            raise (
                ValueError(
                    "examples are not supported in chat generation pass them as a constructor parameter"
                )
            )  
        generation = await acompletion_with_retry(
            client=self._chat_client,
            prompt=question,
            chat=True,
            is_gemini=self._is_gemini,
            params=chat_params,
            max_retries=self.max_retries,
            **params,
        )
        ##this is due to a bug in vertex AI we have to await twice
        if self.iscode:
            generation = await generation

        content, tool_calls = self._get_content_and_tool_calls(generation)
        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                additional_kwargs={"tool_calls": tool_calls},
            ),
            raw=generation.__dict__,
        )
#    @llm_chat_callback()
#    async def achat(
#        self, messages: Sequence[ChatMessage], **kwargs: Any
#    ) -> ChatResponse:
#        if not self._is_gemini:
            # Fallback to original logic for non-Gemini models
#            merged_messages = messages
#            question = _parse_message(merged_messages[-1], self._is_gemini)
#            chat_history = _parse_chat_history(merged_messages[:-1], self._is_gemini)
#            chat_params = {**chat_history}
#            params = {**self._model_kwargs, **kwargs}
#            generation = await acompletion_with_retry(
#                client=self._chat_client,
#                prompt=question,
#                chat=True,
#                is_gemini=self._is_gemini,
#                params=chat_params,
#                max_retries=self.max_retries,
#                **params,
#            )
            
#        else:
            # Use the more robust message processing logic from astream_chat
#            processed_messages_for_gemini: List[Content] = []
#            merged_llama_messages = merge_neighboring_same_role_messages(messages)

#            for llama_msg in merged_llama_messages:
#                raw_gemini_parts = _parse_message(llama_msg, self._is_gemini)
#                gemini_content_obj = self._sanitize_parsed_message_to_content(
#                    raw_gemini_parts, llama_msg.role
#                )
#                if gemini_content_obj:
#                    processed_messages_for_gemini.append(gemini_content_obj)
            
#            if self.examples:
#                merged_example_llama_messages = merge_neighboring_same_role_messages(self.examples)
#                for example_llama_msg in merged_example_llama_messages:
#                    raw_example_gemini_parts = _parse_message(example_llama_msg, self._is_gemini)
#                    example_gemini_content_obj = self._sanitize_parsed_message_to_content(
#                        raw_example_gemini_parts, example_llama_msg.role
#                    )
#                    if example_gemini_content_obj:
#                        processed_messages_for_gemini.append(example_gemini_content_obj)

#            gen_params = {**self._model_kwargs, **kwargs}
#            known_config_keys = [
#                "temperature", "max_output_tokens", "top_p", "top_k", 
#                "candidate_count", "stop_sequences"
#            ]
#            config_kwargs = {
#                k: gen_params[k]
#                for k in known_config_keys
#                if k in gen_params and gen_params[k] is not None
#            }
#            generation_config_obj = GenerationConfig(**config_kwargs)

            # Make a non-streaming async call
#            generation = await self._chat_client.generate_content_async(
#                contents=processed_messages_for_gemini,
#                generation_config=generation_config_obj,
#                safety_settings=self._safety_settings,
#                stream=False,
#            )

        # Common response processing for both paths
#        content, tool_calls = self._get_content_and_tool_calls(generation)
#        self._track_token_usage_from_messages(messages, content, operation="achat")
#        return ChatResponse(
#            message=ChatMessage(
#                role=MessageRole.ASSISTANT,
#                content=content,
#                additional_kwargs={"tool_calls": tool_calls},
#            ),
#            raw=generation.to_dict() if hasattr(generation, "to_dict") else generation,
#        )

    @llm_completion_callback()
    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        kwargs = kwargs if kwargs else {}
        params = {**self._model_kwargs, **kwargs}
        if self.iscode and "candidate_count" in params:
            raise (ValueError("candidate_count is not supported by the codey model's"))
        completion = await acompletion_with_retry(
            client=self._client,
            prompt=prompt,
            max_retries=self.max_retries,
            is_gemini=self._is_gemini,
            **params,
        )
        
        return CompletionResponse(text=completion.text)


    @llm_completion_callback()
    async def astream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseAsyncGen:
        raise (ValueError("Not Implemented"))

    def _prepare_chat_with_tools(
        self,
        tools: List["BaseTool"],
        user_msg: Optional[Union[str, ChatMessage]] = None,
        chat_history: Optional[List[ChatMessage]] = None,
        verbose: bool = False,
        allow_parallel_tool_calls: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Prepare the arguments needed to let the LLM chat with tools."""
        chat_history = chat_history or []

        if isinstance(user_msg, str):
            user_msg = ChatMessage(role=MessageRole.USER, content=user_msg)
            chat_history.append(user_msg)

        tool_dicts = []
        for tool in tools:
            tool_dicts.append(
                {
                    "name": tool.metadata.name,
                    "description": tool.metadata.description,
                    "parameters": tool.metadata.get_parameters_dict(),
                }
            )

        return {
            "messages": chat_history,
            "tools": tool_dicts or None,
            **kwargs,
        }

    def _validate_chat_with_tools_response(
        self,
        response: ChatResponse,
        tools: List["BaseTool"],
        allow_parallel_tool_calls: bool = False,
        **kwargs: Any,
    ) -> ChatResponse:
        """Validate the response from chat_with_tools."""
        if not allow_parallel_tool_calls:
            force_single_tool_call(response)
        return response

    def get_tool_calls_from_response(
        self,
        response: "ChatResponse",
        error_on_no_tool_call: bool = True,
        **kwargs: Any,
    ) -> List[ToolSelection]:
        """Predict and call the tool."""
        tool_calls = response.message.additional_kwargs.get("tool_calls", [])

        if len(tool_calls) < 1:
            if error_on_no_tool_call:
                raise ValueError(
                    f"Expected at least one tool call, but got {len(tool_calls)} tool calls."
                )
            else:
                return []

        tool_selections = []
        for tool_call in tool_calls:
            response_dict = tool_call.to_dict()
            if "args" not in response_dict or "name" not in response_dict:
                raise ValueError("Invalid tool call.")
            argument_dict = response_dict["args"]

            tool_selections.append(
                ToolSelection(
                    tool_id="None",
                    tool_name=tool_call.name,
                    tool_kwargs=argument_dict,
                )
            )

        return tool_selections
