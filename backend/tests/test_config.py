from tsunami.config import Settings


class TestSettings:
    def test_default_settings(self):
        settings = Settings()
        assert settings.database_url.endswith("tsunami.db")
        assert settings.data_dir.endswith("data")
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_results_dir_under_data(self):
        settings = Settings()
        assert "results" in settings.results_dir
