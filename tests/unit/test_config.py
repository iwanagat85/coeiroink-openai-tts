"""環境変数の既定値と、秘密情報を変形せず扱うことを検証する"""

import pytest

from coeiroink_openai_tts.config import Settings

ENVIRONMENT = ("COEIROINK_URL", "API_KEY", "DEFAULT_VOICE", "CORS_ORIGINS")


def test_defaults_do_not_depend_on_external_environment(monkeypatch):
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env() == Settings()
    assert Settings().cors_origins == ()


def test_custom_environment_preserves_literal_key(monkeypatch):
    monkeypatch.setenv("COEIROINK_URL", "http://localhost:50032/")
    monkeypatch.setenv("API_KEY", "test-$-#-key")
    monkeypatch.setenv("DEFAULT_VOICE", "speaker-b:1")
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:3000/ ,, https://app.test ")
    assert Settings.from_env() == Settings(
        coeiroink_url="http://localhost:50032",
        api_key="test-$-#-key",
        default_voice="speaker-b:1",
        cors_origins=("http://localhost:3000", "https://app.test"),
    )


@pytest.mark.parametrize("value", [None, ""])
def test_empty_or_missing_key_falls_back_to_local(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", value)
    assert Settings.from_env().api_key == "local"


def test_empty_environment_uses_compose_defaults(monkeypatch):
    for name in ENVIRONMENT:
        monkeypatch.setenv(name, "")
    assert Settings.from_env() == Settings()


def test_settings_repr_does_not_expose_api_key():
    assert "private-test-key" not in repr(Settings(api_key="private-test-key"))
