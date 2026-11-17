"""認証、入力検査、話者選択、CORS、合成リクエストの互換性を検証する"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from coeiroink_openai_tts.api import create_app
from coeiroink_openai_tts.config import Settings
from tests.support import AUTH, SPEAKERS_PATH, post_speech


def preflight(client, origin):
    return client.options(
        "/v1/audio/speech",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


@pytest.mark.parametrize("path", ["/v1/models", "/v1/voices", "/v1/audio/speech"])
@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic test-key", "Bearer"])
def test_auth_required_before_upstream_work(client, upstream, path, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    if path.endswith("speech"):
        response = client.post(path, headers=headers, json={"input": "テスト"})
    else:
        response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "invalid_api_key"
    assert not upstream.requests


def test_models_accepts_case_insensitive_bearer_without_upstream(client, upstream):
    response = client.get("/v1/models", headers={"Authorization": "bearer test-key"})
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "coeiroink"
    assert not upstream.requests


def test_health_is_public_and_checks_upstream(client, upstream):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "speakers": 2}
    assert upstream.requests[0].url.path == SPEAKERS_PATH


def test_voice_list_preserves_ids_and_names(client):
    response = client.get("/v1/voices", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "id": "speaker-a:10",
                "name": "話者A/通常",
                "speaker_uuid": "speaker-a",
                "style_id": 10,
            },
            {
                "id": "speaker-a:20",
                "name": "話者A/元気",
                "speaker_uuid": "speaker-a",
                "style_id": 20,
            },
            {
                "id": "speaker-b:3",
                "name": "話者B/通常",
                "speaker_uuid": "speaker-b",
                "style_id": 3,
            },
        ],
    }


def test_synthesis_preserves_request_flow_and_parameters(client, upstream, wav_bytes):
    # 前後の空白もそのままCOEIROINKへ渡せるかテストする
    response = post_speech(
        client, input=" こんにちは。 ", voice="speaker-b:3", speed=1.5, instructions="ignored"
    )
    assert response.status_code == 200
    assert response.content == wav_bytes
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert [(r.method, r.url.path) for r in upstream.requests] == [
        ("GET", SPEAKERS_PATH),
        ("POST", "/v1/estimate_prosody"),
        ("POST", "/v1/synthesis"),
    ]
    assert json.loads(upstream.requests[1].content) == {"text": " こんにちは。 "}
    assert json.loads(upstream.requests[2].content) == {
        "speakerUuid": "speaker-b",
        "styleId": 3,
        "text": " こんにちは。 ",
        "prosodyDetail": upstream.prosody["detail"],
        "volumeScale": 1.0,
        "pitchScale": 0.0,
        "intonationScale": 1.0,
        "prePhonemeLength": 0.1,
        "postPhonemeLength": 0.1,
        "outputSamplingRate": 44100,
        "speedScale": 1.5,
    }


def synthesized_voice(upstream):
    payload = json.loads(upstream.requests[-1].content)
    return payload["speakerUuid"], payload["styleId"]


@pytest.mark.parametrize("voice", [None, "auto", "default", ""])
@pytest.mark.parametrize(
    "default_voice, expected",
    [
        ("auto", ("speaker-b", 3)),
        ("default", ("speaker-b", 3)),
        ("", ("speaker-b", 3)),
        ("speaker-a:20", ("speaker-a", 20)),
        ("20", ("speaker-a", 20)),
    ],
)
def test_default_selection_uses_override_or_smallest_style_id(
    client_factory, upstream, voice, default_voice, expected
):
    # voiceがNoneの場合は、項目そのものを省略する
    overrides = {} if voice is None else {"voice": voice}
    response = post_speech(client_factory(default_voice=default_voice), **overrides)
    assert response.status_code == 200
    assert synthesized_voice(upstream) == expected


def test_explicit_voice_ignores_default_voice(client_factory, upstream):
    response = post_speech(client_factory(default_voice="speaker-a:20"), voice="speaker-b:3")
    assert response.status_code == 200
    assert synthesized_voice(upstream) == ("speaker-b", 3)


@pytest.mark.parametrize("voice", ["20", "020"])
def test_numeric_voice_uses_style_id(client, upstream, voice):
    assert post_speech(client, voice=voice).status_code == 200
    assert synthesized_voice(upstream) == ("speaker-a", 20)


@pytest.mark.parametrize(
    "voice, expected",
    [("話者A/元気", ("speaker-a", 20)), ("話者B/通常", ("speaker-b", 3))],
)
def test_display_name_selects_voice(client, upstream, voice, expected):
    assert post_speech(client, voice=voice).status_code == 200
    assert synthesized_voice(upstream) == expected


@pytest.mark.parametrize(
    "voice",
    [
        "alloy",
        "話者A",
        "話者A / 元気",
        "話者A/げんき",
        "nova",
        "missing",
        "AUTO",
        " auto",
        "1",
        "speaker-a",
        "speaker-a:3",
        "speaker-a:x",
        ":10",
        "9" * 5000,
    ],
)
def test_unknown_voice_returns_400_without_fallback(client, upstream, voice):
    response = post_speech(client, voice=voice)
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": f"Unknown voice: {voice}. See GET /v1/voices",
            "type": "invalid_request_error",
            "param": "voice",
            "code": None,
        }
    }
    assert [r.url.path for r in upstream.requests] == [SPEAKERS_PATH]


def test_null_voice_is_rejected_before_upstream(client, upstream):
    response = post_speech(client, voice=None)
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "voice"
    assert not upstream.requests


def test_inventory_changes_apply_without_restart(client, upstream):
    assert post_speech(client, voice="speaker-c:0").status_code == 400
    upstream.speakers.append(
        {"speakerUuid": "speaker-c", "speakerName": "話者C", "styles": [{"styleId": 0}]}
    )
    voices = client.get("/v1/voices", headers=AUTH).json()["data"]
    assert "speaker-c:0" in [voice["id"] for voice in voices]
    assert post_speech(client, voice="speaker-c:0").status_code == 200
    assert post_speech(client).status_code == 200
    assert synthesized_voice(upstream) == ("speaker-c", 0)


@pytest.mark.parametrize("speakers", [[], [{"speakerUuid": "empty", "styles": []}]])
def test_no_installed_styles_returns_503(client, upstream, speakers):
    upstream.speakers = speakers
    assert client.get("/v1/voices", headers=AUTH).json()["data"] == []
    upstream.requests.clear()
    assert post_speech(client).status_code == 503
    assert len(upstream.requests) == 1


@pytest.mark.parametrize(
    "override, param",
    [
        ({"model": "tts-1"}, "model"),
        ({"response_format": "invalid"}, "response_format"),
        ({"stream_format": "sse"}, "stream_format"),
        ({"input": ""}, "input"),
        ({"input": " \n\t　"}, "input"),
        ({"input": "あ" * 4097}, "input"),
        ({"input": 123}, "input"),
        ({"speed": 0.24}, "speed"),
        ({"speed": 4.01}, "speed"),
    ],
)
def test_invalid_request_never_calls_upstream(client, upstream, override, param):
    response = post_speech(client, **override)
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["param"] == param
    assert not upstream.requests


@pytest.mark.parametrize("speed", [0.25, 4.0])
def test_speed_boundaries_and_buffered_audio_stream_format(client, speed):
    assert post_speech(client, speed=speed, stream_format="audio").status_code == 200


def test_input_at_length_limit_is_accepted(client, upstream):
    assert post_speech(client, input="あ" * 4096).status_code == 200
    assert json.loads(upstream.requests[1].content) == {"text": "あ" * 4096}


def test_empty_key_keeps_authentication_enabled(client_factory):
    client = client_factory(api_key="")
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer local"}).status_code == 200


@pytest.mark.parametrize("api_key, warned", [("", True), ("local", True), ("test-key", False)])
def test_default_key_is_reported_at_startup(client_factory, caplog, api_key, warned):
    client_factory(api_key=api_key)
    assert ("API_KEY" in caplog.text) is warned


def test_cors_is_disabled_by_default(client, upstream):
    response = preflight(client, "http://localhost:3000")
    assert "access-control-allow-origin" not in response.headers
    response = client.get("/v1/models", headers={**AUTH, "Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert not upstream.requests


def test_configured_origin_passes_preflight_without_authentication(client_factory, upstream):
    client = client_factory(cors_origins=("http://localhost:3000",))
    response = preflight(client, "http://localhost:3000")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    # 許可していないオリジンでは応答が返ってこない
    response = preflight(client, "http://untrusted.test")
    assert "access-control-allow-origin" not in response.headers
    assert not upstream.requests


def test_apps_keep_separate_settings_and_close_http_clients(upstream):
    first = create_app(Settings(api_key="first"), transport=httpx.MockTransport(upstream))
    second = create_app(Settings(api_key="second"), transport=httpx.MockTransport(upstream))
    with TestClient(first) as one, TestClient(second) as two:
        header = {"Authorization": "Bearer first"}
        assert one.get("/v1/models", headers=header).status_code == 200
        assert two.get("/v1/models", headers=header).status_code == 401
        assert not first.state.coeiroink.http.is_closed
    assert first.state.coeiroink.http.is_closed
    assert second.state.coeiroink.http.is_closed
