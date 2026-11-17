"""待受開始後にホスト側の接続先を表示する、コンテナ用の起動処理"""

import logging
import os
import socket

import uvicorn

logger = logging.getLogger("uvicorn.error")


class Server(uvicorn.Server):
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if not self.started:
            return

        # コンテナ内からはホストの公開ポートを取得できないため、Composeから渡す
        public_port = os.getenv("APP_PORT") or self.config.port
        public_url = f"http://localhost:{public_port}"
        logger.info("OpenAI API Base URL: %s/v1", public_url)
        logger.info("API docs: %s/docs", public_url)


def main() -> None:
    server = Server(uvicorn.Config("coeiroink_openai_tts.api:app", host="0.0.0.0", port=8000))
    server.run()


if __name__ == "__main__":
    main()
