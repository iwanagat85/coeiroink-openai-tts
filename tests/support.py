"""テスト専用の話者データとCOEIROINKの代替応答。実サービスには接続しない"""

from copy import deepcopy

import httpx

SPEAKERS = [
    {
        "speakerUuid": "speaker-a",
        "speakerName": "話者A",
        "styles": [{"styleId": 10, "styleName": "通常"}, {"styleId": 20, "styleName": "元気"}],
    },
    {
        "speakerUuid": "speaker-b",
        "speakerName": "話者B",
        "styles": [{"styleId": 3, "styleName": "通常"}],
    },
]
AUTH = {"Authorization": "Bearer test-key"}
# アダプターが話者一覧の取得に使う、画像を含まない軽量版のエンドポイント
SPEAKERS_PATH = "/v1/speakers_path_variant"


def post_speech(client, **overrides):
    """正しいキーで音声合成を呼ぶ。既定ではWAVを要求し、ffmpegを起動しない"""
    payload = {"input": "テスト", "response_format": "wav", **overrides}
    return client.post("/v1/audio/speech", json=payload, headers=AUTH)


class FakeCoeiroink:
    def __init__(self, wav: bytes):
        self.speakers = deepcopy(SPEAKERS)
        # COEIROINK v2の実応答と同じ「文節 -> 音素」の二重配列を使う
        self.prosody = {"detail": [[{"phoneme": "t-e", "hira": "て", "accent": 1}]]}
        self.wav = wav
        self.requests: list[httpx.Request] = []
        self.overrides: dict[str, httpx.Response | Exception] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        override = self.overrides.get(path)
        if isinstance(override, Exception):
            raise override
        if override is not None:
            return override
        if path == SPEAKERS_PATH:
            return httpx.Response(200, json=self.speakers)
        if path == "/v1/estimate_prosody":
            return httpx.Response(200, json=self.prosody)
        if path == "/v1/synthesis":
            return httpx.Response(200, content=self.wav)
        raise AssertionError(f"Unexpected upstream request: {request.method} {path}")
