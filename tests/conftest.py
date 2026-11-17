"""実際のCOEIROINKやAPIキーに触れず、API全体を検証するための共通部品"""

import io
import math
import struct
import wave
from contextlib import ExitStack

import httpx
import pytest
from fastapi.testclient import TestClient

from coeiroink_openai_tts.api import create_app
from coeiroink_openai_tts.config import Settings
from tests.support import FakeCoeiroink


@pytest.fixture
def wav_bytes():
    # 短い正弦波をメモリ上に作る。外部の音声素材やスピーカー再生は不要
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        samples = (int(8000 * math.sin(2 * math.pi * 440 * n / 44100)) for n in range(4410))
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()


@pytest.fixture
def upstream(wav_bytes):
    return FakeCoeiroink(wav_bytes)


@pytest.fixture
def client_factory(upstream):
    # lifespanも実行し、実運用と同様に共有HTTP接続を作成・終了させる
    with ExitStack() as stack:

        def make_client(**settings):
            config = {"api_key": "test-key", "coeiroink_url": "http://coeiroink.test"}
            config.update(settings)
            app = create_app(Settings(**config), transport=httpx.MockTransport(upstream))
            return stack.enter_context(TestClient(app))

        yield make_client


@pytest.fixture
def client(client_factory):
    return client_factory()
