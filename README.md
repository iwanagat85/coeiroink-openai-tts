# COEIROINK OpenAI互換TTSアダプター

COEIROINKv2で文章を音声に変換し、OpenAI互換の音声APIとして利用できます。  
音声・話速を指定でき、WAV・MP3など6形式で出力します。

## Requirements

- OS: Windows11
- Dockerが使える
- COEIROINKv2が使える状態にある（デフォルトポート: `50032`）

## How To Use

1. `.env` を設定  
   `APP_PORT` で公開ポートを変更できます（既定: `50033`）  
   `API_KEY` は推測されにくい任意のキーにしてください  
   既定の `local` のままでも動きますが起動時のログで警告が出ます

2. 以下のコマンドで起動  
   ```powershell
   docker compose up -d --build
   ```

- OpenAI互換TTSに対応したクライアントに次の値を設定して利用してください

| 項目 | 値 |
| --- | --- |
| Base URL | `http://localhost:50033/v1` |
| API Key | `.env` に設定したキー |
| Model | `coeiroink` |
| Voice | `auto`、スタイルID、または`つくよみちゃん/れいせい`のような名前 |

- ブラウザー上で動くクライアントから使う場合は、`.env` の `CORS_ORIGINS` にオリジンを設定してください

- 起動確認は以下のコマンドで行います  
   ```powershell
   Invoke-RestMethod http://localhost:50033/health
   ```

## ライセンス

このアダプターのソースコードは[MIT License](LICENSE)で提供します。

生成した音声には、COEIROINKと使用した音声ライブラリの利用規約が適用されます。  
音声を公開・配布する前に、話者ごとの利用規約とクレジット表記の指定を確認してください。
