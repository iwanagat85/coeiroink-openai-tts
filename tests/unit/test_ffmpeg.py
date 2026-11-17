"""同梱バイナリがない場合も、環境のffmpegへ切り替わらないことを検証する"""

import pytest

from coeiroink_openai_tts.ffmpeg import ffmpeg_executable


@pytest.mark.parametrize("binaries", [[], ["ffmpeg-one.exe", "ffmpeg-two.exe"]])
def test_missing_or_ambiguous_bundle_is_rejected(monkeypatch, tmp_path, binaries):
    for name in binaries:
        (tmp_path / name).touch()
    # 外部ffmpegが指定されていても、不完全なインストールはエラーとして扱う
    monkeypatch.setenv("IMAGEIO_FFMPEG_EXE", "external-ffmpeg")
    monkeypatch.setattr("coeiroink_openai_tts.ffmpeg.files", lambda package: tmp_path)
    with pytest.raises(RuntimeError, match="reinstall imageio-ffmpeg"):
        ffmpeg_executable()


def test_missing_package_has_installation_guidance(monkeypatch):
    def missing(package):
        raise ModuleNotFoundError(package)

    monkeypatch.setattr("coeiroink_openai_tts.ffmpeg.files", missing)
    with pytest.raises(RuntimeError, match="reinstall imageio-ffmpeg"):
        ffmpeg_executable()
