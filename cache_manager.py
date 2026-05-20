import json
import logging
import os
from typing import Any, Dict, List, Optional

import redis

logger = logging.getLogger(__name__)


def _create_redis_client() -> redis.Redis:
    """Build a Redis client from REDIS_URL or host/port env vars."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    socket_connect_timeout = float(os.getenv("REDIS_CONNECT_TIMEOUT", "2"))

    if redis_url:
        return redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=socket_connect_timeout,
        )

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "0"))
    return redis.Redis(
        host=host,
        port=port,
        db=db,
        decode_responses=True,
        socket_connect_timeout=socket_connect_timeout,
    )


class RedisCacheManager:
    """
    A class to manage caching of report data in Redis.
  """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, ttl_seconds: int = 86400):
        """
        Initializes the RedisCacheManager.

        Connection priority:
        1. REDIS_URL (Render Key Value / external Redis)
        2. REDIS_HOST + REDIS_PORT + REDIS_DB
        3. host/port/db constructor args (defaults to localhost)
        """
        self.client: Optional[redis.Redis] = None
        self.ttl = ttl_seconds

        if os.getenv("REDIS_URL"):
            target = "REDIS_URL"
        elif os.getenv("REDIS_HOST"):
            target = f"{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT', '6379')}"
        else:
            target = f"{host}:{port}"

        try:
            self.client = _create_redis_client() if os.getenv("REDIS_URL") or os.getenv("REDIS_HOST") else redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,
                socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "2")),
            )
            self.client.ping()
            logger.info("Successfully connected to Redis at %s.", target)
        except Exception as exc:
            logger.warning("Could not connect to Redis (%s): %s. Caching will be disabled.", target, exc)
            self.client = None

    @property
    def is_enabled(self) -> bool:
        return self.client is not None

    @staticmethod
    def _normalize_report_type(report_type: Optional[str]) -> str:
        normalized = (report_type or "investment").strip().lower()
        return "credit" if normalized in {"credit", "credit_analysis", "credit-analysis"} else "investment"

    def _cache_key(self, ticker: str, report_type: Optional[str] = None) -> str:
        normalized_type = self._normalize_report_type(report_type)
        return f"agentinvest:report:{normalized_type}:{ticker}"

    @staticmethod
    def _credit_agencies_slug(agencies: Optional[List[str]]) -> str:
        if not agencies:
            return "default"
        parts = []
        for agency in sorted(agencies):
            slug = (
                str(agency)
                .strip()
                .lower()
                .replace("'", "")
                .replace("&", "and")
                .replace(" ", "_")
            )
            if slug:
                parts.append(slug)
        return "_".join(parts) if parts else "default"

    def _credit_cache_key(
        self,
        ticker: str,
        agencies: Optional[List[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> str:
        period_slug = "latest"
        if start_year is not None and end_year is not None:
            period_slug = f"{start_year}_{end_year}"
        return f"agentinvest:credit_rating:{ticker}:{self._credit_agencies_slug(agencies)}:{period_slug}"

    def get_credit_rating_cached_data(
        self,
        ticker: str,
        agencies: Optional[List[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None

        cache_key = self._credit_cache_key(ticker, agencies, start_year, end_year)
        cached_value = self.client.get(cache_key)
        if cached_value:
            logger.info("Credit rating cache hit for ticker: %s", ticker)
            return json.loads(cached_value)

        logger.info("Credit rating cache miss for ticker: %s", ticker)
        return None

    def merge_credit_rating_cached_data(
        self,
        ticker: str,
        agencies: Optional[List[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        *,
        company_name: Optional[str] = None,
        web_queries: Optional[List[str]] = None,
        web_results: Optional[List[Any]] = None,
        context: Optional[str] = None,
        source_map: Optional[Dict[str, Any]] = None,
        comparison_paragraphs: Optional[List[str]] = None,
        comparison_table_markdown: Optional[str] = None,
        cited_source_map: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.client:
            return

        existing = self.get_credit_rating_cached_data(ticker, agencies, start_year, end_year) or {}
        merged: Dict[str, Any] = {
            "ticker": ticker,
            "agencies": existing.get("agencies", agencies or []),
            "start_year": existing.get("start_year", start_year),
            "end_year": existing.get("end_year", end_year),
            "company_name": existing.get("company_name", ""),
            "web_queries": existing.get("web_queries", []),
            "web_results": existing.get("web_results", []),
            "context": existing.get("context", ""),
            "source_map": existing.get("source_map", {}),
            "comparison_paragraphs": existing.get("comparison_paragraphs", []),
            "comparison_table_markdown": existing.get("comparison_table_markdown", ""),
            "cited_source_map": existing.get("cited_source_map", {}),
        }
        updates = {
            "agencies": agencies,
            "start_year": start_year,
            "end_year": end_year,
            "company_name": company_name,
            "web_queries": web_queries,
            "web_results": web_results,
            "context": context,
            "source_map": source_map,
            "comparison_paragraphs": comparison_paragraphs,
            "comparison_table_markdown": comparison_table_markdown,
            "cited_source_map": cited_source_map,
        }
        for key, value in updates.items():
            if value is not None:
                merged[key] = value

        cache_key = self._credit_cache_key(
            ticker,
            agencies or merged.get("agencies"),
            merged.get("start_year"),
            merged.get("end_year"),
        )
        self.client.set(cache_key, json.dumps(merged, default=str), ex=self.ttl)
        logger.info("Merged credit rating cache update for ticker: %s", ticker)

    def get_cached_data(self, ticker: str, report_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached report structure and context for a given ticker.

        Args:
            ticker (str): The stock ticker symbol.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing 'structure' and 'context', or None if not found.
        """
        if not self.client:
            return None

        normalized_type = self._normalize_report_type(report_type)
        cache_key = self._cache_key(ticker, normalized_type)
        cached_value = self.client.get(cache_key)

        # Backward compatibility for legacy investment-only cache keys.
        if not cached_value and normalized_type == "investment":
            cached_value = self.client.get(f"agentinvest:report:{ticker}")

        if cached_value:
            logger.info("Cache hit for ticker: %s report_type: %s", ticker, normalized_type)
            return json.loads(cached_value)

        logger.info("Cache miss for ticker: %s report_type: %s", ticker, normalized_type)
        return None

    def set_cached_data(
        self,
        ticker: str,
        company_name: str,
        structure: List[str],
        context: str,
        web_results: Optional[List[Any]] = None,
        financial_results: Optional[List[Any]] = None,
        web_queries: Optional[List[str]] = None,
        financial_queries: Optional[List[Dict[str, str]]] = None,
        report_type: Optional[str] = None,
    ) -> None:
        """Caches the report structure, context, and raw results for a given ticker."""
        if not self.client:
            return

        normalized_type = self._normalize_report_type(report_type)
        cache_key = self._cache_key(ticker, normalized_type)
        data_to_cache = {
            "report_type": normalized_type,
            "company_name": company_name,
            "structure": structure,
            "context": context,
            "web_results": web_results,
            "financial_results": financial_results,
            "web_queries": web_queries,
            "financial_queries": financial_queries,
        }

        self.client.set(cache_key, json.dumps(data_to_cache, default=str), ex=self.ttl)
        logger.info("Cached comprehensive data for ticker: %s report_type: %s", ticker, normalized_type)

    def merge_cached_data(
        self,
        ticker: str,
        report_type: Optional[str] = None,
        *,
        company_name: Optional[str] = None,
        structure: Optional[List[str]] = None,
        context: Optional[str] = None,
        web_results: Optional[List[Any]] = None,
        financial_results: Optional[List[Any]] = None,
        web_queries: Optional[List[str]] = None,
        financial_queries: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """Merge partial updates into the cached report payload (write-after-each-step)."""
        if not self.client:
            return

        normalized_type = self._normalize_report_type(report_type)
        existing = self.get_cached_data(ticker, report_type=report_type) or {}
        merged: Dict[str, Any] = {
            "report_type": normalized_type,
            "company_name": existing.get("company_name", ""),
            "structure": existing.get("structure", []),
            "context": existing.get("context", ""),
            "web_results": existing.get("web_results", []),
            "financial_results": existing.get("financial_results", []),
            "web_queries": existing.get("web_queries", []),
            "financial_queries": existing.get("financial_queries", []),
        }
        updates = {
            "company_name": company_name,
            "structure": structure,
            "context": context,
            "web_results": web_results,
            "financial_results": financial_results,
            "web_queries": web_queries,
            "financial_queries": financial_queries,
        }
        for key, value in updates.items():
            if value is not None:
                merged[key] = value

        cache_key = self._cache_key(ticker, normalized_type)
        self.client.set(cache_key, json.dumps(merged, default=str), ex=self.ttl)
        logger.info("Merged cache update for ticker: %s report_type: %s", ticker, normalized_type)

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
            pattern = "agentinvest:report:*"
            keys_to_delete: List[str] = []

            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor, match=pattern, count=100)
                keys_to_delete.extend(keys)
                if cursor == 0:
                    break

            if keys_to_delete:
                deleted_count = self.client.delete(*keys_to_delete)
                logger.info("Successfully deleted %s cached report entries.", deleted_count)
                return int(deleted_count)

            logger.info("No cached report entries found to delete.")
            return 0

        except Exception as exc:
            logger.error("Error clearing cached reports: %s", exc)
            return -1

    def clear_cached_report(self, ticker: str, report_type: Optional[str] = None) -> bool:
        """Clears cached report data for a specific ticker and report type."""
        if not self.client:
            logger.warning("Redis client not available. Cannot clear cache.")
            return False

        try:
            normalized_type = self._normalize_report_type(report_type)
            cache_key = self._cache_key(ticker, normalized_type)
            deleted = self.client.delete(cache_key)
            if deleted:
                logger.info("Successfully cleared cached data for ticker: %s report_type: %s", ticker, normalized_type)
                return True

            logger.info("No cached data found for ticker: %s report_type: %s", ticker, normalized_type)
            return False

        except Exception as exc:
            logger.error("Error clearing cache for ticker %s: %s", ticker, exc)
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Gets statistics about cached report data."""
        if not self.client:
            return {"error": "Redis client not available", "enabled": False}

        try:
            pattern = "agentinvest:report:*"
            keys: List[str] = []

            cursor = 0
            while True:
                cursor, batch_keys = self.client.scan(cursor, match=pattern, count=100)
                keys.extend(batch_keys)
                if cursor == 0:
                    break

            redis_info = self.client.info()

            return {
                "enabled": True,
                "total_report_keys": len(keys),
                "cached_tickers": [key.replace("agentinvest:report:", "") for key in keys],
                "redis_memory_used": redis_info.get("used_memory_human", "Unknown"),
                "redis_connected_clients": redis_info.get("connected_clients", "Unknown"),
                "redis_uptime_seconds": redis_info.get("uptime_in_seconds", "Unknown"),
            }

        except Exception as exc:
            logger.error("Error getting cache stats: %s", exc)
            return {"error": str(exc), "enabled": True}
