"""すべてのエラー応答がOpenAIと同じ形式で返せることをテストする"""

import httpx
import pytest
from fastapi.testclient import TestClient

from coeiroink_openai_tts.api import create_app
from coeiroink_openai_tts.config import Settings
from tests.support import AUTH, post_speech


def test_validation_error_uses_openai_format(client):
    response = post_speech(client, speed=9)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Invalid value for 'speed': Input should be less than or equal to 4",
            "type": "invalid_request_error",
            "param": "speed",
            "code": None,
        }
    }


def test_unreadable_json_body_returns_400(client, upstream):
    response = client.post(
        "/v1/audio/speech",
        headers={**AUTH, "Content-Type": "application/json"},
        content=b"{not json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"].startswith("Invalid request body:")
    assert response.json()["error"]["param"] is None
    assert not upstream.requests


def test_framework_errors_use_openai_format(client):
    response = client.get("/v1/unknown", headers=AUTH)
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "message": "Not Found",
            "type": "invalid_request_error",
            "param": None,
            "code": None,
        }
    }
    response = client.get("/v1/audio/speech", headers=AUTH)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert response.json()["error"]["message"] == "Method Not Allowed"


def test_openai_voice_name_uses_invalid_voice_error(client):
    response = post_speech(client, voice="alloy")
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Unknown voice: alloy. See GET /v1/voices",
            "type": "invalid_request_error",
            "param": "voice",
            "code": None,
        }
    }


@pytest.mark.parametrize("default_voice", ["missing:9", "alloy", "1"])
@pytest.mark.parametrize("voice", [None, "auto"])
def test_unmatched_default_voice_uses_invalid_voice_error(
    client_factory, upstream, default_voice, voice
):
    overrides = {} if voice is None else {"voice": voice}
    response = post_speech(client_factory(default_voice=default_voice), **overrides)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": f"Unknown voice: {default_voice} (DEFAULT_VOICE). See GET /v1/voices",
            "type": "invalid_request_error",
            "param": "voice",
            "code": None,
        }
    }
    assert len(upstream.requests) == 1


@pytest.mark.parametrize(
    "cors_origins, origin, allowed_origin",
    [
        ((), "http://localhost:3000", None),
        (("http://localhost:3000",), "http://localhost:3000", "http://localhost:3000"),
        (("http://localhost:3000",), "http://untrusted.test", None),
        (("*",), "http://localhost:3000", "*"),
    ],
)
def test_unexpected_error_uses_openai_format_and_cors(
    upstream, monkeypatch, cors_origins, origin, allowed_origin
):
    def broken(*args, **kwargs):
        raise ValueError("private failure")

    monkeypatch.setattr("coeiroink_openai_tts.api.encode_audio", broken)
    app = create_app(
        Settings(api_key="test-key", cors_origins=cors_origins),
        transport=httpx.MockTransport(upstream),
    )
    # 想定外の例外を受け取る
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/audio/speech",
            headers={**AUTH, "Origin": origin},
            json={"input": "テスト", "response_format": "wav"},
        )
    assert response.status_code == 500
    assert response.json()["error"]["message"] == "Internal server error"
    assert "private" not in response.text
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    if allowed_origin and allowed_origin != "*":
        assert "Origin" in response.headers["vary"]
