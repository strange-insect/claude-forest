# ants シェルスクリプト仕様書

ants の主要な制御はシェルスクリプトで実装する。ただし `export-session` は `scripts/export_session.py` を使用し、`plant-uml` の補助スクリプトでも `python3` を使用する。

スクリプトは 2 つに分類される。

1. **`_shared-bin/` 配下の共有スクリプト**（4 個）：複数スキルから呼び出される共通処理
2. **各スキルの `bin/` 配下スクリプト**：そのスキル専用の実装（各スキル仕様書を参照）

このドキュメントは `_shared-bin/` 配下のみを対象とする。

## 共有スクリプト一覧

| スクリプト名 | 用途 | 主な利用元 |
|-------------|------|-----------|
| `ask-pipeline.sh` | ask 系スキルの共通パイプライン入口 | `codex-ask`, `codex-review`, `opus-ask`, `opus-review` |
| `save-ask-log.sh` | 中間 JSON を Markdown ログに変換 | `ask-pipeline.sh` |
| `translate-json.sh` | JSON 内の指定フィールドを翻訳 | `ask-pipeline.sh` |
| `get-working-set.sh` | ワーキングセット（git 変更）を取得 | `codex-review`, `opus-review` |

## 共通方針

- **bash 前提**：先頭に `set -euo pipefail`（または互換）を付ける
- **配置基準**：`${CLAUDE_PLUGIN_ROOT}/skills/_shared-bin/` 直下
- **入出力**：stdin / 引数で受け取り、stdout に結果を返す。エラーは stderr に出して非ゼロで終了
- **副作用**：`/tmp` 配下の中間ファイルは原則として呼び出し側で削除する

## 詳細仕様

各スクリプトの詳細は以下を参照：

- [ask-pipeline.sh](ask-pipeline.md)
- [save-ask-log.sh](save-ask-log.md)
- [translate-json.sh](translate-json.md)
- [get-working-set.sh](get-working-set.md)

## スキル専用スクリプト

`_shared-bin/` 以外のスクリプトは各スキル仕様書で扱う：

| スクリプト | スキル仕様書 |
|----------|------------|
| `skills/codex-ask/bin/run-codex-ask.sh` | [codex-ask](../skills/codex-ask.md) |
| `skills/codex-review/bin/run-codex-review.sh` | [codex-review](../skills/codex-review.md) |
| `skills/opus-ask/bin/run-opus-ask.sh` | [opus-ask](../skills/opus-ask.md) |
| `skills/opus-review/bin/run-opus-review.sh` | [opus-review](../skills/opus-review.md) |
| `skills/get-pr-info/bin/run-get-pr-info.sh` | [get-pr-info](../skills/get-pr-info.md) |
| `skills/plant-uml/bin/{generate_puml_url,decode_puml_url,md-convert}.sh` | [plant-uml](../skills/plant-uml.md) |
| `scripts/export_session.py` | [export-session](../skills/export-session.md) |
