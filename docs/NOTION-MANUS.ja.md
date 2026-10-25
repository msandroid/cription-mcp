# Notion・ManusからCriptionを使う

対象：Cription MCP v0.4.0、macOS 26以降、Python 3.9以降。各ユーザーが自分のMacで実行します。共用サーバーや共用キーはありません。

## インストール

```bash
brew install uv cloudflared
uv tool install --from git+https://github.com/msandroid/cription-mcp@v0.4.0 cription-mcp
uv tool update-shell
# ターミナルを開き直してから：
cription-mcp-setup doctor
```

初回の音声認識ではXcode Command Line ToolsとAppleの言語アセットが必要です。GUIアプリ用のMCP設定とは別に、以下のCLIが追加されます。

- `cription-notion`：選んだノート／文字起こしをNotionページへ保存。
- `cription-mcp-remote`：Notion Custom Agents／Manus用の認証付きStreamable HTTP接続。

## Notionへの保存（Custom Agents不要）

1. [Notionのコネクション管理](https://www.notion.so/profile/integrations)で自分のワークスペース用にCriptionコネクションを作成します。通常のエクスポートに必要なのはコンテンツの挿入権限です。読み戻しをする場合だけ読み取り権限も付けます。ユーザー情報やコメントへの権限は不要です。
2. 「コンテンツへのアクセス」で、保存先の親ページだけを選択します。保存先は通常ページです。データベース／データソースへの直接保存はこのCLIの対象外です。
3. 次のコマンドを実行し、開いた**このMacだけのフォーム**にAPIトークンを入力します。トークンは `~/.config/cription-mcp/notion-api-key` に権限600で保存されます。キーをチャットやGitに貼り付けないでください。既存ファイルは上書きしません。

```bash
cription-notion --setup-token
```

既にキーを管理している場合は、ローカルの `NOTION_API_KEY` 環境変数、または `--token-file /absolute/path/to/private-key` を使えます。トークンファイルは権限600が必要です。

まず送信前の内容を確認します。`--output` のファイルは新規作成・権限600です。

```bash
cription-notion --file /absolute/path/to/transcript.md --dry-run --output /absolute/path/to/export-preview.json
```

Notionに保存します。`PAGE_ID` は親ページURL末尾の32桁のIDです。ハイフン付きUUIDも使えます。

```bash
cription-notion --file /absolute/path/to/transcript.md --parent-page PAGE_ID --title '会議メモ'
cription-notion --note-id NOTE_ID --parent-page PAGE_ID
```

`NOTE_ID` はCriptionの `list_notes`／`search_notes` で確認します。ノートの要約・文字起こし・メモを保存します。見出し、箇条書き、チェックリスト、引用を変換します。その他のMarkdownは段落のテキストとして保持します。長文は文字数、100ブロック、リクエスト容量に合わせて分割します。添付音声・画像・データベースのプロパティは転送しません。

成功時に作成ページのURLを返します。追記の途中で失敗した場合は、そのページURLを表示します。重複を避けるため、ページを確認してから再実行してください。書き込みは自動再試行しません。Notion側の権限、ブロック上限、API制限は適用されます。

## Manus／Notion Custom Agents共通：HTTPS MCP

クラウド側のAIからMacの `localhost` やstdioを直接呼べないため、認証付きHTTPS経由で接続します。OpenAI Secure MCP Tunnelはこの接続には使用しません。

最初は、ノートを読めない `speech_languages` だけを許可します。クライアントごとに別のキーと設定ファイルを作ります。

```bash
cription-mcp-remote init manus
cription-mcp-remote serve manus --tunnel
```

Notion用は `manus` を `notion` に置き換えます。初期化は一度だけです。再起動時は `serve` を実行します。既存の設定やキーを勝手に上書きしません。

表示される `Open locally: http://127.0.0.1:.../connect/...` を**同じMac**で開きます。フォームの値を接続先へ設定します。

| 項目 | 値 |
|---|---|
| 接続名 | Cription |
| MCP URL | フォームに表示された `https://.../mcp` |
| 認証方式 | Header／Bearer token |
| ヘッダー名 | `Authorization` |
| ヘッダー値 | フォームの `Bearer ...` 全体 |

Bearer専用欄がある場合は `Bearer ` を除いたキーだけ入力します。キーは画面では伏せ字です。キー入りURLは生成しません。フォームはローカルHost以外から取得できません。

接続後の確認プロンプト：

> Criptionのspeech_languagesを1回呼び出し、日本語が対応しているか答えてください。他のファイルやノートは読みません。

### Manusの画面

[Manus](https://manus.im)へログインし、Settings → Connectors → Custom MCP（またはAdd custom connector）で上記URLと認証を設定します。接続テスト後、チャットでCriptionコネクターを選びます。画面名や利用条件はアカウントによって異なる場合があります。ローカルコマンドの入力欄だけでMac上の実行が保証されるわけではありません。この手順はHTTPS URL接続を使用します。

公式：[Custom MCP Servers](https://manus.im/docs/integrations/custom-mcp)

### Notion Custom Agentsの画面

**Business／Enterpriseが必要**です。通常のNotion保存CLIとは利用条件が異なります。

ワークスペース管理者がSettings → ConnectionsでCustom MCPを許可し、必要ならURLを許可リストに追加します。対象エージェントのSettings → Tools and access → Add tool → Custom MCPで上記URLとHeader／Bearer認証を登録します。最初は手動実行にし、自動トリガーを有効にする前にアクセス範囲を確認します。利用権限がない場合、この接続試験は実行できません。CLIからのページ保存は別途利用できます。

公式：[MCP connections for Notion Custom Agents](https://www.notion.com/help/mcp-connections-for-custom-agents)

## 必要なツールだけを公開する

新しい接続を初期化する時に `--tools` で選びます。例：

```bash
cription-mcp-remote init manus --tools speech_languages list_notes search_notes get_note
# 8ツールすべてを許可する場合のみ：
cription-mcp-remote init notion --tools all
```

既に初期化済みなら先にプロセスを止め、該当の `~/.config/cription-mcp/remote-manus.json` または `remote-notion.json` の `tools` 配列だけを編集します。モード600を維持して再起動してください。`config manus`／`config notion` はキーを出力せず、設定先と許可ツールを確認できます。

`all` は8ツールです：`transcribe_audio`、`read_transcript`、`speech_languages`、`list_notes`、`search_notes`、`get_note`、`list_folders`、`cription_status`。許可したクライアントは、このMacのノートや指定されたローカル音声ファイルにアクセスできます。ブラウザへの添付は自動的にMacのファイルになりません。リモート接続での任意ファイル書き込み `save_to` は無効です。認識結果の内部キャッシュは従来どおりMacに保存されます。

## 継続利用・更新・停止

`--tunnel` はCloudflare Quick Tunnelです。URLは起動ごとに変わります。再起動した場合は接続先のURLも更新します。Macのスリープ、ネットワーク切断、プロセス終了中は利用できません。自動起動はインストールしません。

安定したURLが必要な場合は、自分で管理するCloudflare Named TunnelなどのHTTPSリバースプロキシを、固定ポートのループバックに向けます。

```bash
cription-mcp-remote serve manus --port 8766 --public-url https://cription.example.com
```

`--public-url` はURLを設定するだけです。DNS、証明書、リバースプロキシは別途必要です。`127.0.0.1:8766` を転送先にし、公開Hostを維持してください。LAN全体へのbind、認証削除、キーをGitHubに公開する設定は不要です。実装はstateless Streamable HTTPで、旧SSE専用クライアントは対象外です。

キー失効時はプロセスを停止し、接続先のコネクターを削除します。該当する `remote-CLIENT.json` を削除して再初期化すると新しいキーを発行できます。再起動後、古いキーは利用できません。Notion APIトークンの失効はNotionのコネクション管理で行います。

更新：

```bash
uv tool install --force --from git+https://github.com/msandroid/cription-mcp@v0.4.0 cription-mcp
```

音声認識はMac内で行います。許可したツールが返す文字起こし・ノート本文は接続先AIへ、Notion保存内容はNotionへ送信されます。HTTPSトンネル利用時はCloudflareも通信経路に入ります。各サービスのデータ取り扱い規約を確認してください。

## 検証状況（2026-10-25）

- Notion REST API：専用試験ページだけにアクセスを付与し、新CLIでページ作成・5ブロックの読み戻し照合に成功。合成データのみ使用。
- MCP：公式Python SDKでHTTP経由の8ツール、実音声認識に成功。公開HTTPS経由でもBearer認証、ツール一覧、`speech_languages` に成功。
- Notion Custom Agents：接続先ワークスペースのBusiness権限制限で未検証。プラン変更はしていません。
- Manus：ログイン時の規約同意が未完了のため、Manusアプリからの実呼び出しは未検証。HTTPS MCPの試験成功とは区別しています。
