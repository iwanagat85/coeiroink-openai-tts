"""COEIROINKのWAVを、要求された音声形式に変換する"""

import subprocess

from coeiroink_openai_tts.errors import (
    ConversionError,
    ConversionTimeoutError,
    InvalidRequestError,
)
from coeiroink_openai_tts.ffmpeg import ffmpeg_executable

# 形式ごとのffmpegの出力引数と、応答のContent-Type
CODECS: dict[str, tuple[tuple[str, ...], str]] = {
    "mp3": (("-codec:a", "libmp3lame", "-b:a", "192k", "-f", "mp3"), "audio/mpeg"),
    "opus": (("-codec:a", "libopus", "-b:a", "96k", "-f", "opus"), "audio/ogg"),
    "aac": (("-codec:a", "aac", "-b:a", "192k", "-f", "adts"), "audio/aac"),
    "flac": (("-codec:a", "flac", "-f", "flac"), "audio/flac"),
    "pcm": (("-ar", "24000", "-ac", "1", "-f", "s16le"), "application/octet-stream"),
}
# OpenAPIも、実際の応答と同じ形式一覧を参照
MEDIA_TYPES = {"wav": "audio/wav", **{fmt: media_type for fmt, (_, media_type) in CODECS.items()}}
SUPPORTED_FORMATS = frozenset(MEDIA_TYPES)
CONVERSION_TIMEOUT_SECONDS = 60
# ログに残すffmpegのエラー出力の最大文字数
STDERR_LOG_LIMIT = 500


def validate_format(fmt: str) -> None:
    if fmt not in SUPPORTED_FORMATS:
        raise InvalidRequestError(f"Unsupported response_format: {fmt}", param="response_format")


def encode_audio(wav: bytes, fmt: str) -> tuple[bytes, str]:
    """WAVを指定の形式に変換し、音声データとContent-Typeを返す。

    変換できない場合はConversionError、時間内に終わらない場合は
    ConversionTimeoutErrorを送出する。
    """
    validate_format(fmt)
    # WAVは再圧縮せず、同梱ffmpegの検索や起動も行わない
    if fmt == "wav":
        return wav, MEDIA_TYPES[fmt]

    args, media_type = CODECS[fmt]
    try:
        command = [
            ffmpeg_executable(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            *args,
            "pipe:1",
        ]
        # 引数を配列で渡してシェルを介さずに起動し、入力をコマンドとして解釈させない
        result = subprocess.run(
            command,
            input=wav,
            capture_output=True,
            check=False,
            timeout=CONVERSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.runが子プロセスを終了・回収した後に投げる
        raise ConversionTimeoutError("Audio conversion timed out") from exc
    except (RuntimeError, FileNotFoundError) as exc:
        raise ConversionError(
            "Bundled audio converter is unavailable", log_detail=str(exc)
        ) from exc
    except OSError as exc:
        raise ConversionError("Could not start ffmpeg", log_detail=str(exc)) from exc

    if result.returncode != 0 or not result.stdout:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConversionError(
            "ffmpeg failed to encode audio",
            log_detail=(
                f"exit code {result.returncode}: {stderr[-STDERR_LOG_LIMIT:] or 'no error output'}"
            ),
        )
    return result.stdout, media_type
