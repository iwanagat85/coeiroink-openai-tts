"""話者とスタイルの組み合わせから、利用する声を一意に選ぶ"""

from collections.abc import Iterator, Sequence

from coeiroink_openai_tts.errors import InvalidRequestError, NoVoicesError
from coeiroink_openai_tts.models import Speaker, Style

# 既定の声を選ぶ指定。完全一致だけを受け付ける。未知の名前は400にする
DEFAULT_ALIASES = frozenset({"auto", "default", ""})
Voice = tuple[Speaker, Style]


def iter_voices(data: Sequence[Speaker]) -> Iterator[Voice]:
    for speaker in data:
        for style in speaker.styles:
            yield speaker, style


def voice_id(speaker: Speaker, style: Style) -> str:
    return f"{speaker.speaker_uuid}:{style.style_id}"


def voice_name(speaker: Speaker, style: Style) -> str:
    return f"{speaker.speaker_name}/{style.style_name}"


def resolve_voice(value: str, data: Sequence[Speaker], default_voice: str) -> Voice:
    """voiceの指定を、インストール済みの話者とスタイルに解決する

    1. 既定の声の指定（auto・default・空文字）はDEFAULT_VOICEに置き換える。
       DEFAULT_VOICEも同じ指定なら、スタイルIDが最小の声を使う
    2. ``<speakerUuid>:<styleId>`` 形式のIDと完全に一致する声を使う
    3. 数値だけの指定は、そのスタイルIDを持つ声を使う
    4. ``<話者名>/<スタイル名>`` 形式の表示名と完全に一致する声を使う。
       複数の声が一致する場合は、IDでの指定を求めてHTTP 400にする

    該当する声がなければ、別の声に置き換えずにHTTP 400のエラーにする。
    DEFAULT_VOICEから選んだ声も、クライアントが指定した声と同じ規則で検証する。
    """
    available = list(iter_voices(data))
    if not available:
        raise NoVoicesError("COEIROINK has no installed speakers/styles")

    from_default = value in DEFAULT_ALIASES
    effective = default_voice if from_default else value
    if effective in DEFAULT_ALIASES:
        # スタイルIDで比べる
        return min(available, key=lambda voice: voice[1].style_id)

    voice = _find_voice(effective, available)
    if voice is None:
        named = [v for v in available if voice_name(*v) == effective]
        if len(named) > 1:
            raise InvalidRequestError(
                f"Ambiguous voice name: {effective}. Use an id from GET /v1/voices",
                param="voice",
            )
        if named:
            return named[0]
        source = " (DEFAULT_VOICE)" if from_default else ""
        raise InvalidRequestError(
            f"Unknown voice: {effective}{source}. See GET /v1/voices", param="voice"
        )
    return voice


def _find_voice(value: str, available: Sequence[Voice]) -> Voice | None:
    for speaker, style in available:
        if value == voice_id(speaker, style):
            return speaker, style

    if not value.isdecimal():
        return None
    try:
        style_id = int(value)
    except ValueError:
        return None
    return next(
        ((speaker, style) for speaker, style in available if style.style_id == style_id), None
    )
