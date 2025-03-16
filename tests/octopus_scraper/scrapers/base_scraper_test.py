import pytest

from octopus_scraper.scrapers.base_scraper import Scraper, Content


@pytest.fixture
def sspai_rss_hub_config():
    config = {
        "fetcher_name": "rsshub",
        "fecher_config": {
            "hub_root": "https://rsshub.thzu.xyz",
            "route": "/sspai/matrix",
            "fetch_params": {"limit": 3},
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
                title="Original Article",
                link="http://original.com",
                summary="Original summary",
            )
        ]
        scraper.active_content_processor = {"mock_processor": lambda x: x}
        processed_contents = scraper._content_process(fetched_contents)

        assert len(processed_contents) == 1
        assert processed_contents[0].title == "Processed Article"
        assert processed_contents[0].link == "http://processed.com"
        assert processed_contents[0].summary == "Processed summary"
