"""プラットフォーム別wheelに同梱されたffmpegだけを利用"""

from importlib.resources import files


def ffmpeg_executable() -> str:
    """同梱された実行ファイルの絶対パスを返す"""
    message = "Bundled ffmpeg is unavailable; reinstall imageio-ffmpeg from a platform wheel"
    try:
        # imageio-ffmpegの自動検出はPATHやCondaへフォールバックするため使わない
        binaries = files("imageio_ffmpeg.binaries")
        candidates = [
            path
            for path in binaries.iterdir()
            if path.name.startswith("ffmpeg-") and path.is_file()
        ]
    except (ModuleNotFoundError, OSError) as exc:
        raise RuntimeError(message) from exc
    if len(candidates) != 1:
        raise RuntimeError(message)
    return str(candidates[0])
