# claude-forest

[strange-insect](https://github.com/strange-insect) の Claude Code プラグイン集。

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
| [ants](./plugins/ants/README.md) | よく使う機能の基本セット |
| [silverfish](./plugins/silverfish/README.md) | 作業記録・タスク管理 |

## インストール

```bash
# プラグインをインストール
claude plugin install ants@claude-forest
claude plugin install silverfish@claude-forest

# インストール済みプラグインを確認
claude plugin list
```

## 更新

```bash
# マーケットプレイスのカタログを最新化
claude plugin marketplace update claude-forest

# プラグインを更新
claude plugin update ants@claude-forest
claude plugin update silverfish@claude-forest

# 更新したプラグインを確認
claude plugin list
```

`/plugin` → Marketplaces タブで **auto-update** を有効にすると、起動時に自動更新される。

## ローカルで試す（セッション限定）

```bash
claude --plugin-dir /path/to/claude-forest/plugins/ants
```
