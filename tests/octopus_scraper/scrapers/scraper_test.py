from unittest.mock import Mock, patch

import pytest

from octopus_scraper.scrapers.scraper import Content, Scraper


@pytest.fixture
def sspai_rss_hub_config():
    config = {
        "fetcher_name": "rsshub",
        "fetcher_config": {
            "hub_root": "https://rsshub.thzu.xyz",
            "route": "/sspai/matrix",
            "fetch_params": {"limit": 3},
        },
        "content_processor_configs": {},
    }
    return config


@pytest.fixture
def direct_rss_config():
    config = {
        "fetcher_name": "direct_rss",
        "fetcher_config": {
            "hub_root": "https://example.com",
            "route": "/feed.xml",
        },
        "content_processor_configs": {},
    }
    return config


class TestScraper:
    # TODO: no processer imp omit for now <16-03-25, Duan-JM> #
    @pytest.mark.need_external_service
    def test_scrap_contents(self, sspai_rss_hub_config):
        scraper = Scraper(sspai_rss_hub_config)
        contents = scraper.scrap_contents(params={})
        assert len(contents) == 3

        # check if params avaliable
        contents = scraper.scrap_contents(params={"limit": 1})
        assert len(contents) == 1

    def test_content_processing(self, sspai_rss_hub_config):
        scraper = Scraper(sspai_rss_hub_config)

        fetched_contents = [
            Content(
                content_id="http://xxxx",
                title="Original Article",
                link="http://original.com",
                summary="Original summary",
                content="Original content",
                published="2025-04-06T13:50:59+08:00",
            )
        ]
        scraper.active_content_processor = {"mock_processor": lambda x: x}
        processed_contents = scraper._content_process(fetched_contents)

        assert len(processed_contents) == 1
        assert processed_contents[0].title == "Original Article"
        assert processed_contents[0].link == "http://original.com"
        assert processed_contents[0].summary == "Original summary"
        assert processed_contents[0].content == "Original content"

    def test_scraper_initialization_direct_rss(self, direct_rss_config):
        """测试DirectRSS fetcher的初始化"""
        scraper = Scraper(direct_rss_config)
        assert scraper.config.fetcher_name == "direct_rss"
        assert scraper.activate_fetcher is not None
        assert scraper.storage is None

    def test_scraper_initialization_invalid_fetcher(self):
        """测试无效fetcher的初始化"""
        config = {
            "fetcher_name": "invalid_fetcher",
            "fetcher_config": {},
            "content_processor_configs": {},
        }

        # 初始化时应该抛出异常但被捕获
        scraper = Scraper(config)

        # 验证activate_fetcher没有被正确设置
        assert (
            not hasattr(scraper, "activate_fetcher") or scraper.activate_fetcher is None
        )

    def test_set_storage(self, sspai_rss_hub_config):
        """测试设置存储器"""
        scraper = Scraper(sspai_rss_hub_config)
        mock_storage = Mock()

        scraper.set_storage(mock_storage)
        assert scraper.storage == mock_storage

    def test_scrap_contents_with_storage(self, sspai_rss_hub_config):
        """测试带存储器的内容抓取（去重）"""
        scraper = Scraper(sspai_rss_hub_config)

        # Mock storage
        mock_storage = Mock()
        mock_storage.get_all_content_ids.return_value = {"existing_id"}
        scraper.set_storage(mock_storage)

        # Mock fetcher
        mock_contents = [
            Content(
                content_id="existing_id",  # This one exists
                title="Existing Title",
                link="http://existing.com",
                summary="Existing summary",
                content="Existing content",
                published="2025-01-01T00:00:00Z",
            ),
            Content(
                content_id="new_id",  # This one is new
                title="New Title",
                link="http://new.com",
                summary="New summary",
                content="New content",
                published="2025-01-01T00:00:00Z",
            ),
        ]

        scraper.activate_fetcher = Mock()
        scraper.activate_fetcher.fetch_contents.return_value = mock_contents

        # Run test
        result = scraper.scrap_contents({"test": "params"})

        # Verify calls
        scraper.activate_fetcher.fetch_contents.assert_called_once_with(
            {"test": "params"}
        )
        mock_storage.get_all_content_ids.assert_called_once()

        # Should only return the new content (existing one filtered out)
        assert len(result) == 1
        assert result[0].content_id == "new_id"

    def test_scrap_contents_without_storage(self, sspai_rss_hub_config):
        """测试不带存储器的内容抓取（不去重）"""
        scraper = Scraper(sspai_rss_hub_config)

        # Mock fetcher
        mock_contents = [
            Content(
                content_id="test_id",
                title="Test Title",
                link="http://test.com",
                summary="Test summary",
                content="Test content",
                published="2025-01-01T00:00:00Z",
            )
        ]

        scraper.activate_fetcher = Mock()
        scraper.activate_fetcher.fetch_contents.return_value = mock_contents

        # Run test
        result = scraper.scrap_contents({"test": "params"})

        # Verify
        scraper.activate_fetcher.fetch_contents.assert_called_once_with(
            {"test": "params"}
        )
        assert result == mock_contents

    def test_content_process_multiple_processors(self, sspai_rss_hub_config):
        """测试多个处理器的内容处理"""
        scraper = Scraper(sspai_rss_hub_config)

        initial_contents = [
            Content(
                content_id="test_id",
                title="Original Title",
                link="http://test.com",
                summary="Original summary",
                content="Original content",
                published="2025-01-01T00:00:00Z",
            )
        ]

        # Mock processors
        def processor1(contents):
            for content in contents:
                content.title = content.title + " - Processed1"
            return contents

        def processor2(contents):
            for content in contents:
                content.title = content.title + " - Processed2"
            return contents

        scraper.active_content_processor = {
            "processor1": processor1,
            "processor2": processor2,
        }

        # Run test
        result = scraper._content_process(initial_contents)

        # Verify
        assert len(result) == 1
        assert result[0].title == "Original Title - Processed1 - Processed2"

    def test_content_process_empty_list(self, sspai_rss_hub_config):
        """测试空内容列表的处理"""
        scraper = Scraper(sspai_rss_hub_config)
        scraper.active_content_processor = {"mock_processor": lambda x: x}

        result = scraper._content_process([])
        assert result == []

    def test_config_with_processors(self):
        """测试带处理器配置的初始化"""
        config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://example.com",
                "route": "/test",
                "fetch_params": {},
            },
            "content_processor_configs": {"llm": {"test": "config"}},
        }

        mock_processor_class = Mock()
        mock_processor_instance = Mock()
        mock_processor_class.return_value = mock_processor_instance

        with patch(
            "octopus_scraper.scrapers.scraper.AVALIABLE_PROCESSOR",
            {"llm": mock_processor_class},
        ):
            scraper = Scraper(config)

            # Verify processor was initialized
            mock_processor_class.assert_called_once_with({"test": "config"})
            assert "llm" in scraper.active_content_processor
            assert scraper.active_content_processor["llm"] == mock_processor_instance
