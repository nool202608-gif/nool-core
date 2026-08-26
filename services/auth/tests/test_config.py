from src.config.settings import AuthSettings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("FIREBASE_WEB_API_KEY", raising=False)

    settings = AuthSettings()

    assert settings.service_name == "auth"
    assert settings.environment == "development"
    assert settings.firebase_project_id is None
    assert settings.firebase_credentials_path is None
    assert settings.firebase_web_api_key is None


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-project")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = AuthSettings()

    assert settings.firebase_project_id == "demo-project"
    assert settings.log_level == "DEBUG"
