import html as html_module
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog
from dacite import Config, from_dict
from notion_client import Client
from tenacity import retry, stop_after_attempt, wait_fixed

from octopus_scraper.protos import Content
from octopus_scraper.storages.base_storage import BaseStorage
from octopus_scraper.storages.markdown_to_notion import MarkdownToNotionConverter

logger = structlog.getLogger(__name__)
MAX_NOTION_SUMMARY_LENGTH = 2000
NOTION_PROPERTIY_TITLE_NAME = "Name"
NOTION_PROPERTIY_SUMMARY_NAME = "Summary"
NOTION_PROPERTIY_CONTENT_ID = "ContentId"
NOTION_PROPERTIY_URL = "URL"
NOTION_PROPERTY_AUTHOR_NAME = "Author"
NOTION_PROPERTY_KEYWORDS_NAME = "Keywords"
NOTION_PROPERTY_TAGS_NAME = "Tags"
NOTION_PROPERTY_SOURCE_NAME = "Source"
NOTION_PROPERTY_PUBLISHED_DATE = "Published Date"

# Rate limiting: Notion recommends 3 requests per second
# We'll be more conservative and use 2 requests per second
NOTION_MIN_REQUEST_INTERVAL = 0.5  # 500ms between requests = 2 req/sec

# Cache TTL for content IDs (seconds)
CONTENT_IDS_CACHE_TTL = 300  # 5 minutes

# Max concurrent workers for page creation (bounded by Notion rate limit)
MAX_UPLOAD_WORKERS = 2

# Default delay (seconds) before batch-level retry of failed uploads.
# Gives Notion time to become consistent before re-querying.
# Configurable via NOTION_UPLOAD_RETRY_DELAY env var.
DEFAULT_UPLOAD_RETRY_DELAY = 30


@dataclass
class NotionAPIConfig:
    api_key: str
    database_id: str


