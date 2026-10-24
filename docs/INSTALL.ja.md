# Cription連携：日本語インストールガイド

MCPサーバー v0.3.0／プラグイン v0.3.0。音声認識はMac上で処理します。返された文字起こし・ノート本文は接続先のAIサービスに渡ります。

## 1. 必要なもの

- 文字起こし：macOS 26以降、Python 3.9以降、Xcode Command Line Tools。
- ノート参照：Cription Macアプリ内に保存済みのノート。iPhoneのノートはMacに存在するものだけが対象です。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)。サーバー自体にPythonの追加依存ライブラリはありません。
- 利用するAIクライアントへのログインと、そのクライアントの利用可能なモデル枠。

Command Line Toolsがない場合は、ターミナルで実行して画面の案内に従います。

```bash
xcode-select --install
```

## 2. サーバーをインストール

```bash
uv tool install --from git+https://github.com/msandroid/cription-mcp@v0.3.0 cription-mcp
uv tool update-shell
```

ターミナルを開き直し、`cription-mcp-setup --help`を確認してください。PATHに反映されていない場合は、`"$(uv tool dir --bin)/cription-mcp-setup"`を代わりに使えます。以降はソースのダウンロード先に依存しない設定です。

MCPを重複登録しないよう、各クライアントで「プラグイン経由」か「サーバー単体」の一方を選んでください。セットアップは既存の他のサーバーを保持し、変更前のJSONを同じフォルダにバックアップします。

## 3. クライアントごとの接続

### Claude Code

スキル付きプラグインはClaude Code内で実行します。

```text
/plugin marketplace add msandroid/cription-plugins
/plugin install cription@cription
```

サーバーだけを使う場合はターミナルで実行します。

```bash
cription-mcp-setup install claude-code
claude mcp get cription
```

`Connected`を確認します。未ログインなら`claude auth login`を実行してください。

### Claude Desktop

