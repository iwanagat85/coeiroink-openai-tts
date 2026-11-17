"""クライアント入力と、COEIROINKから利用する応答項目を定義"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from coeiroink_openai_tts.config import MODEL

# OpenAIと同じ上限。長い文章でCOEIROINKが長時間占有されるのを防ぐ
MAX_INPUT_LENGTH = 4096


class ErrorDetail(BaseModel):
    message: str
    type: Literal["invalid_request_error", "server_error"]
    param: str | None
    code: str | None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SpeechRequest(BaseModel):
    model: str = MODEL
    input: str = Field(min_length=1, max_length=MAX_INPUT_LENGTH)
    voice: str = "auto"
    response_format: str = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    # 互換性のため受け付けるが、このアダプターでは合成パラメーターへ変換しない
    instructions: str | None = None
    stream_format: str | None = None

    @field_validator("input")
    @classmethod
    def reject_blank_input(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("input must contain non-whitespace text")
        # 前後の空白も読み上げ指定の一部なので、検査後は元の文章を保つ
        return value


class Style(BaseModel):
    style_id: int = Field(alias="styleId", strict=True, ge=0)
    style_name: str = Field(default="Style", alias="styleName")


class Speaker(BaseModel):
    speaker_uuid: str = Field(alias="speakerUuid", min_length=1)
    speaker_name: str = Field(default="Unknown", alias="speakerName")
    styles: list[Style] = Field(default_factory=list)


class Prosody(BaseModel):
    # 文節ごとの配列に音素の辞書が並ぶ。各音素の内容は加工せず合成へ渡す
    detail: list[list[dict[str, Any]]]
