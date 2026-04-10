# claude-general-plugins

個人的によく使う機能をまとめた Claude Code プラグイン集。

## 導入方法

### マーケットプレイスとして追加

```bash
/plugin marketplace add your-name/claude-general-plugins
```

### プラグインをインストール

```bash
/plugin install my-plugin@your-name-claude-general-plugins
```

### ローカルで試す

```bash
claude --plugin-dir /path/to/claude-general-plugins
```

## 構成

```
claude-general-plugins/
├── .claude-plugin/
│   ├── plugin.json        # プラグインのメタデータ
│   └── marketplace.json   # マーケットプレイス定義
├── skills/                # スキル（/コマンド名 で呼び出せるカスタムコマンド）
│   └── my-skill/
│       └── SKILL.md
├── hooks/                 # フックスクリプト
│   └── my-hook.sh
└── hooks.json             # フック設定
```

## スキル一覧

| スキル名 | 説明 |
|---------|------|
| `my-skill` | （説明を記入）|

## フック一覧

| フック名 | イベント | 説明 |
|---------|--------|------|
| `my-hook` | `PreToolUse` | （説明を記入）|
