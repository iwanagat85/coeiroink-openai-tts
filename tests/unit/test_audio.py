"""ffmpegを起動せずに確認できる、音声形式の選択とWAVの取り扱いを検証する"""

import pytest

from coeiroink_openai_tts.audio import encode_audio
from coeiroink_openai_tts.errors import InvalidRequestError


def test_wav_does_not_launch_ffmpeg(monkeypatch, wav_bytes):
    def unexpected_call(*args, **kwargs):
        pytest.fail("WAV output must not invoke ffmpeg")

    monkeypatch.setattr("coeiroink_openai_tts.audio.subprocess.run", unexpected_call)
    monkeypatch.setattr("coeiroink_openai_tts.audio.ffmpeg_executable", unexpected_call)
    assert encode_audio(wav_bytes, "wav") == (wav_bytes, "audio/wav")


def test_unsupported_format_is_rejected(wav_bytes):
    with pytest.raises(InvalidRequestError) as error:
        encode_audio(wav_bytes, "invalid")
    assert error.value.status_code == 400
    assert error.value.param == "response_format"
