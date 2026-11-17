"""PATHにffmpegがない環境で、同梱版による各形式の変換とデコードを検証する"""

import shutil
import subprocess
from pathlib import Path

import pytest

from coeiroink_openai_tts.audio import encode_audio
from coeiroink_openai_tts.ffmpeg import ffmpeg_executable
from scripts.smoke_test import decode_audio
from tests.support import AUTH


@pytest.fixture(autouse=True)
def without_system_ffmpeg(monkeypatch):
    monkeypatch.setenv("PATH", "")
    # 他のアプリ向けの設定にも影響されないことを確認
    monkeypatch.setenv("IMAGEIO_FFMPEG_EXE", "unavailable-external-ffmpeg")
    assert shutil.which("ffmpeg") is None


@pytest.mark.parametrize(
    "fmt, media_type",
    [
        ("wav", "audio/wav"),
        ("mp3", "audio/mpeg"),
        ("opus", "audio/ogg"),
        ("aac", "audio/aac"),
        ("flac", "audio/flac"),
        ("pcm", "application/octet-stream"),
    ],
)
def test_all_formats_decode_with_bundled_ffmpeg(wav_bytes, fmt, media_type):
    executable = Path(ffmpeg_executable())
    assert executable.is_absolute() and executable.is_file()
    audio, actual_type = encode_audio(wav_bytes, fmt)
    assert actual_type == media_type
    assert audio
    # 生PCMだけはヘッダーがないので、入力側にも24kHz/モノラル/16bitを指定
    input_args = (
        ["-f", "s16le", "-ar", "24000", "-ac", "1"]
        if fmt == "pcm"
        else ["-f", "ogg" if fmt == "opus" else fmt]
    )
    result = subprocess.run(
        [str(executable), "-v", "error", *input_args, "-i", "pipe:0", "-f", "s16le", "pipe:1"],
        input=audio,
        capture_output=True,
        check=True,
        timeout=20,
    )
    assert result.stdout
    if fmt == "pcm":
        assert len(audio) == 2400 * 2  # 0.1sec x 24,000Hz x 16bit
    assert decode_audio(audio, fmt) == len(result.stdout)


def test_default_mp3_response_without_system_ffmpeg(client):
    response = client.post("/v1/audio/speech", headers=AUTH, json={"input": "テスト"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    assert decode_audio(response.content, "mp3") > 0
