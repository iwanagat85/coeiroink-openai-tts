"""COEIROINKの異常を、クライアントが判断できるHTTPエラーに変換できることをテストする"""

import json
import struct

import httpx
import pytest

from tests.support import SPEAKERS_PATH, post_speech


@pytest.mark.parametrize("endpoint", [SPEAKERS_PATH, "/v1/estimate_prosody", "/v1/synthesis"])
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("private connection detail"),
        httpx.ReadTimeout("private timeout detail"),
        httpx.Response(500, text="private upstream detail"),
        httpx.Response(302, headers={"Location": "http://unrelated.test"}),
    ],
)
def test_upstream_errors_return_502_without_leaking_body(client, upstream, endpoint, failure):
    upstream.overrides[endpoint] = failure
    response = post_speech(client)
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "server_error"
    assert "private" not in response.text
    assert upstream.requests[-1].url.path == endpoint


@pytest.mark.parametrize("status", [400, 404, 422])
@pytest.mark.parametrize(
    "voice, expected", [("speaker-a:20", ("speaker-a", 20)), ("auto", ("speaker-b", 3))]
)
def test_synthesis_rejection_keeps_502_without_retrying_another_voice(
    client, upstream, status, voice, expected
):
    # OpenAPI互換にするため、COEIROINKの4xx系の拒否を502にまとめる
    upstream.overrides["/v1/synthesis"] = httpx.Response(status, json={"detail": "private"})
    response = post_speech(client, voice=voice)
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "server_error"
    assert "private" not in response.text
    synthesis = [r for r in upstream.requests if r.url.path == "/v1/synthesis"]
    assert len(synthesis) == 1
    payload = json.loads(synthesis[0].content)
    assert (payload["speakerUuid"], payload["styleId"]) == expected


def test_connection_failure_cause_is_logged_but_not_returned(client, upstream, caplog):
    upstream.overrides[SPEAKERS_PATH] = httpx.ConnectError("private connection detail")
    response = post_speech(client)
    assert "private" not in response.text
    assert "ConnectError: private connection detail" in caplog.text


def test_upstream_response_body_is_not_logged(client, upstream, caplog):
    upstream.overrides["/v1/synthesis"] = httpx.Response(500, text="private upstream detail")
    post_speech(client)
    assert "returned HTTP 500" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.parametrize("endpoint", [SPEAKERS_PATH, "/v1/estimate_prosody"])
def test_invalid_json_returns_502(client, upstream, endpoint):
    upstream.overrides[endpoint] = httpx.Response(200, text="<html>not JSON</html>")
    assert post_speech(client).status_code == 502
    assert upstream.requests[-1].url.path == endpoint


@pytest.mark.parametrize(
    "data",
    [
        {},
        None,
        [None],
        [{"styles": []}],
        [{"speakerUuid": "a", "styles": None}],
        [{"speakerUuid": "a", "styles": [{}]}],
        [{"speakerUuid": "a", "styles": [{"styleId": True}]}],
    ],
)
def test_malformed_speakers_return_502(client, upstream, data):
    upstream.speakers = data
    assert post_speech(client).status_code == 502
    assert len(upstream.requests) == 1


@pytest.mark.parametrize(
    "data",
    [{}, None, [], {"detail": None}, {"detail": "bad"}, {"detail": [1]}, {"detail": [{}]}],
)
def test_malformed_prosody_stops_before_synthesis(client, upstream, data):
    upstream.prosody = data
    assert post_speech(client).status_code == 502
    assert len(upstream.requests) == 2


def test_validation_log_omits_upstream_values(client, upstream, caplog):
    # 韻律の応答には読み上げる文章が含まれる可能性があるからログに位置と理由だけ残す
    upstream.prosody = {"detail": [["private-reading-text"]]}
    assert post_speech(client, input="private-reading-text").status_code == 502
    assert "validation error" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.parametrize("audio", [b"", b"{}", b"<html>error</html>"])
def test_non_wav_synthesis_response_returns_502(client, upstream, audio):
    upstream.wav = audio
    assert post_speech(client).status_code == 502


@pytest.mark.parametrize("response_format", ["wav", "mp3"])
@pytest.mark.parametrize(
    "damage",
    [
        "header_only",
        "missing_fmt",
        "missing_data",
        "truncated_data",
        "truncated_chunk",
        "empty_data",
        "partial_frame",
        "invalid_format",
    ],
)
def test_corrupt_wav_is_rejected_before_conversion(
    client, upstream, wav_bytes, monkeypatch, response_format, damage
):
    def unexpected_conversion(*args, **kwargs):
        raise AssertionError("Corrupt upstream WAV must not reach audio conversion")

    monkeypatch.setattr("coeiroink_openai_tts.api.encode_audio", unexpected_conversion)
    if damage == "header_only":
        broken = wav_bytes[:12]
    elif damage == "missing_fmt":
        broken = wav_bytes[:12] + wav_bytes[36:]
    elif damage == "missing_data":
        broken = wav_bytes[:36]
    elif damage == "truncated_data":
        broken = wav_bytes[:-2]
    elif damage == "truncated_chunk":
        broken = wav_bytes + b"bad"
    elif damage == "empty_data":
        broken = wav_bytes[:40] + struct.pack("<I", 0)
    elif damage == "partial_frame":
        broken = wav_bytes[:40] + struct.pack("<I", len(wav_bytes) - 45) + wav_bytes[44:-1]
    else:
        broken = wav_bytes[:32] + b"\x00\x00" + wav_bytes[34:]
    # RIFF全体の長さを合わせても内部チャンクの破損を検出できることを確認
    upstream.wav = broken[:4] + struct.pack("<I", len(broken) - 8) + broken[8:]
    response = post_speech(client, response_format=response_format)
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "server_error"


def test_wav_with_incorrect_riff_length_returns_502(client, upstream, wav_bytes):
    upstream.wav = wav_bytes + b"unexpected trailing bytes"
    assert post_speech(client).status_code == 502


def test_float_wav_with_metadata_is_preserved(client, upstream):
    # PCM専用のwaveモジュールでは読めない浮動小数点WAVと奇数長の補助チャンク
    fmt = struct.pack("<HHIIHH", 3, 1, 44100, 176400, 4, 32)
    samples = struct.pack("<ff", 0.0, 0.25)
    chunks = (
        b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"JUNK"
        + struct.pack("<I", 3)
        + b"abc\x00"
        + b"data"
        + struct.pack("<I", len(samples))
        + samples
    )
    upstream.wav = b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks
    response = post_speech(client)
    assert response.status_code == 200
    assert response.content == upstream.wav


def test_health_reports_unreachable_upstream(client, upstream):
    upstream.overrides[SPEAKERS_PATH] = httpx.ConnectError("unavailable")
    assert client.get("/health").status_code == 502
