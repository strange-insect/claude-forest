# claude-forest

## マーケットプレイスの追加

```bash
# プラグインを追加
claude plugin marketplace add strange-insect/claude-forest

# 追加したプラグインを確認
claude plugin marketplace list
```

## プラグイン一覧

| プラグイン | 説明 |
|-----------|------|
| [cecropia](./plugins/cecropia/docs/README.md) | よく使う機能の基本セット |
| [aphid](./plugins/aphid/docs/README.md) | OpenAI Codex CLI 連携 |
| [treehopper](./plugins/treehopper/docs/README.md) | opencode CLI 連携 |

## インストール

```bash
# プラグインをインストール
claude plugin install cecropia@claude-forest
claude plugin install aphid@claude-forest
claude plugin install treehopper@claude-forest

# インストール済みプラグインを確認
claude plugin list
```

## 更新

```bash
# マーケットプレイスのカタログを最新化
claude plugin marketplace update claude-forest

# プラグインを更新
claude plugin update cecropia@claude-forest
claude plugin update aphid@claude-forest
claude plugin update treehopper@claude-forest

# 更新したプラグインを確認
claude plugin list
```

`/plugin` → Marketplaces タブで **auto-update** を有効にすると、起動時に自動更新される。

## ローカルで試す（セッション限定）

```bash
claude --plugin-dir /path/to/claude-forest/plugins/cecropia
claude --plugin-dir /path/to/claude-forest/plugins/aphid
claude --plugin-dir /path/to/claude-forest/plugins/treehopper
```
