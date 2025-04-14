import pytest

from octopus_scraper.scrapers.utils.direct_rss import DirectRSS


class TestRssHub:
    @pytest.fixture
    def owenyoung_rsshub(self):
        """Fixture to create a mock RssHub instance."""
        config = {
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
        }
        return DirectRSS(config)

    @pytest.mark.need_external_service
    def test_fetch_owen_contents(self, owenyoung_rsshub):
        contents = owenyoung_rsshub.fetch_contents()
        assert len(contents) > 0

    @pytest.mark.need_external_service
    def test_fetch_own_contents_with_filter_time(self, owenyoung_rsshub):
        contents = owenyoung_rsshub.fetch_contents()
        total_cnt = len(contents)
        contents = owenyoung_rsshub.fetch_contents(
            params={"filter_time": 60 * 60 * 24 * 60}
        )
        assert len(contents) < total_cnt and len(contents) > 0
