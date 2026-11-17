"""音声変換の失敗が、呼び出し元へ適切なHTTPエラーとして届くことをテストする"""

import subprocess

import pytest

from tests.support import post_speech


@pytest.fixture
def ffmpeg_outcome(monkeypatch):
    def replace(outcome):
        def run(*args, **kwargs):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr("coeiroink_openai_tts.audio.ffmpeg_executable", lambda: "ffmpeg")
        monkeypatch.setattr("coeiroink_openai_tts.audio.subprocess.run", run)

    return replace


@pytest.mark.parametrize(
    "failure, status",
    [
        (FileNotFoundError(), 500),
        (PermissionError(), 500),
        (subprocess.TimeoutExpired("ffmpeg", 60), 504),
        (subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"private details"), 500),
        (subprocess.CompletedProcess([], 0, stdout=b"", stderr=b""), 500),
    ],
)
def test_conversion_errors_reach_api(client, ffmpeg_outcome, failure, status):
    ffmpeg_outcome(failure)
    response = post_speech(client, response_format="mp3")
    assert response.status_code == status
    assert response.json()["error"]["type"] == "server_error"
    assert "private" not in response.text


def test_ffmpeg_error_output_is_logged_but_not_returned(client, ffmpeg_outcome, caplog):
    ffmpeg_outcome(subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"private encoder detail"))
    response = post_speech(client, response_format="mp3")
    assert "private" not in response.text
    assert "exit code 1: private encoder detail" in caplog.text


def test_missing_bundle_reaches_api_without_starting_process(client, monkeypatch, caplog):
    def missing():
        raise RuntimeError("private installation details")

    def unexpected_call(*args, **kwargs):
        pytest.fail("Missing bundle must not start a process")

    monkeypatch.setattr("coeiroink_openai_tts.audio.ffmpeg_executable", missing)
    monkeypatch.setattr("coeiroink_openai_tts.audio.subprocess.run", unexpected_call)
    response = post_speech(client, response_format="mp3")
    assert response.status_code == 500
    assert response.json()["error"]["message"] == "Bundled audio converter is unavailable"
    assert "private installation details" in caplog.text
