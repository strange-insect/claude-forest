#!/usr/bin/env bash
# get-working-set.sh
# ワーキングセット（staged + unstaged + untracked）のファイル一覧を出力する
# 重複は除去して stdout に1行ずつ返す
set -euo pipefail

{
  git diff --name-only 2>/dev/null
  git diff --name-only --cached 2>/dev/null
  git ls-files --others --exclude-standard 2>/dev/null
} | sort -u | grep -v '^$' || true
