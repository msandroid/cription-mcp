# Cription連携：日本語インストールガイド

MCPサーバー v0.2.0／プラグイン v0.3.0。音声認識はMac上で処理します。返された文字起こし・ノート本文は接続先のAIサービスに渡ります。

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
uv tool install --from git+https://github.com/msandroid/cription-mcp@v0.2.0 cription-mcp
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

[cription-0.2.0.mcpbをダウンロード](https://github.com/msandroid/cription-mcp/releases/download/v0.2.0/cription-0.2.0.mcpb)してClaude Desktopで開くか、手順2のインストール後に実行します。

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

1. 手順2でサーバーをインストールします。
2. [OpenAI公式tunnel-client](https://github.com/openai/tunnel-client/releases/latest)のMac向け配布を入手し、`tunnel-client help quickstart`が実行できる状態にします。Apple Siliconはdarwin-arm64、Intel Macはdarwin-amd64を選びます。
3. [PlatformのTunnel設定](https://platform.openai.com/settings/organization/tunnels)でTunnelを作成し、使用するChatGPTワークスペースに関連付けます。作成にはTunnels Read・Manage、実行にはRead・Use権限が必要です。ChatGPTの契約・ワークスペース権限によって利用可否が変わります。
4. ランタイムAPIキーを作成します。権限は**Tunnels Read・Useだけ**にします。管理者キーは使いません。有効期限も設定してください。
5. 次のコマンドで表示される、このMacだけの入力画面にキーを入力します。

```bash
cription-mcp-setup chatgpt key
```

キーは`~/.config/cription-mcp/runtime-key`に権限600で保存されます。キー本文はログに残しません。既存ファイルは上書きしません。保存先を変える場合は`--key-file /absolute/path/to/key`を指定します。

6. `tunnel_YOUR_ID`を自分のIDに置き換えて実行します。

```bash
cription-mcp-setup chatgpt init --tunnel-id tunnel_YOUR_ID --key-file "$HOME/.config/cription-mcp/runtime-key"
cription-mcp-setup chatgpt doctor --key-file "$HOME/.config/cription-mcp/runtime-key"
cription-mcp-setup chatgpt run --key-file "$HOME/.config/cription-mcp/runtime-key"
```

`run`を停止するとChatGPTからの呼び出しも止まります。MacとTunnelを起動したままにしてください。既存プロファイルがある場合は別名の`--profile`を3コマンドすべてに指定します。起動を管理したい場合は、公式CLIの`runtimes connect`と`runtimes status`も利用できます。

7. ChatGPTで**Plugins → Add → Add custom MCP server**を開きます。名前を入力し、接続を**Tunnel**にして自分のIDを選びます。Cription自体の認証は**No authentication**です。Tunnel側ではキーとワークスペースの権限が使われます。
8. リスク説明を確認して作成し、**Connect → Try in chat**を実行します。

[OpenAI公式のTunnel手順](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)も参照してください。APIキーをチャットに貼り付ける必要はありません。

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

v0.2.0へ更新する場合：

```bash
uv tool install --force --from git+https://github.com/msandroid/cription-mcp@v0.2.0 cription-mcp
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
