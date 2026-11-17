"""クライアントへ返すエラーの分類"""


class AdapterError(Exception):
    """クライアント向けの文言とサーバーログだけに残す原因を分けて持つ"""

    status_code = 500
    code: str | None = None

    def __init__(
        self, message: str, *, param: str | None = None, log_detail: str | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        # 問題のあったリクエスト項目。OpenAI形式のエラーのparamとして返す
        self.param = param
        # 上流の例外やffmpegの出力など内部情報を含み得るのでクライアントには返さない
        self.log_detail = log_detail


class InvalidRequestError(AdapterError):
    status_code = 400


class AuthenticationError(AdapterError):
    status_code = 401
    code = "invalid_api_key"


class ConversionError(AdapterError):
    """Audio conversion by the bundled ffmpeg failed"""


class ConversionTimeoutError(ConversionError):
    status_code = 504


class UpstreamError(AdapterError):
    """Failed to connect to COEIROINK, or received an unexpected response"""

    status_code = 502


class NoVoicesError(AdapterError):
    status_code = 503
