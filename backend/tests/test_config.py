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

    def test_public_api_url_defaults_to_internal(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TSUNAMI_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("TSUNAMI_PUBLIC_API_URL", raising=False)
        monkeypatch.delenv("TSUNAMI_INTERNAL_API_URL", raising=False)
        s = Settings()
        assert s.internal_api_url == "http://localhost:8000"
        assert s.public_api_url == s.internal_api_url

    def test_public_api_url_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TSUNAMI_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("TSUNAMI_PUBLIC_API_URL", "http://localhost:8001")
        s = Settings()
        assert s.public_api_url == "http://localhost:8001"
        assert s.internal_api_url == "http://localhost:8000"
