# API仕様

| エンドポイント | メソッド | 認証 | 用途 |
| --- | --- | --- | --- |
| `/health` | GET | 不要 | アダプターからCOEIROINKへの疎通確認 |
| `/v1/models` | GET | Bearerキー | 対応モデルの取得 |
| `/v1/voices` | GET | Bearerキー | インストール済みの話者・スタイルIDの取得 |
| `/v1/audio/speech` | POST | Bearerキー | 音声全体を生成してから返す音声合成 |


### 声の指定

- 声を固定する場合は、`/v1/voices` が返す `<speakerUuid>:<styleId>` 形式のIDを指定します。
- `voice` を省略、`auto`・`default`、空文字を指定した場合は、既定の声を使います。  
  `DEFAULT_VOICE` にIDを設定していればその声、設定していなければスタイルIDが一番若いものを使います。
- `/v1/voices` の `name`（例: `つくよみちゃん/れいせい`）と完全に一致する指定も使えます。  
  確実に選ぶには `<speakerUuid>:<styleId>` 形式を使ってください。
