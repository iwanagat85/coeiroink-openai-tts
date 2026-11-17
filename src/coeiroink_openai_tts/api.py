"""COEIROINK v2をOpenAI互換の音声APIとして公開する入口"""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from coeiroink_openai_tts.audio import MEDIA_TYPES, encode_audio, validate_format
from coeiroink_openai_tts.client import CoeiroinkClient
from coeiroink_openai_tts.config import DEFAULT_API_KEY, MODEL, Settings
from coeiroink_openai_tts.errors import AdapterError, AuthenticationError, InvalidRequestError
from coeiroink_openai_tts.models import ErrorResponse, SpeechRequest
from coeiroink_openai_tts.voices import iter_voices, resolve_voice, voice_id, voice_name

logger = logging.getLogger(__name__)
LOG_FORMAT = "%(levelname)s: %(name)s: %(message)s"


def error_response(
    status_code: int,
    message: str,
    *,
    param: str | None = None,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """OpenAIのSDKやクライアントが解釈できる形式で、エラー応答を作る"""
    error_type = "invalid_request_error" if status_code < 500 else "server_error"
    return JSONResponse(
        {"error": {"message": message, "type": error_type, "param": param, "code": code}},
        status_code=status_code,
        headers=headers,
    )


async def handle_adapter_error(request: Request, exc: AdapterError) -> JSONResponse:
    if exc.status_code >= 500:
        # 原因はサーバーログにだけ残し、クライアントには要約した文言を返す
        detail = f" ({exc.log_detail})" if exc.log_detail else ""
        logger.warning("%s %s failed: %s%s", request.method, request.url.path, exc.message, detail)
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return error_response(
        exc.status_code, exc.message, param=exc.param, code=exc.code, headers=headers
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # 入力の不備は400で返し、最初に見つかった項目を伝える
    first = exc.errors()[0]
    names = [str(part) for part in first["loc"][1:] if isinstance(part, str)]
    param = ".".join(names) or None
    subject = f"Invalid value for '{param}'" if param else "Invalid request body"
    return error_response(400, f"{subject}: {first['msg']}", param=param)


async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # 存在しないパスや許可されていないメソッドなど、FastAPI自体のエラーも同じ形式にする
    return error_response(exc.status_code, str(exc.detail), headers=exc.headers)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # トレースバックはuvicornが記録するので、ここでは形式だけをそろえる
    return error_response(500, "Internal server error")


def create_app(
    settings: Settings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI | CORSMiddleware:
    """アプリごとに設定と通信接続を持ち、テストでも本番設定を変更せず使えるようにする。"""
    settings = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # uvicornは自身のロガーだけを設定するため、アプリの警告も標準エラー出力へ出す
        # ログがすでに設定されている場合、basicConfigは何もしない
        logging.basicConfig(format=LOG_FORMAT)
        if settings.api_key == DEFAULT_API_KEY:
            logger.warning("API_KEY is not set or uses the well-known default; set a unique key")
        # リクエストごとの接続作成を避け、終了時には共有接続を必ず閉じる
        async with httpx.AsyncClient(
            base_url=settings.coeiroink_url,
            timeout=httpx.Timeout(120, connect=5),
            transport=transport,
        ) as http:
            app.state.coeiroink = CoeiroinkClient(http)
            yield

    app = FastAPI(
        title="COEIROINK OpenAI TTS Adapter",
        lifespan=lifespan,
        responses={
            400: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            # 404, 405なども同じ形式
            "default": {"model": ErrorResponse, "description": "Error response"},
        },
    )
    app.add_exception_handler(AdapterError, handle_adapter_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
    bearer = HTTPBearer(
        auto_error=False,
        scheme_name="BearerAuth",
        description="API key configured for this adapter",
    )

    async def check_auth(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        # HTTPBearerで方式を検査してキーは完全一致で突き合わせる
        token = credentials.credentials if credentials else ""
        valid = secrets.compare_digest(token.encode("utf-8"), settings.api_key.encode("utf-8"))
        if credentials is None or not valid:
            raise AuthenticationError("Invalid API key")

    protected = [Depends(check_auth)]
    protected_responses = {
        401: {
            "model": ErrorResponse,
            "headers": {"WWW-Authenticate": {"schema": {"type": "string", "const": "Bearer"}}},
        },
    }

    @app.get(
        "/health",
        summary="Check COEIROINK connectivity",
        responses={502: {"model": ErrorResponse}},
    )
    async def health(request: Request):
        # ヘルスチェックはCOEIROINKへの疎通も確認
        data = await request.app.state.coeiroink.speakers()
        return {"status": "ok", "speakers": len(data)}

    @app.get(
        "/v1/models",
        dependencies=protected,
        summary="List supported models",
        responses=protected_responses,
    )
    async def models():
        return {
            "object": "list",
            "data": [{"id": MODEL, "object": "model", "owned_by": "local"}],
        }

    @app.get(
        "/v1/voices",
        dependencies=protected,
        summary="List available voices",
        responses={**protected_responses, 502: {"model": ErrorResponse}},
    )
    async def voices(request: Request):
        data = await request.app.state.coeiroink.speakers()
        return {
            "object": "list",
            "data": [
                {
                    "id": voice_id(speaker, style),
                    "name": voice_name(speaker, style),
                    "speaker_uuid": speaker.speaker_uuid,
                    "style_id": style.style_id,
                }
                for speaker, style in iter_voices(data)
            ],
        }

    @app.post(
        "/v1/audio/speech",
        dependencies=protected,
        summary="Generate speech from text",
        response_class=Response,
        responses={
            **protected_responses,
            200: {
                "description": "Audio in the requested format",
                "content": {
                    media_type: {"schema": {"type": "string", "format": "binary"}}
                    for media_type in MEDIA_TYPES.values()
                },
            },
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
            504: {"model": ErrorResponse},
        },
    )
    async def speech(payload: SpeechRequest, request: Request):
        # 未対応の指定は時間のかかる音声合成を始める前に拒否
        if payload.model != MODEL:
            raise InvalidRequestError(
                f"Unsupported model: {payload.model}; expected {MODEL}", param="model"
            )
        if payload.stream_format not in (None, "audio"):
            raise InvalidRequestError(
                "Streaming chunked audio is not supported", param="stream_format"
            )
        validate_format(payload.response_format)

        client: CoeiroinkClient = request.app.state.coeiroink
        data = await client.speakers()
        speaker, style = resolve_voice(payload.voice, data, settings.default_voice)
        wav = await client.synthesize(payload.input, speaker, style, payload.speed)
        # ffmpegの完了待ちで、ほかのHTTPリクエストの処理を止めない
        audio, media_type = await asyncio.to_thread(encode_audio, wav, payload.response_format)
        return Response(
            content=audio,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    if settings.cors_origins:
        # 例外処理を含むアプリ全体を包み、想定外の500にもCORSヘッダーを付ける
        return CORSMiddleware(
            app,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
    return app


# "uvicorn coeiroink_openai_tts.api:app"から参照されるアプリケーション
app = create_app()
