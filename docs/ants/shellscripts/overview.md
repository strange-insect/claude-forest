# ants シェルスクリプト仕様書

ants の主要な制御はシェルスクリプトで実装する。ただし `export-session` は `agents/export-session.py` を使用し、`plant-uml` の補助スクリプトでも `python3` を使用する。

スクリプトは 2 つに分類される。

1. **plugin root の `bin/` 配下の共有スクリプト**（4 個）：複数 agent から呼び出される共通処理
2. **各 agent / skill 専用スクリプト**：その agent / skill 固有の実装（各仕様書を参照）

このドキュメントは plugin root の `bin/` 配下のみを対象とする。

## 共有スクリプト一覧

| スクリプト名 | 用途 | 主な利用元 |
|-------------|------|-----------|
| `ask-pipeline.sh` | ask 系 agent の共通パイプライン入口 | `codex-ask`, `codex-review`, `opus-ask`, `opus-review` |
| `save-ask-log.sh` | 中間 JSON を Markdown ログに変換 | `ask-pipeline.sh` |
| `translate-json.sh` | JSON 内の指定フィールドを翻訳 | `ask-pipeline.sh` |
| `get-working-set.sh` | ワーキングセット（git 変更）を取得 | `codex-review`, `opus-review` |

## 共通方針

- **bash 前提**：先頭に `set -euo pipefail`（または互換）を付ける
- **配置基準**：`${CLAUDE_PLUGIN_ROOT}/bin/` 直下
- **入出力**：stdin / 引数で受け取り、stdout に結果を返す。エラーは stderr に出して非ゼロで終了
- **副作用**：`/tmp` 配下の中間ファイルは原則として呼び出し側で削除する

## 詳細仕様

各スクリプトの詳細は以下を参照：

- [ask-pipeline.sh](ask-pipeline.md)
- [save-ask-log.sh](save-ask-log.md)
- [translate-json.sh](translate-json.md)
- [get-working-set.sh](get-working-set.md)

## agent / skill 専用スクリプト

plugin root の `bin/` 以外のスクリプトは各仕様書で扱う：

| スクリプト | 仕様書 |
|----------|--------|
| `agents/codex-ask.sh` | [codex-ask](../agents/codex-ask.md) |
| `agents/codex-review.sh` | [codex-review](../agents/codex-review.md) |
| `agents/opus-ask.sh` | [opus-ask](../agents/opus-ask.md) |
| `agents/opus-review.sh` | [opus-review](../agents/opus-review.md) |
| `agents/get-pr-info.sh` | [get-pr-info](../agents/get-pr-info.md) |
| `agents/plant-uml/{generate_puml_url,decode_puml_url,md-convert}.sh` | [plant-uml](../agents/plant-uml.md) |
| `agents/export-session.py` | [export-session](../agents/export-session.md) |
