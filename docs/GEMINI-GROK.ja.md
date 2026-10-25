# Gemini CLI・Grok・Gemini APIとCription

MCPサーバー v0.5.0。各ユーザーが自分のMac・自分のアカウントで接続します。macOS 26以降、Python 3.9以降、uvが必要です。

```bash
brew install uv cloudflared
uv tool install --from git+https://github.com/msandroid/cription-mcp@v0.5.0 cription-mcp
uv tool update-shell
```

ターミナルを開き直してください。音声認識はApple SpeechAnalyzerをMac内で実行します。初回はXcode Command Line Toolsと言語アセットが必要です。

## Gemini CLI：ローカルMCP

[公式Gemini CLI](https://geminicli.com/docs/get-started/installation/)をインストールし、自分のGoogleアカウントまたはGemini APIキーで認証します。

```bash
npm install -g @google/gemini-cli
cription-mcp-setup install gemini
gemini
```

設定先は `~/.gemini/settings.json` の `mcpServers.cription` です。実行ファイルは絶対パスで登録します。他のサーバーや設定を保持し、変更前のバックアップを権限600で作成します。再実行は冪等です。更新時の置き換えは `cription-mcp-setup install gemini --replace` です。

Gemini CLI内で信頼する作業フォルダーを選び、`/mcp` でCriptionの8ツールを確認してください。信頼されていないフォルダーではMCPが無効になる場合があります。信頼確認は実際に使用するフォルダーについて行ってください。

> Criptionのspeech_languagesを1回だけ呼び出し、ja_JPが対応しているか確認してください。他のファイルやノートは読みません。

続いて自分の試験音声を絶対パスで指定し、`transcribe_audio` を呼び出します。長文は `read_transcript` で最後まで取得します。

### Gemini Extensionを使う場合

ExtensionはMCPとCriptionの利用ガイドをまとめたものです。公式レジストリへの掲載とは別です。

```bash
gemini extensions install https://github.com/msandroid/cription-plugins --ref v0.5.0
```

インストール時に表示されるMCP・コンテキストを確認します。`uvx` がPATH上に必要です。単体MCPとExtensionを同時に登録すると重複するため、どちらか一方を選んでください。単体設定から切り替える場合は `gemini mcp remove cription` でそのエントリだけを削除します。Extension削除は `gemini extensions uninstall cription` です。

公式：[MCP](https://geminicli.com/docs/tools/mcp-server/)／[Extensions](https://geminicli.com/docs/extensions/)

## Grok・Gemini API共通：認証付きHTTPS MCP

```bash
cription-mcp-remote init grok
cription-mcp-remote serve grok --tunnel
```

Gemini API用は `grok` を `gemini-api` に置き換えます。各サービスで別キーを作成します。初期化は一度だけで、再起動時は `serve` を実行します。初期状態は `speech_languages` のみ公開します。

表示された `Open locally` URLを同じMacで開き、MCP URLと `Authorization: Bearer ...` を確認します。キーをURL、チャット、Gitに入れないでください。フォームはローカルからだけ取得できます。公開URLは実行中のMacに転送されます。

Quick Tunnelは起動ごとにURLが変わります。継続利用は固定HTTPSプロキシと `--port`／`--public-url` を使用します。詳細は[HTTPS接続・公開範囲・キー失効](NOTION-MANUS.ja.md)を参照してください。自動起動は設定しません。

## Grok Web：Custom Connector

[Grok Connectors](https://grok.com/connectors) → New Connector → Customで、表示されたMCP URLを登録します。認証設定が表示される場合は、その方式に合わせてこの接続専用Bearerキーを設定します。URLだけで認証済みになるわけではありません。組織アカウントでは管理者設定が必要な場合があります。

接続後にCriptionの `speech_languages` だけを呼び出して確認します。認証の選択肢や利用条件が合わない場合はAPI経由を使用します。Webの認証を回避するためにMCP認証を無効にしないでください。

公式：[Grok Connectors](https://docs.x.ai/grok/connectors)

## Grok API

xAI Consoleで自分のAPIキーとモデル利用権限を確認します。既存キーは次のローカルフォームで保存できます。キーの新規発行やクレジット購入はこのCLIでは行いません。

```bash
cription-cloud grok --setup-key
```

保存先は `~/.config/cription-mcp/xai-api-key`、権限600です。代わりにローカル環境変数 `XAI_API_KEY` または `--key-file` を使えます。

```bash
cription-cloud grok --url https://YOUR-HOST/mcp --model YOUR_MODEL_ID \
  --prompt 'Call Cription speech_languages once. Is ja_JP supported?' --dry-run
# 確認後、--dry-run を外して実行します。
```

xAI Responses APIのRemote MCPを使用します。モデルを勝手に選択しません。`--model` はアカウントで利用可能なIDを指定してください。生成上限は既定512トークンです。

公式：[Remote MCP](https://docs.x.ai/developers/tools/remote-mcp)

## Gemini API

[Google AI Studio](https://aistudio.google.com/api-keys)で自分のプロジェクトのAPIキー・利用枠を確認します。Google AI Pro／Ultraの契約と、Gemini APIの課金・利用枠は別です。

```bash
cription-cloud gemini --setup-key
```

保存先は `~/.config/cription-mcp/gemini-api-key`、権限600です。代わりに `GEMINI_API_KEY`／`GOOGLE_API_KEY` または `--key-file` を使えます。Gemini CLIはこの管理ファイルを自動では読みません。CLIは自身のログイン機能、または自分で管理した環境変数で認証してください。

```bash
cription-cloud gemini --url https://YOUR-HOST/mcp --model YOUR_MODEL_ID \
  --prompt 'Call Cription speech_languages once. Is ja_JP supported?' --dry-run
# 確認後、--dry-run を外して実行します。
```

Interactions APIのStreamable HTTP MCPを使用し、`store: false` を指定します。これはGoogle側のすべてのログ・保持ポリシーを無効にする保証ではありません。プロジェクトの利用条件を確認してください。

公式：[Function calling / Remote MCP](https://ai.google.dev/gemini-api/docs/function-calling)／[Interactions API](https://ai.google.dev/api/interactions-api)

## ツール公開範囲・プライバシー

追加ツールが必要なら、初期化時に `--tools speech_languages list_notes search_notes get_note` のように指定します。8ツールすべてを許可する場合だけ `--tools all` を使います。既存プロファイルでは `~/.config/cription-mcp/remote-CLIENT.json` の `tools` 配列を変更し、権限600を維持して再起動します。API呼び出し側の `--tools` でさらに絞れますが、サーバーで許可されていないツールは追加できません。

音声認識はMac内で処理します。ツール結果の文字起こし・ノート本文はGrok／Googleへ送信され、トンネル利用時はCloudflareも通信経路に入ります。既定の試験は言語一覧だけで、録音やノートを読みません。リモートの任意保存先 `save_to` は無効です。

APIキーとMCP接続キーは別です。片方をもう片方の入力欄に入れないでください。キーは出力・配布せず、dry-runは認証ヘッダーを伏せ字にします。HTTPエラー本文は資格情報を含む可能性があるため表示しません。課金や重複を避けるため、API書き込みは自動再試行しません。

## Meta AI

[Connectors早期アクセス](https://dev.meta.ai/products/connectors)は招待制です。申請・承認と、コネクター実装・一般公開は別です。OAuthアカウント連携と安定した公開先の対応は未実装です。このリリースはMeta AI接続済み・承認済みとはしていません。

## 検証状況（2026-10-25）

- Gemini CLI 0.65.0：単体MCPの `Connected` と、`gemini-3.1-flash-lite` での `speech_languages` 呼び出し・成功結果・モデル回答を確認。比較試験では `gemini-3.5-flash` が503（高負荷）を返し、`gemini-3.8-flash` はタイムアウト。これはMCP接続成功とは別に扱っています。
- Gemini API：無料枠の既存キーと `gemini-3.5-flash` を使用し、公開HTTPS MCPの `speech_languages` 呼び出し・`function_result`・日本語対応の回答を確認。APIが返した `requires_action` ステータスはそのまま報告し、書き換えていません。`gemini-3.8-flash` はツールなしの対照試験でもタイムアウトしました。
- Grok：専用プロファイルの公開HTTPSで公式MCP SDKによる認証・言語一覧取得に成功。Grokアプリの登録・会話はログイン時の規約同意待ち。xAI APIの実呼び出しも未検証です。
- 共通MCP：合成ノートを使った8ツール・実音声認識が成功。
- 自動テスト：サーバー側35件、プラグイン側4件成功。
- Meta AI：申請内容を準備済み。必須の氏名・チーム人数が未確定で、送信・受付は未完了。承認済みとはしていません。

モデル経由の再試験には、既存設定と自分の認証を使って `python tests/smoke_gemini_cli.py --model MODEL_ID --log /absolute/path/to/new-private.log` を実行できます。ログは新規作成・権限600です。試験は一時的な空フォルダーだけを信頼し、`speech_languages` だけを自動承認します。通常利用の設定や信頼範囲は変更しません。