class NotionStorage(BaseStorage):
    """
    Store contents in Notion database

    Examples:
    >>> notion_storage = NotionStorage(config)
    >>> notion_storage.store_content(contents)

    """

    def __init__(self, config: Dict):
        self.config = from_dict(
            data_class=NotionAPIConfig,
            data=config,
            config=Config(cast=[str], strict=True),
        )

        self.notion = Client(auth=self.config.api_key)
        self._check_property_exist()

        # Thread-safe rate limiting
        self._last_request_time = 0.0
        self._rate_limit_lock = threading.Lock()

        # Cache for content IDs to avoid repeated full-database scans
        self._content_ids_cache: Optional[set] = None
        self._content_ids_cache_time: float = 0.0

        self._markdown_converter = MarkdownToNotionConverter()

        # Configurable delay before batch-level retry
        self._upload_retry_delay = float(
            os.environ.get("NOTION_UPLOAD_RETRY_DELAY", str(DEFAULT_UPLOAD_RETRY_DELAY))
        )

    def _rate_limit(self):
        """Enforce rate limiting to avoid hitting Notion API limits.

        Thread-safe: uses a lock to coordinate rate limiting across
        concurrent upload workers.

        Notion recommends max 3 requests per second. We use 2 req/sec to be safe.
        This method ensures minimum interval between requests.
        """
        with self._rate_limit_lock:
            current_time = time.time()
            time_since_last_request = current_time - self._last_request_time

            if time_since_last_request < NOTION_MIN_REQUEST_INTERVAL:
                sleep_time = NOTION_MIN_REQUEST_INTERVAL - time_since_last_request
                logger.debug(
                    f"Rate limiting: sleeping {sleep_time:.2f}s",
                    min_interval=NOTION_MIN_REQUEST_INTERVAL,
                )
                time.sleep(sleep_time)

            self._last_request_time = time.time()

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def get_all_content_ids(self, force_refresh: bool = False) -> set:
        """批量获取数据库中所有已存在的 content_id。

        Uses a TTL-based cache to avoid repeated full-database scans.
        The cache is automatically updated when new content is stored.

        Args:
            force_refresh: If True, bypass cache and query Notion directly.
        """
        # Return cached result if still valid
        if not force_refresh and self._content_ids_cache is not None:
            cache_age = time.time() - self._content_ids_cache_time
            if cache_age < CONTENT_IDS_CACHE_TTL:
                logger.debug(
                    "Using cached content IDs",
                    cache_size=len(self._content_ids_cache),
                    cache_age_seconds=round(cache_age, 1),
                )
                return self._content_ids_cache.copy()

        all_content_ids = set()
        has_more = True
        next_cursor = None

        # Resolve the property ID for ContentId to use filter_properties,
        # which drastically reduces response payload size.
        content_id_property_id = self._get_property_id(NOTION_PROPERTIY_CONTENT_ID)

        while has_more:
            query_params = {
                "database_id": self.config.database_id,
                "page_size": 100,  # Notion API 最大支持 100
            }

            if next_cursor:
                query_params["start_cursor"] = next_cursor

            # Only request the ContentId property to reduce payload
            if content_id_property_id:
                query_params["filter_properties"] = [content_id_property_id]

            response = self.notion.databases.query(**query_params)

            if isinstance(response, dict):
                results = response.get("results", [])
                for page in results:
                    properties = page.get("properties", {})
                    content_id_prop = properties.get(NOTION_PROPERTIY_CONTENT_ID, {})
                    rich_text = content_id_prop.get("rich_text", [])
                    if rich_text and len(rich_text) > 0:
                        content_id = rich_text[0].get("text", {}).get("content", "")
                        if content_id:
                            all_content_ids.add(content_id)

                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")
            else:
                logger.error("Notion databases query response is not a dict.")
                break

        # Update cache
        self._content_ids_cache = all_content_ids.copy()
        self._content_ids_cache_time = time.time()

        logger.info(
            f"Retrieved {len(all_content_ids)} existing content IDs from Notion"
        )
        return all_content_ids

    def invalidate_content_ids_cache(self):
        """Invalidate the content IDs cache, forcing a fresh query on next access."""
        self._content_ids_cache = None
        self._content_ids_cache_time = 0.0
        logger.debug("Content IDs cache invalidated")

    def _get_property_id(self, property_name: str) -> Optional[str]:
        """Retrieve the Notion-internal property ID for a given property name.

        Used to pass ``filter_properties`` in database queries so that Notion
        returns only the requested columns, reducing response payload size.

        Returns:
            The short property ID string, or None if lookup fails.
        """
        try:
            db_info = self.notion.databases.retrieve(
                database_id=self.config.database_id
            )
            props = db_info.get("properties", {})
            prop = props.get(property_name, {})
            return prop.get("id")
        except Exception as e:
            logger.debug(
                "Failed to resolve property ID, will query without filter_properties",
                property_name=property_name,
                error=str(e),
            )
            return None

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def _check_property_exist(self):
        """Ensure required properties exist in the content database.

        Retrieves the current database schema first and only creates
        properties that are missing.  This avoids overwriting existing
        select / multi_select options (e.g. Source, Tags, Keywords)
        which would be cleared if we unconditionally passed
        ``{"select": {}}`` for an existing column.
        """
        # Define expected property schemas
        expected_properties = {
            NOTION_PROPERTIY_TITLE_NAME: {"title": {}},
            NOTION_PROPERTIY_SUMMARY_NAME: {"rich_text": {}},
            NOTION_PROPERTIY_URL: {"url": {}},
            NOTION_PROPERTIY_CONTENT_ID: {"rich_text": {}},
            NOTION_PROPERTY_AUTHOR_NAME: {"rich_text": {}},
            NOTION_PROPERTY_KEYWORDS_NAME: {"multi_select": {}},
            NOTION_PROPERTY_TAGS_NAME: {"multi_select": {}},
            NOTION_PROPERTY_SOURCE_NAME: {"select": {}},
            NOTION_PROPERTY_PUBLISHED_DATE: {"date": {}},
        }

        # Retrieve current database schema to find existing columns
        db_info = self.notion.databases.retrieve(database_id=self.config.database_id)
        existing_properties = set(db_info.get("properties", {}).keys())

        # Only add columns that are missing
        missing_properties = {
            name: prop_def
            for name, prop_def in expected_properties.items()
            if name not in existing_properties
        }

        if not missing_properties:
            logger.debug("All required content database columns already exist")
            return

        logger.info(
            "Creating missing content database columns",
            missing_columns=list(missing_properties.keys()),
        )

        self.notion.databases.update(
            database_id=self.config.database_id,
            properties=missing_properties,
        )

    def _sanitize_option_name(self, name: str, max_length: int = 100) -> str:
        """Sanitize select/multi-select option names for Notion API.

        Notion enforces a 100-character limit on option names and rejects
        names with certain special characters (newlines, etc.).

        Args:
            name: Raw option name
            max_length: Maximum allowed length (Notion limit is 100)

        Returns:
            Sanitized name that meets Notion requirements, or empty string if invalid
        """
        if not name or not isinstance(name, str):
            return ""

        # Remove leading/trailing whitespace
        name = name.strip()
        if not name:
            return ""

        # Replace newlines and multiple spaces with single space
        name = re.sub(r"[\r\n]+", " ", name)
        name = re.sub(r"\s+", " ", name)

        # Truncate if too long
        if len(name) > max_length:
            name = name[: max_length - 3] + "..."
            logger.debug(
                f"Truncated option name to {max_length} chars",
                original_length=len(name) + 3,
            )

        return name

    def _strip_html(self, text: str) -> str:
        """Strip HTML tags and decode HTML entities from plain-text properties.

        Notion ``rich_text`` database properties do not render HTML markup, so
        raw HTML in the summary field would appear as literal tag characters.
        This method converts such content to readable plain text.

        Args:
            text: Raw text that may contain HTML tags and entities.

        Returns:
            Plain text with HTML tags removed and entities decoded.
        """
        if not text:
            return text
        # Decode HTML entities first (e.g. &gt; → >, &amp; → &, &#39; → ')
        text = html_module.unescape(text)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Normalise whitespace introduced by removed tags
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _validate_url(self, url: str) -> Optional[str]:
        """Validate and sanitize URL for Notion URL property.

        Args:
            url: URL string to validate

        Returns:
            Valid URL or None if invalid/empty
        """
        if not url or not isinstance(url, str):
            return None

        # Remove all whitespace including newlines
        url = url.strip()
        if not url:
            return None

        # Basic URL validation - must start with http:// or https://
        if not url.startswith(("http://", "https://")):
            logger.warning(
                "Invalid URL format (missing protocol), setting to None", url=url[:100]
            )
            return None

        # Check for spaces and other invalid characters (after stripping)
        if " " in url or "\n" in url or "\r" in url or "\t" in url:
            logger.warning(
                "Invalid URL (contains whitespace), setting to None", url=url[:100]
            )
            return None

        return url

    def _build_properties(self, content: Content) -> dict:
        """构建Notion属性结构"""
        # Validate and sanitize title (cannot be empty)
        title = content.title.strip() if content.title else ""
        if not title:
            title = "Untitled"
            logger.warning(
                "Content has empty title, using 'Untitled'",
                content_id=content.content_id,
            )

        # Validate and sanitize summary
        summary = content.summary if content.summary else ""
        # Strip HTML tags/entities – Notion text properties don't render HTML
        summary = self._strip_html(summary)
        if len(summary) > MAX_NOTION_SUMMARY_LENGTH:
            logger.warning(
                f"Content summary return larger than {MAX_NOTION_SUMMARY_LENGTH}. Summary will be cut off.",
                content_id=content.content_id,
            )
        summary = summary[:MAX_NOTION_SUMMARY_LENGTH]
        if not summary.strip():
            summary = "[No summary available]"

        # Validate URL
        validated_url = self._validate_url(content.link)
        if not validated_url and content.link:
            logger.warning(
                "Invalid URL detected, setting to None",
                content_id=content.content_id,
                original_url=content.link[:100] if content.link else None,
            )

        # Sanitize keywords (filter empty and truncate long ones)
        sanitized_keywords = [
            self._sanitize_option_name(keyword) for keyword in (content.keywords or [])
        ]
        sanitized_keywords = [
            k for k in sanitized_keywords if k
        ]  # Remove empty strings

        # Sanitize tags (filter empty and truncate long ones)
        sanitized_tags = [
            self._sanitize_option_name(tag) for tag in (content.tags or [])
        ]
        sanitized_tags = [t for t in sanitized_tags if t]  # Remove empty strings

        # Sanitize scraper name
        sanitized_scraper_name = (
            self._sanitize_option_name(content.scraper_name)
            if content.scraper_name
            else None
        )

        return {
            NOTION_PROPERTIY_TITLE_NAME: {"title": [{"text": {"content": title}}]},
            NOTION_PROPERTIY_SUMMARY_NAME: {
                "rich_text": [{"text": {"content": summary}}]
            },
            NOTION_PROPERTIY_URL: {"url": validated_url},
            NOTION_PROPERTIY_CONTENT_ID: {
                "rich_text": [{"text": {"content": content.content_id}}]
            },
            NOTION_PROPERTY_AUTHOR_NAME: {
                "rich_text": [{"text": {"content": content.author or ""}}]
            },
            NOTION_PROPERTY_KEYWORDS_NAME: {
                "multi_select": [{"name": keyword} for keyword in sanitized_keywords]
            },
            NOTION_PROPERTY_TAGS_NAME: {
                "multi_select": [{"name": tag} for tag in sanitized_tags],
            },
            NOTION_PROPERTY_SOURCE_NAME: (
                {"select": {"name": sanitized_scraper_name}}
                if sanitized_scraper_name
                else {"select": None}
            ),
            NOTION_PROPERTY_PUBLISHED_DATE: (
                {"date": {"start": parsed_date}}
                if (parsed_date := self._parse_published_date(content.published))
                else {"date": None}
            ),
        }

    def _parse_published_date(self, published: str) -> Optional[str]:
        """Parse published date string to ISO 8601 format for Notion.

        Args:
            published: Date string from RSS feed (e.g. '2025-04-06T13:50:59+08:00').

        Returns:
            ISO 8601 formatted date string, or None if parsing fails.
        """
        if not published:
            return None
        try:
            from dateutil import parser as date_parser

            dt = date_parser.parse(published)
            return dt.isoformat()
        except (ValueError, TypeError) as e:
            logger.warning(
                "Failed to parse published date",
                published=published,
                error=str(e),
            )
            return None

    def _store_content(self, content: Content) -> bool:
        """存储单个内容，不做重复性检查。

        Does NOT retry internally. Batch-level retry is handled by
        store_contents which re-checks Notion after a delay.
        Returns False only for permanent/non-retryable failures.
        """
        # Warn if scraper_name (Source) is missing — helps diagnose unstable Source field
        if not content.scraper_name:
            logger.warning(
                "Content has no scraper_name (Source will be empty in Notion)",
                content_id=content.content_id,
                title=content.title[:80] if content.title else "N/A",
            )

        children = self._markdown_converter.convert(content.content)

        # Build validated properties
        properties = self._build_properties(content)

        # Notion has a limit of ~100 blocks per page creation
        # If we have more blocks, we'll create the page with first 100,
        # then append the rest in batches
        max_blocks_per_request = 100
        initial_children = children[:max_blocks_per_request]
        remaining_children = children[max_blocks_per_request:]

        # Log payload for debugging (helpful for diagnosing 400 errors)
        logger.debug(
            "Creating Notion page",
            content_id=content.content_id,
            title=properties.get(NOTION_PROPERTIY_TITLE_NAME, {})
            .get("title", [{}])[0]
            .get("text", {})
            .get("content", "N/A")[:50],
            url=properties.get(NOTION_PROPERTIY_URL, {}).get("url"),
            total_blocks=len(children),
            initial_blocks=len(initial_children),
            remaining_blocks=len(remaining_children),
        )

        # Apply rate limiting before API call
        self._rate_limit()

        try:
            page = self.notion.pages.create(
                parent={"database_id": self.config.database_id},
                properties=properties,
                children=initial_children,
            )
            page_id = page["id"]
        except Exception as e:
            # Log detailed error information for 400 errors
            error_details = {
                "content_id": content.content_id,
                "title": content.title[:100] if content.title else "N/A",
                "error_type": type(e).__name__,
                "error_message": str(e),
            }

            # Try to extract detailed error message from APIResponseError
            if hasattr(e, "body"):
                error_details["notion_error_body"] = str(e.body)[:500]
            if hasattr(e, "code"):
                error_details["notion_error_code"] = e.code

            logger.error(
                "Failed to create Notion page - detailed error",
                **error_details,
            )

            # Log a sample of the properties that failed
            logger.debug(
                "Failed properties sample",
                content_id=content.content_id,
                title=properties.get(NOTION_PROPERTIY_TITLE_NAME, {})
                .get("title", [{}])[0]
                .get("text", {})
                .get("content", "N/A")[:100],
                url=properties.get(NOTION_PROPERTIY_URL, {}).get("url"),
                keywords_count=len(
                    properties.get(NOTION_PROPERTY_KEYWORDS_NAME, {}).get(
                        "multi_select", []
                    )
                ),
                tags_count=len(
                    properties.get(NOTION_PROPERTY_TAGS_NAME, {}).get(
                        "multi_select", []
                    )
                ),
            )

            return False

        # Update cache immediately after successful page creation,
        # before appending remaining blocks. This ensures retry logic
        # and concurrent uploads can detect this item was already created.
        if self._content_ids_cache is not None:
            self._content_ids_cache.add(content.content_id)

        # If there are remaining blocks, append them in batches
        if remaining_children:
            logger.info(
                f"Appending {len(remaining_children)} additional blocks to page",
                content_id=content.content_id,
                page_id=page_id,
            )

            # Append remaining blocks in batches of 100
            for i in range(0, len(remaining_children), max_blocks_per_request):
                batch = remaining_children[i : i + max_blocks_per_request]

                # Apply rate limiting before each batch append
                self._rate_limit()

                try:
                    self.notion.blocks.children.append(
                        block_id=page_id,
                        children=batch,
                    )
                    logger.debug(
                        f"Appended batch of {len(batch)} blocks",
                        content_id=content.content_id,
                        batch_start=i,
                        batch_size=len(batch),
                    )
                except Exception as e:
                    logger.error(
                        "Failed to append block batch",
                        content_id=content.content_id,
                        page_id=page_id,
                        batch_start=i,
                        batch_size=len(batch),
                        error=str(e),
                    )
                    # Continue trying other batches even if one fails
                    continue

        logger.info(
            "Content stored successfully",
            content_id=content.content_id,
            source=content.scraper_name,
            total_blocks=len(children),
        )

        return True

    def store_contents(self, contents: List[Content], deduplicate=True) -> List[bool]:
        """批量存储内容到 Notion 数据库（并发版本）。

        Overrides BaseStorage.store_contents to upload pages concurrently
        using a thread pool, significantly reducing total upload time while
        respecting Notion's rate limits via the thread-safe ``_rate_limit``.

        Args:
            contents: 要存储的内容列表
            deduplicate: 是否启用去重功能，默认为 True

        Returns:
            每个内容存储结果的列表，True 表示存储成功/已跳过
        """
        if not contents:
            return []

        # Batch-internal dedup: keep first occurrence of each content_id
        if deduplicate:
            seen_ids: set = set()
            unique_contents: List[Content] = []
            batch_dup_count = 0
            for content in contents:
                if content.content_id not in seen_ids:
                    seen_ids.add(content.content_id)
                    unique_contents.append(content)
                else:
                    batch_dup_count += 1
            if batch_dup_count > 0:
                logger.warning(
                    "Removed batch-internal duplicates",
                    original_count=len(contents),
                    unique_count=len(unique_contents),
                    duplicates_removed=batch_dup_count,
                )
            contents_to_process = unique_contents
        else:
            contents_to_process = contents

        existing_content_ids = self.get_all_content_ids()
        store_contents_list = []
        if deduplicate:
            logger.info("Deduplication enabled, checking existing content IDs...")
            for content in contents_to_process:
                if content.content_id not in existing_content_ids:
                    store_contents_list.append(content)
                else:
                    logger.debug(
                        "Content already exists in storage, skipping",
                        content_id=content.content_id,
                    )
        else:
            store_contents_list = contents_to_process

        # Upload contents concurrently with bounded parallelism
        results = []
        if store_contents_list:
            results = self._concurrent_store(store_contents_list)

            # Batch-level retry: if any items failed, sleep then re-check Notion
            failed_indices = [i for i, r in enumerate(results) if not r]
            if failed_indices:
                failed_contents = [store_contents_list[i] for i in failed_indices]
                failed_ids = [c.content_id for c in failed_contents]
                logger.warning(
                    "Some items failed in first pass, will retry after delay",
                    failed_count=len(failed_indices),
                    retry_delay_seconds=self._upload_retry_delay,
                    failed_content_ids=failed_ids,
                )

                time.sleep(self._upload_retry_delay)

                # Force-refresh cache to get Notion's true state
                self.invalidate_content_ids_cache()
                refreshed_ids = self.get_all_content_ids(force_refresh=True)

                # Only retry items confirmed NOT in Notion
                retry_contents = []
                retry_original_indices = []
                for idx in failed_indices:
                    content = store_contents_list[idx]
                    if content.content_id in refreshed_ids:
                        logger.info(
                            "Failed item found in Notion after delay, skipping retry",
                            content_id=content.content_id,
                        )
                        results[idx] = True  # It was actually created
                    else:
                        retry_contents.append(content)
                        retry_original_indices.append(idx)

                if retry_contents:
                    logger.info(
                        "Retrying confirmed-missing items",
                        retry_count=len(retry_contents),
                    )
                    retry_results = self._concurrent_store(retry_contents)
                    for i, orig_idx in enumerate(retry_original_indices):
                        results[orig_idx] = retry_results[i]

                    # If still failures after retry, invalidate cache for next cycle
                    still_failed = any(not r for r in retry_results)
                    if still_failed:
                        self.invalidate_content_ids_cache()

        # Count skipped (both batch-internal dups and Notion-existing)
        skipped_count = len(contents) - len(store_contents_list)
        results.extend([True] * skipped_count)

        success_count = sum(1 for r in results if r)
        failure_count = sum(1 for r in results if not r)
        logger.info(
            f"Batch storage completed: {success_count} stored, "
            f"{failure_count} failed, {skipped_count} skipped "
            f"(1 API call for deduplicate check, concurrent upload)"
        )
        return results

    def _concurrent_store(self, contents: List[Content]) -> List[bool]:
        """Store multiple contents concurrently using a thread pool.

        Rate limiting is enforced per-request via the thread-safe
        ``_rate_limit`` method, keeping aggregate throughput within
        Notion's limits.

        Args:
            contents: List of non-duplicate contents to store.

        Returns:
            Ordered list of booleans indicating success/failure.
        """
        results: List[Optional[bool]] = [None] * len(contents)

        # For small batches, sequential is fine (avoids thread overhead)
        if len(contents) <= 2:
            for i, content in enumerate(contents):
                try:
                    results[i] = self._store_content(content)
                except Exception as e:
                    logger.error(
                        "Failed to store content after retries",
                        content_id=content.content_id,
                        error=str(e),
                    )
                    results[i] = False
            return [r if r is not None else False for r in results]

        logger.info(
            f"Starting concurrent upload of {len(contents)} items "
            f"with {MAX_UPLOAD_WORKERS} workers"
        )

        with ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS) as executor:
            future_to_index = {}
            for i, content in enumerate(contents):
                future = executor.submit(self._store_content, content)
                future_to_index[future] = i

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(
                        "Failed to store content after retries",
                        content_id=contents[idx].content_id,
                        error=str(e),
                    )
                    results[idx] = False

        return [r if r is not None else False for r in results]
