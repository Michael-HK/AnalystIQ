import os
import asyncio
from dotenv import load_dotenv
from typing import List, Dict
from tavily import AsyncTavilyClient

load_dotenv()

class WebSearchTool:
    """
    A tool for performing web searches using the Tavily API.
    """

    def __init__(self, api_key: str = None):
        """
        Initializes the WebSearchTool.

        Args:
            api_key (str, optional): The Tavily API key. If not provided, it will be
                                     retrieved from the TAVILY_API_KEY environment variable.
        """
        api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "Tavily API key not provided. Please pass it as an argument or set the "
                "TAVILY_API_KEY environment variable."
            )
        self.client = AsyncTavilyClient(api_key=api_key)

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """
        Performs a web search using the Tavily API.

        Args:
            query (str): The search query.
            max_results (int, optional): The maximum number of search results to return. Defaults to 5.

        Returns:
            List[Dict[str, str]]: A list of search results, where each result is a dictionary
                                  containing 'title', 'url', and 'content'.
        """
        try:
            response = await self.client.search(query=query, search_depth="advanced", max_results=max_results)
            results = [
                {
                    "title": res.get("title", ""),
                    "url": res.get("url", ""),
                    "content": res.get("content", "")
                }
                for res in response.get("results", [])
            ]
            return results
        except Exception as e:
            print(f"An error occurred during web search: {e}")
            return []


async def parallel_search(search_tool: WebSearchTool, queries: List[str]) -> List[Dict[str, str]]:
    """
    Performs web searches for a list of queries in parallel.
    """
    all_results = []
    #batch of 3 queries at a time
    for i in range(0, len(queries), 3):
        batch = queries[i:i+3]
        tasks = [search_tool.search(query) for query in batch]
        search_results = await asyncio.gather(*tasks, return_exceptions=True)
        all_results.extend(search_results)
        #wait for 2 second
        await asyncio.sleep(2)
    
    return all_results
