"""環境変数と既定値を管理する"""

import os
from dataclasses import dataclass, field

MODEL = "coeiroink"
DEFAULT_API_KEY = "local"


@dataclass(frozen=True, slots=True)
class Settings:
    coeiroink_url: str = "http://host.docker.internal:50032"
    api_key: str = field(default=DEFAULT_API_KEY, repr=False)
    # auto・default・空文字ならスタイルIDが最小の声
    default_voice: str = "auto"
    # ブラウザーからの呼び出しを許可するオリジン。空ならCORSは無効
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # 直接起動でもComposeと同じ既定値に戻し、空キーで認証が無効になるのを防ぐ
        if not self.api_key:
            object.__setattr__(self, "api_key", DEFAULT_API_KEY)

    @classmethod
    def from_env(cls) -> "Settings":
        # .envの読み込みはComposeに任せる。Python単独起動では環境変数を使う
        defaults = cls()
        return cls(
            coeiroink_url=(os.getenv("COEIROINK_URL") or defaults.coeiroink_url).rstrip("/"),
            api_key=os.getenv("API_KEY") or defaults.api_key,
            default_voice=os.getenv("DEFAULT_VOICE") or defaults.default_voice,
            cors_origins=_parse_origins(os.getenv("CORS_ORIGINS", "")),
        )


def _parse_origins(value: str) -> tuple[str, ...]:
    # ブラウザーが送るOriginには末尾のスラッシュが付かないので照合できる形にそろえる
    origins = (origin.strip().rstrip("/") for origin in value.split(","))
    return tuple(origin for origin in origins if origin)
