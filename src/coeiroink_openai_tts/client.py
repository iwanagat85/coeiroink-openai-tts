"""COEIROINKとの通信と応答検証を、HTTPの受付処理から分離する"""

from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from coeiroink_openai_tts.errors import UpstreamError
from coeiroink_openai_tts.models import Prosody, Speaker, Style
from coeiroink_openai_tts.wav import validate_wav

SPEAKERS_ADAPTER = TypeAdapter(list[Speaker])
PROSODY_ADAPTER = TypeAdapter(Prosody)
SPEAKERS_PATH = "/v1/speakers_path_variant"
# 話速以外の音量・抑揚などは固定値とし、クライアントからは変更できない。
SYNTHESIS_PARAMETERS = {
    "volumeScale": 1.0,
    "pitchScale": 0.0,
    "intonationScale": 1.0,
    "prePhonemeLength": 0.1,
    "postPhonemeLength": 0.1,
    "outputSamplingRate": 44100,
}


def describe_exception(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def describe_validation_error(exc: ValidationError) -> str:
    """ログ用に、入力値を含めずに検証エラーを要約する。"""
    # 韻律の応答などには読み上げる文章が含まれ得るため、位置と理由だけを残す
    first = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = ".".join(str(part) for part in first["loc"]) or "response"
    return f"{exc.error_count()} validation error(s); first at {location}: {first['msg']}"


class CoeiroinkClient:
    """COEIROINKのHTTP APIを呼び、このアダプターが使う項目だけを検証して返す。"""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.http.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.RequestError as exc:
            # 例外の内容は接続先の情報を含み得るので、ログにだけ残す
            raise UpstreamError(
                f"COEIROINK connection failed for {path}", log_detail=describe_exception(exc)
            ) from exc
        except httpx.HTTPStatusError as exc:
            # 上流の応答本文は、クライアントにもログにも出さない
            raise UpstreamError(
                f"COEIROINK {path} returned HTTP {exc.response.status_code}"
            ) from exc

    @staticmethod
    def _parse[T](response: httpx.Response, adapter: TypeAdapter[T], name: str) -> T:
        """JSONの応答を検証し、想定外の内容は上流のエラーとして扱う"""
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"COEIROINK {response.request.url.path} returned invalid JSON",
                log_detail=describe_exception(exc),
            ) from exc
        try:
            return adapter.validate_python(data)
        except ValidationError as exc:
            raise UpstreamError(
                f"Unexpected COEIROINK {name} response", log_detail=describe_validation_error(exc)
            ) from exc

    async def speakers(self) -> list[Speaker]:
        response = await self._request("GET", SPEAKERS_PATH)
        # 欠けたUUIDや不正なスタイルをここで検出し、後段のKeyErrorを防ぐ
        return self._parse(response, SPEAKERS_ADAPTER, "speakers")

    async def synthesize(self, text: str, speaker: Speaker, style: Style, speed: float) -> bytes:
        response = await self._request("POST", "/v1/estimate_prosody", json={"text": text})
        prosody = self._parse(response, PROSODY_ADAPTER, "prosody")

        # 推定した韻律を加工せずに渡し、話速だけをクライアントの指定に合わせる
        payload = {
            "speakerUuid": speaker.speaker_uuid,
            "styleId": style.style_id,
            "text": text,
            "prosodyDetail": prosody.detail,
            **SYNTHESIS_PARAMETERS,
            "speedScale": speed,
        }
        response = await self._request("POST", "/v1/synthesis", json=payload)
        wav = response.content
        # WAVをそのまま返す場合も、空の音声や途中で切れたチャンクを成功にしない
        try:
            validate_wav(wav)
        except ValueError as exc:
            raise UpstreamError(
                "COEIROINK synthesis did not return valid WAV audio",
                log_detail=(
                    f"{exc}; {len(wav)} bytes, content-type: {response.headers.get('content-type')}"
                ),
            ) from exc
        return wav
