"""実際のCOEIROINKを使い、APIの認証と音声生成・デコードを確認する"""

import argparse
import secrets
import subprocess

import httpx
from fastapi.testclient import TestClient

from coeiroink_openai_tts.api import create_app
from coeiroink_openai_tts.audio import SUPPORTED_FORMATS
from coeiroink_openai_tts.config import Settings
from coeiroink_openai_tts.ffmpeg import ffmpeg_executable

MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "pcm": "application/octet-stream",
}


def require_status(response: httpx.Response, expected: int) -> None:
    if response.status_code != expected:
        # 秘密情報や読み上げ内容を出力しないよう、応答本文は表示しない
        raise RuntimeError(
            f"{response.request.url.path}: expected HTTP {expected}, got {response.status_code}"
        )


def decode_audio(audio: bytes, fmt: str) -> int:
    # デコードだけを行い、ファイル保存やスピーカーでの再生はしない
    input_args = ["-f", "s16le", "-ar", "24000", "-ac", "1"] if fmt == "pcm" else []
    result = subprocess.run(
        [ffmpeg_executable(), "-v", "error", *input_args, "-i", "pipe:0", "-f", "s16le", "pipe:1"],
        input=audio,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"{fmt}: generated audio could not be decoded")
    return len(result.stdout)


def verify(client: httpx.Client | TestClient, api_key: str, formats: list[str]) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    health = client.get("/health")
    require_status(health, 200)
    print(f"health: ok, speakers={health.json()['speakers']}")

    # 認証なし・誤ったキー・正しいキーを分けて確認
    for path in ("/v1/models", "/v1/voices", "/v1/audio/speech"):
        method = "POST" if path.endswith("speech") else "GET"
        body = {"json": {"input": "認証テスト"}} if method == "POST" else {}
        require_status(client.request(method, path, **body), 401)
        wrong = {"Authorization": f"Bearer {api_key}{secrets.token_hex(8)}"}
        require_status(client.request(method, path, headers=wrong, **body), 401)

    models = client.get("/v1/models", headers=headers)
    require_status(models, 200)
    if models.json()["data"][0]["id"] != "coeiroink":
        raise RuntimeError("Unexpected model identifier")
    voices = client.get("/v1/voices", headers=headers)
    require_status(voices, 200)
    if not voices.json()["data"]:
        raise RuntimeError("No voices available for synthesis")
    print(f"authentication: ok, voices={len(voices.json()['data'])}")

    for fmt in formats:
        response = client.post(
            "/v1/audio/speech",
            headers=headers,
            json={"input": "こんにちは、テスト音声です。", "voice": "auto", "response_format": fmt},
        )
        require_status(response, 200)
        if response.headers.get("content-type") != MEDIA_TYPES[fmt]:
            raise RuntimeError(f"{fmt}: unexpected Content-Type")
        if response.headers.get("cache-control") != "no-store":
            raise RuntimeError(f"{fmt}: missing Cache-Control")
        decoded_size = decode_audio(response.content, fmt)
        print(f"{fmt}: ok, encoded={len(response.content)} bytes, decoded={decoded_size} bytes")


def main() -> None:
    # ソースの説明は日本語、コマンド実行時に表示する案内は英語で管理
    parser = argparse.ArgumentParser(
        description="Check authentication and audio generation against a real COEIROINK service."
    )
    parser.add_argument("--base-url", default="http://localhost:50033")
    parser.add_argument(
        "--in-process", action="store_true", help="Check the app without a running adapter server"
    )
    parser.add_argument(
        "--formats", nargs="+", choices=sorted(SUPPORTED_FORMATS), default=["wav", "mp3"]
    )
    args = parser.parse_args()
    settings = Settings.from_env()

    # 一時コンテナではアプリを直接呼び、既存サーバーのポートや起動状態を変えない
    client = (
        TestClient(create_app(settings))
        if args.in_process
        else httpx.Client(base_url=args.base_url, timeout=180)
    )
    with client:
        verify(client, settings.api_key, args.formats)


if __name__ == "__main__":
    main()
