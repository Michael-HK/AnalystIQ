import redis
import json
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class RedisCacheManager:
    """
    A class to manage caching of report data in Redis.
    """
    def __init__(self, host='localhost', port=6379, db=0, ttl_seconds=86400):
        """
        Initializes the RedisCacheManager.

        Args:
            host (str): Redis server host.
            port (int): Redis server port.
            db (int): Redis database number.
            ttl_seconds (int): Time-to-live for cache entries in seconds (default is 24 hours).
        """
        try:
            self.client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                decode_responses=True,
                socket_connect_timeout=2  # Add a 2-second connection timeout
            )
            self.client.ping()
            logger.info("Successfully connected to Redis.")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis: {e}. Caching will be disabled.")
            self.client = None
        self.ttl = ttl_seconds

    def get_cached_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached report structure and context for a given ticker.

        Args:
            ticker (str): The stock ticker symbol.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing 'structure' and 'context', or None if not found.
        """
        if not self.client:
            return None
        
        cache_key = f"agentinvest:report:{ticker}"
        cached_value = self.client.get(cache_key)
        
        if cached_value:
            logger.info(f"Cache hit for ticker: {ticker}")
            return json.loads(cached_value)
        
        logger.info(f"Cache miss for ticker: {ticker}")
        return None

    def set_cached_data(self, ticker: str, company_name: str, structure: List[str], context: str, 
                       web_results: Optional[List[Any]] = None, financial_results: Optional[List[Any]] = None,
                       web_queries: Optional[List[str]] = None, financial_queries: Optional[List[Dict[str, str]]] = None) -> None:
        """
        Caches the report structure, context, and raw results for a given ticker.

        Args:
            ticker (str): The stock ticker symbol.
            company_name (str): The company name.
            structure (List[str]): The generated report structure.
            context (str): The formatted context from data gathering.
            web_results (Optional[List[Any]]): Raw web search results.
            financial_results (Optional[List[Any]]): Raw financial query results.
            web_queries (Optional[List[str]]): The web search queries used.
            financial_queries (Optional[List[Dict[str, str]]]): The financial queries used.
        """
        if not self.client:
            return

        cache_key = f"agentinvest:report:{ticker}"
        data_to_cache = {
            "company_name": company_name,
            "structure": structure,
            "context": context,
            "web_results": web_results,
            "financial_results": financial_results,
            "web_queries": web_queries,
            "financial_queries": financial_queries
        }
        
        self.client.set(cache_key, json.dumps(data_to_cache, default=str), ex=self.ttl)
        logger.info(f"Cached comprehensive data for ticker: {ticker}")

    def clear_all_cached_reports(self) -> int:
        """
        Clears all cached report data (all keys matching agentinvest:report:*).
        
        Returns:
            int: Number of keys deleted, or -1 if Redis is not available.
        """
        if not self.client:
            logger.warning("Redis client not available. Cannot clear cache.")
            return -1
        
        try:
            # Use SCAN to find all keys matching the pattern
            pattern = "agentinvest:report:*"
            keys_to_delete = []
            
            # SCAN is safer than KEYS for production use
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor, match=pattern, count=100)
                keys_to_delete.extend(keys)
                if cursor == 0:
                    break
            
            if keys_to_delete:
                # Delete all found keys
                deleted_count = self.client.delete(*keys_to_delete)
                logger.info(f"Successfully deleted {deleted_count} cached report entries.")
                return deleted_count
            else:
                logger.info("No cached report entries found to delete.")
                return 0
                
        except Exception as e:
            logger.error(f"Error clearing cached reports: {e}")
            return -1

    def clear_cached_report(self, ticker: str) -> bool:
        """
        Clears cached report data for a specific ticker.
        
        Args:
            ticker (str): The stock ticker symbol.
            
        Returns:
            bool: True if successfully deleted, False otherwise.
        """
        if not self.client:
            logger.warning("Redis client not available. Cannot clear cache.")
            return False
            
        try:
            cache_key = f"agentinvest:report:{ticker}"
            deleted = self.client.delete(cache_key)
            
            if deleted:
                logger.info(f"Successfully cleared cached data for ticker: {ticker}")
                return True
            else:
                logger.info(f"No cached data found for ticker: {ticker}")
                return False
                
        except Exception as e:
            logger.error(f"Error clearing cache for ticker {ticker}: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Gets statistics about cached report data.
        
        Returns:
            Dict[str, Any]: Statistics including total keys, memory usage, etc.
        """
        if not self.client:
            return {"error": "Redis client not available"}
            
        try:
            pattern = "agentinvest:report:*"
            keys = []
            
            # Count keys matching our pattern
            cursor = 0
            while True:
                cursor, batch_keys = self.client.scan(cursor, match=pattern, count=100)
                keys.extend(batch_keys)
                if cursor == 0:
                    break
            
            # Get Redis info
            redis_info = self.client.info()
            
            return {
                "total_report_keys": len(keys),
                "cached_tickers": [key.replace("agentinvest:report:", "") for key in keys],
                "redis_memory_used": redis_info.get("used_memory_human", "Unknown"),
                "redis_connected_clients": redis_info.get("connected_clients", "Unknown"),
                "redis_uptime_seconds": redis_info.get("uptime_in_seconds", "Unknown")
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
