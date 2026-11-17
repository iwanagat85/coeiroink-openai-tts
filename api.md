# API仕様

| エンドポイント | メソッド | 認証 | 用途 |
| --- | --- | --- | --- |
| `/health` | GET | 不要 | アダプターからCOEIROINKへの疎通確認 |
| `/v1/models` | GET | Bearerキー | 対応モデルの取得 |
| `/v1/voices` | GET | Bearerキー | インストール済みの話者・スタイルIDの取得 |
| `/v1/audio/speech` | POST | Bearerキー | 音声全体を生成してから返す音声合成 |

キーの設定方法は[設定・トラブル対応](configuration.md)を参照してください。

起動中のアダプターの `/docs` で操作可能なAPI仕様、`/openapi.json` でOpenAPI定義を確認できます。  
音声生成の6種類のContent-Type、Bearer認証、JSON形式のエラー応答を定義しています。  
これらの仕様の閲覧には認証は不要ですが、`/docs` から `/v1/*` を実行する際はAuthorizeでキーを設定します。

## 音声生成の例（PowerShell）

[README](../README.md)に従って起動した後、`.env` と同じキーを入力します。
音声一覧を取得し、テキストから生成した音声を `test.wav` に保存する例です。

```powershell
$apiKey = Read-Host 'API key configured in .env'
$headers = @{Authorization="Bearer $apiKey"}
Invoke-RestMethod -Headers $headers http://localhost:50033/v1/models
Invoke-RestMethod -Headers $headers http://localhost:50033/v1/voices
$body = @{model='coeiroink';input='こんにちは、テスト音声です。';voice='auto';response_format='wav';speed=1.0} | ConvertTo-Json
Invoke-WebRequest 'http://localhost:50033/v1/audio/speech' -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -OutFile test.wav
```

## 音声合成のリクエスト

`POST /v1/audio/speech` には、次の項目をJSONで送ります。

| 項目 | 型 | 既定値 | 内容 |
| --- | --- | --- | --- |
| `input` | 文字列 | 必須 | 読み上げる文章。1〜4096文字で、空白以外の文字を含める。前後の空白は保持する |
| `model` | 文字列 | `coeiroink` | `coeiroink` だけを受け付ける |
| `voice` | 文字列 | `auto` | 使う声。指定方法は次の「声の指定」を参照 |
| `response_format` | 文字列 | `mp3` | `wav`、`mp3`、`opus`、`aac`、`flac`、`pcm` のいずれか |
| `speed` | 数値 | `1.0` | 話速。`0.25` 以上 `4.0` 以下 |
| `stream_format` | 文字列 | なし | 省略するか `audio` を指定する。どちらも音声全体を1つの応答で返す |
| `instructions` | 文字列 | なし | 受け付けるが、合成には反映しない |

### 声の指定

- 声を固定する場合は、`/v1/voices` が返す `<speakerUuid>:<styleId>` 形式のIDを指定します。
- `voice` を省略した場合と、`auto`・`default`・空文字を指定した場合は、既定の声を使います。  
  `DEFAULT_VOICE` にIDを設定していればその声、設定していなければスタイルIDが数値として最小の声です。
- 数値だけの指定は、そのスタイルIDを持つ声を使います。  
  スタイルIDは話者をまたいで重複しない前提で、重複している場合は `/v1/voices` で先に並ぶ声になります。
- `/v1/voices` の `name`（例: `つくよみちゃん/れいせい`）と完全に一致する指定も使えます。  
  確実に選ぶには `<speakerUuid>:<styleId>` 形式を使ってください。
- 大文字・小文字や前後の空白は区別します。一致する声がなければ、別の声に置き換えずにHTTP 400を返します。  
  `DEFAULT_VOICE` が一致しない場合も同じで、`message` に `(DEFAULT_VOICE)` が付きます。
- 声の一覧はリクエストのたびにCOEIROINKから取得します。音声ライブラリを追加・削除しても、アダプターの再起動は不要です。

```json
{"error": {"message": "Unknown voice: alloy. See GET /v1/voices", "type": "invalid_request_error", "param": "voice", "code": null}}
```

### 出力形式

| 形式 | Content-Type | 内容 |
| --- | --- | --- |
| `wav` | `audio/wav` | COEIROINKの出力（44.1kHz）を再変換せずに返す |
| `mp3` | `audio/mpeg` | 192kbps |
| `opus` | `audio/ogg` | Oggコンテナ、96kbps |
| `aac` | `audio/aac` | ADTS形式、192kbps |
| `flac` | `audio/flac` | 可逆圧縮 |
| `pcm` | `application/octet-stream` | ヘッダーなし・符号付き16bit・リトルエンディアン・24kHz・モノラル |

## 応答の例

`GET /v1/voices` は、インストール済みのスタイルごとに1件を返します。`id` を `voice` に指定できます。

```json
{
  "object": "list",
  "data": [
    {"id": "<speakerUuid>:<styleId>", "name": "<話者名>/<スタイル名>", "speaker_uuid": "<speakerUuid>", "style_id": 0}
  ]
}
```

`GET /health` は、COEIROINKに接続できると話者の数を返します。

```json
{"status": "ok", "speakers": 3}
```

## エラー応答

エラーの本文はOpenAIと同じ形式です。`type` は4xxで `invalid_request_error`、5xxで `server_error` です。  
`param` には問題のあった項目名が入り、特定できない場合は `null` です。

```json
{"error": {"message": "Unsupported response_format: ogg", "type": "invalid_request_error", "param": "response_format", "code": null}}
```

| ステータス | 主な原因 |
| --- | --- |
| 400 | 未対応の `model`・`voice`（`DEFAULT_VOICE` が一致しない場合を含む）・`response_format`・`stream_format`、項目の型や範囲の誤り、JSONとして読めない本文 |
| 401 | キーの欠落・誤り。`code` は `invalid_api_key` で、`WWW-Authenticate: Bearer` ヘッダーを付ける |
| 404・405 | 存在しないパス、または許可されていないメソッド |
| 500 | 音声変換の失敗、その他の想定外のエラー |
| 502 | COEIROINKへの接続失敗やタイムアウト（接続5秒・応答120秒）、COEIROINKのHTTPエラー、不正なJSONやデータ構造、WAVでない・空または途中で切れた合成結果 |
| 503 | COEIROINKに利用可能な声・スタイルがない |
| 504 | 音声変換が60秒を超えた |

接続エラーの種類やffmpegのエラー出力などの詳細は、内部情報を含み得るため応答には含めず、アダプターのログに記録します。  
想定外のエラーでは、応答の `message` は `Internal server error` だけになり、ログにトレースバックを記録します。  
確認方法は[設定・トラブル対応](configuration.md#トラブル対応)を参照してください。

WAVは再変換せず、RIFF全体の長さ、必須チャンク、音声フレームの長さを検査します。  
CORSを有効にしている場合、許可したオリジンには想定外の500応答にもCORSヘッダーを付けます。
