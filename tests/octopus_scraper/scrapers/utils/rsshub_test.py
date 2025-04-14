import pytest

from octopus_scraper.scrapers.utils.rsshub import RssHub


class TestRssHub:
    @pytest.fixture
    def sspai_rsshub(self):
        """Fixture to create a mock RssHub instance."""
        config = {
            "hub_root": "https://rsshub.thzu.xyz",
            "route": "/sspai/matrix",
            "fetch_params": {"limit": 1},
        }
        return RssHub(config)

    @pytest.mark.need_external_service
    def test_fetch_sspai_matrix_contents(self, sspai_rsshub):
        contents = sspai_rsshub.fetch_contents()
        assert len(contents) == 1
