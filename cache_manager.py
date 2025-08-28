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

    def set_cached_data(self, ticker: str, company_name: str, structure: List[str], context: str) -> None:
        """
        Caches the report structure and context for a given ticker.

        Args:
            ticker (str): The stock ticker symbol.
            company_name (str): The company name.
            structure (List[str]): The generated report structure.
            context (str): The formatted context from data gathering.
        """
        if not self.client:
            return

        cache_key = f"agentinvest:report:{ticker}"
        data_to_cache = {
            "company_name": company_name,
            "structure": structure,
            "context": context
        }
        
        self.client.set(cache_key, json.dumps(data_to_cache), ex=self.ttl)
        logger.info(f"Cached data for ticker: {ticker}")