[cription-0.3.0.mcpbをダウンロード](https://github.com/msandroid/cription-mcp/releases/download/v0.3.0/cription-0.3.0.mcpb)してClaude Desktopで開くか、手順2のインストール後に実行します。

```bash
cription-mcp-setup install claude-desktop
```

Claude Desktopを再起動し、開発者／MCP設定でCriptionの起動を確認します。`.mcpb`でもPythonとCommand Line Toolsは必要です。

### Codex

```bash
cription-mcp-setup install codex
codex mcp get cription
```

議事録などのスキルも使う場合は追加します。

```bash
codex plugin marketplace add msandroid/cription-plugins --ref v0.3.0
codex plugin add cription@cription
```

Codexのプラグインはスキルを提供し、上のMCP登録がツールを提供します。設定後は新しいチャットを開始するかアプリを再起動してください。

### Antigravity

```bash
cription-mcp-setup install antigravity
```

Antigravityを再起動し、**Customizations → Installed → MCP Servers → cription → 8 tools enabled**を確認します。

古いIDE版で設定先が異なる場合のみ、`cription-mcp-setup install antigravity-legacy`を使います。スキル付きプラグインのローカル導入は[プラグイン側の案内](https://github.com/msandroid/cription-plugins#antigravity)を参照してください。

### Cursorなど

`cription-mcp-setup config claude-desktop`で、標準的な`mcpServers`設定を表示できます。`cription`の項目だけを`.cursor/mcp.json`などに追加してください。GUIから`uvx`を起動する方式の例は[英語README](../README.md#cursor-and-other-stdio-mcp-clients)にあります。

## 4. ChatGPT

各ユーザーが**自分のMacに接続するTunnel**を作成します。このGitHub公開は、共有サーバーやChatGPTの公開ディレクトリへの掲載を意味しません。他のユーザーのTunnel ID・キーを流用しないでください。

インストール後、次の1コマンドで進めます。

```bash
cription-mcp-setup chatgpt connect
```

- 公式tunnel-clientがなければ、macOS用v0.0.18をSHA-256照合して専用フォルダーにインストールします。
- PlatformのTunnel設定を開き、作成したTunnel IDをターミナルで受け取ります。Tunnelを自分のChatGPTワークスペースへ関連付けてください。
- キーが未保存ならPlatformと、このMacだけのキー入力フォームを開きます。**Tunnels Read・Useだけ**の期限付きキーを作成し、フォームに入力します。キーは`~/.config/cription-mcp/runtime-key`へ権限600で保存し、本文はログに残しません。
- 管理対象のランタイムを起動し、最大60秒待ってreadyを確認します。コマンド終了後も動作します。
- ChatGPTのPlugins画面を開き、登録に使うTunnel IDと設定値を表示します。

最後にChatGPTで **Add → Add custom MCP server** を選び、名前をCription、接続をTunnel、自分のTunnel ID、認証をNo authenticationにします。表示される権限を確認して作成し、Connect → Try in chatを実行します。

ログイン、Tunnelの作成とワークスペース関連付け、APIキー発行、ChatGPT側の登録と権限承認はアカウント側で行います。利用可否は契約・管理者設定に依存します。セットアップはこれらの画面を案内します。

既存Tunnelなら入力を省けます。

```bash
cription-mcp-setup chatgpt connect --tunnel-id tunnel_YOUR_ID
```

再実行時は同名の稼働中Tunnelを再利用します。別のTunnelを使う場合は`--profile another-name`を指定します。`--key-file /absolute/path/to/key`で保存先変更、`--no-browser`でブラウザー自動表示を無効化できます。Mac再起動後は同じconnectコマンドで再開してください。ログイン時の自動起動は設定しません。停止・状態確認のコマンドは実行結果に表示されます。

[OpenAI公式のTunnel手順](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)も参照してください。APIキーをチャットに貼る必要はありません。旧`key`・`init`・`doctor`・`run`も引き続き利用できます。

## 4a. Ollama・llama.cpp（ローカルLLM）

`cription-local`がモデルのtool callingとCriptionの8ツールを接続します。Pythonの追加依存は不要です。認識・モデル推論・ツール結果の受け渡しをMac内で行います。接続先はループバックIPのHTTPに限定し、HTTPプロキシとリダイレクトを使いません。Ollamaではクラウドモデルを選ばず、ダウンロード済みのローカルモデルを使ってください。

### Ollama

```bash
brew install ollama
ollama serve
# 別のターミナル
ollama pull qwen3:0.6b
cription-local ollama --model qwen3:0.6b --prompt 'speech_languagesを呼んで対応言語を教えて'
```

### llama.cpp

```bash
brew install llama.cpp
llama-server -m /absolute/path/to/tool-capable-model.gguf --jinja --host 127.0.0.1 --port 8080
# 別のターミナル。modelはサーバーのモデル名・エイリアスに合わせます。
cription-local llama-cpp --model local --prompt 'speech_languagesを呼んで対応言語を教えて'
```

モデルに合ったtool calling対応テンプレートが必要です。`--jinja`だけで動かない場合は配布元のテンプレート指定に従ってください。モデルの能力により、ツールを正しく選べない場合があります。Qwen3 0.6Bの実機検証では両エンジンからのツール呼び出しは成功しましたが、返された言語数の要約に誤りがありました。小型モデルの回答は原文・ツール結果と照合してください。

音声の例：

```bash
cription-local ollama --model qwen3:0.6b --tools transcribe_audio read_transcript --prompt '/Users/yourname/Downloads/test.m4a をja-JPで文字起こしして要点を日本語でまとめて'
```

`--tools`でモデルが使えるツールを制限できます。省略時は全8ツールです。`--base-url http://127.0.0.1:PORT`でポート変更、`--max-rounds 8`で連続呼び出し回数、`--timeout 180`でモデルの応答待ち秒数を指定できます。長文は標準入力からも渡せます。モデル・音声・ノートのダウンロードや送信はセットアップで自動実行しません。

公式仕様：[Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling)、[llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)。

## 5. 最初の動作確認

次のように依頼します。音声パスは自分のMacに実在するファイルへ置き換えてください。

> Criptionのspeech_languagesを呼び出し、続いて /Users/yourname/Downloads/test.m4a をlocale ja-JPで文字起こししてください。他のノートやファイルは開かないでください。

初回はSwiftヘルパーのビルドやAppleの言語データ取得で時間がかかります。長い文字起こしは`transcriptId`と`nextOffset`が返るため、`read_transcript`で続きを取得します。ChatGPTに添付しただけのファイルは、このMacのファイルにはなりません。

## 困ったとき

| 状況 | 対処 |
|---|---|
| コマンドが見つからない | ターミナルを開き直すか、`"$(uv tool dir --bin)/cription-mcp-setup"`を使います。GUIでは絶対パスの設定を使います。 |
| Criptionが既に登録済み | 既存設定を確認し、置き換える場合だけ`install CLIENT --replace`を実行します。 |
| ノートが0件 | `cription_status`で保存先を確認します。Mac内にあるCriptionのノートだけが対象です。 |
| 文字起こしが使えない | macOS 26以降、`xcode-select -p`、`speech_languages`の結果を確認します。 |
| Claude／Antigravityのモデル上限 | MCP接続とは別の制限です。クライアントの利用枠が回復してから会話試験を行います。 |
| ChatGPTが接続できない | Tunnelのワークスペース関連付け、キーのRead・Use権限・有効期限、`doctor`の結果、`run`の継続を確認します。 |
| toolsが重複する | 同じクライアントでプラグインのMCPとサーバー単体を両方登録していないか確認します。 |

新しい文字起こしの話者分離は未対応です。アプリに保存済みの話者ラベルはノート取得時に参照できます。アプリの追加エンジン・全対応言語をMCPから利用できるわけではありません。

## 更新と削除

v0.3.0へ更新する場合：

```bash
uv tool install --force --from git+https://github.com/msandroid/cription-mcp@v0.3.0 cription-mcp
```

AIクライアントとTunnelを再起動してください。実行パスが変わった場合は、既存設定を確認して`install CLIENT --replace`で更新します。

削除する場合は、まず各クライアントのCription登録を削除します。

- Claude Code：`claude mcp remove cription --scope user`。プラグイン経由なら`/plugin uninstall cription@cription`。
- Codex：`codex mcp remove cription`。スキルも削除する場合は`codex plugin remove cription@cription`。
- Antigravity：MCP設定から`cription`を削除。プラグイン経由ならプラグインを削除します。
- Claude Desktop：拡張を削除するか、設定JSONの`mcpServers.cription`だけを削除します。
- ChatGPT：Criptionの接続を解除し、実行中のTunnelを停止します。不要になった専用キーはPlatformで失効させます。

設定ファイルの場所：

| クライアント | 保存先 |
|---|---|
| Claude Code | `~/.claude.json` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Codex | `~/.codex/config.toml` |
| Antigravity | `~/.gemini/config/mcp_config.json` |
| 旧Antigravity IDE | `~/.gemini/antigravity/mcp_config.json` |

最後に`uv tool uninstall cription-mcp`でサーバーを削除できます。録音・ノートは削除しません。設定のバックアップ、キャッシュ、専用キーは自動削除されないため、必要性を確認してから整理してください。
