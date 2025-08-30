
import yfinance as yf
from datetime import datetime, timedelta
import trafilatura
import logging
from typing import List, Dict, Any
import asyncio
from llama_index.core.tools.tool_spec.base import BaseToolSpec
from llama_index.core.agent.workflow import ReActAgent
from prompts import FINANCIAL_AGENT_SYSTEM_PROMPT

from llama_index.llms.openrouter import OpenRouter


logger = logging.getLogger(__name__)

class FinancialToolSpec(BaseToolSpec):
    
    """
    A tool for fetching financial data from Yahoo Finance.
    """
    spec_functions = [
        "get_stock_price",
        "get_company_info",
        "get_income_statement",
        "get_balance_sheet",
        "get_cash_flow",
        "get_key_stats",
        "get_stock_news",
        "get_company_name",
    ]
    
    def get_company_name(self, ticker: str) -> str:
        """
        Retrieves the company's long name for a given ticker.
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return info.get("longName", ticker)
        except Exception as e:
            logger.error(f"Error fetching company name for {ticker}: {e}")
            return ticker

    def get_stock_price(self, ticker: str, start_date: str = None, end_date: str = None) -> str:
        """
        Retrieves historical stock prices for a given ticker.
        """
        stock = yf.Ticker(ticker)

        if start_date is None:
            data = stock.history(period="1d")
            if data.empty:
                return f"Could not retrieve the current stock price for {ticker}."
            price = data["Close"].iloc[-1]
            return f"The current stock price of {ticker} is {price}."

        query_end_date = end_date
        if end_date is None:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = start_dt + timedelta(days=1)
                query_end_date = end_dt.strftime("%Y-%m-%d")
            except ValueError:
                return "Invalid date format for start_date. Please use YYYY-MM-DD."

        try:
            hist_data = stock.history(start=start_date, end=query_end_date)
            if hist_data.empty or "Close" not in hist_data:
                return f"No stock data found for {ticker} on {start_date}."
            if end_date is None:
                return f"The closing price for {ticker} on {start_date} was {hist_data['Close'].iloc[0]}."
            else:
                return f"Stock prices for {ticker} from {start_date} to {end_date}:\n{hist_data['Close'].to_string()}"
        except Exception as e:
            return f"Error retrieving historical data for {ticker}: {e}"

    def get_company_info(self, ticker: str) -> str:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get("longBusinessSummary", "No business summary available.")

    def get_income_statement(self, ticker: str) -> str:
        stock = yf.Ticker(ticker)
        return f"Income Statement for {ticker}:\n{stock.income_stmt.to_string()}"

    def get_balance_sheet(self, ticker: str) -> str:
        stock = yf.Ticker(ticker)
        return f"Balance Sheet for {ticker}:\n{stock.balance_sheet.to_string()}"

    def get_cash_flow(self, ticker: str) -> str:
        stock = yf.Ticker(ticker)
        return f"Cash Flow Statement for {ticker}:\n{stock.cashflow.to_string()}"

    def get_key_stats(self, ticker: str) -> str:
        stock = yf.Ticker(ticker)
        info = stock.info
        key_stats = {
            "Market Cap": info.get("marketCap"), "Enterprise Value": info.get("enterpriseValue"),
            "Trailing P/E": info.get("trailingPE"), "Forward P/E": info.get("forwardPE"),
            "PEG Ratio": info.get("pegRatio"), "Price to Sales": info.get("priceToSalesTrailing12Months"),
            "Price to Book": info.get("priceToBook"), "Profit Margins": info.get("profitMargins"),
            "Revenue Growth": info.get("revenueGrowth"), "Earnings Growth": info.get("earningsGrowth"),
        }
        return f"Key Statistics for {ticker}:\n" + "\n".join(f"{k}: {v}" for k, v in key_stats.items())

    def get_stock_news(self, ticker: str) -> List[Dict[str, str]]:
        """
        Retrieves recent news articles for a given stock ticker.
        """
        stock = yf.Ticker(ticker)
        news = stock.news
        if not news:
            return []

        news_list = []
        for article in news[:5]:  # Limit to 5 news items
            link = article.get('link')
            if not link:
                continue

            try:
                downloaded = trafilatura.fetch_url(link)
                if not downloaded:
                    continue
                
                text = trafilatura.extract(downloaded)
                if not text:
                    continue

                news_list.append({
                    "title": article.get('title', ''),
                    "url": link,
                    "content": text,
                    "publisher": article.get('publisher', '')
                })
            except Exception as e:
                logger.error(f"Error scraping article for {ticker} from {link}: {e}")

        return news_list

class FinancialAgent:
    """
    An agent that uses FinancialToolSpec to answer financial questions.
    """
    def __init__(self, llm: OpenRouter, verbose: bool = False):


        self.agent = ReActAgent(
            name="Financial Agent",
            tools=FinancialToolSpec().to_tool_list(),
            llm=llm,
            verbose=verbose,
            system_prompt=FINANCIAL_AGENT_SYSTEM_PROMPT.format(
                current_date=datetime.now().strftime("%Y-%m-%d")
            ),
        )

    async def arun(self, query: str) -> Any:
        """
        Asynchronously runs a query using the ReAct agent.
        The query should contain all necessary information, including the ticker.
        e.g., "what is the income statement for MSFT?"
        """
        try:
            return await self.agent.run(user_msg=query)
        except Exception as e:
            logger.error(f"Error running financial agent for query '{query}': {e}")
            return f"Error running financial agent for query: '{query}'. Error: {e}"


async def run_financial_queries_parallel(agent: FinancialAgent, queries: List[Dict[str, str]]) -> List[Any]:
    """
    Runs financial queries in parallel.
    """
    tasks = [agent.arun(q["query"]) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
