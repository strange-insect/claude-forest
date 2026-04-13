#!/usr/bin/env bash
# get-pr-info: Retrieve PR information and format as Markdown
#
# Usage:
#   get-pr-info.sh <PR_NUMBER>            # カレントディレクトリのリポジトリを使用
#   get-pr-info.sh <ORG/REPO> <PR_NUMBER>
#
# Output (stdout):
#   Saved file paths only
#   Markdown は /tmp/pull-requests/<repo>_pr_<PR_NUMBER>.md に保存
#   Diff は /tmp/pull-requests/<repo>_pr_<PR_NUMBER>.diff に保存

set -euo pipefail

# ---- args ----
if [[ $# -ne 1 && $# -ne 2 ]]; then
  echo "Usage: $0 [<ORG/REPO>] <PR_NUMBER>" >&2
  exit 1
fi

if [[ $# -eq 1 ]]; then
  PR_NUMBER="$1"
  REPO_FULL=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null) || {
    echo "Error: カレントディレクトリの GitHub リポジトリを取得できませんでした" >&2
    exit 1
  }
else
  REPO_FULL="$1"
  PR_NUMBER="$2"
fi

if [[ ! "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "Error: PR_NUMBER must be numeric" >&2
  exit 1
fi
DIFF_DIR="/tmp/pull-requests"
REPO_SLUG="${REPO_FULL//\//_}"
DIFF_FILE="${DIFF_DIR}/${REPO_SLUG}_pr_${PR_NUMBER}.diff"
MD_FILE="${DIFF_DIR}/${REPO_SLUG}_pr_${PR_NUMBER}.md"
BODY_FILE="${DIFF_DIR}/${REPO_SLUG}_pr_${PR_NUMBER}_body.md"

if [[ "$REPO_FULL" != */* ]]; then
  echo "Error: REPO must be in 'ORG/REPO' format (e.g. myorg/myrepo)" >&2
  exit 1
fi

ORG_ID="${REPO_FULL%%/*}"
REPO_ID="${REPO_FULL##*/}"

# ---- branch / commit / body ----
PR_JSON=$(gh pr view "$PR_NUMBER" --repo "$REPO_FULL" --json headRefName,baseRefName,title,body,headRefOid 2>/dev/null) || {
  echo "Error: PR #${PR_NUMBER} not found in ${REPO_FULL}" >&2
  exit 1
}
BRANCH_NAME=$(echo "$PR_JSON" | jq -r '.headRefName')
BASE_BRANCH=$(echo "$PR_JSON" | jq -r '.baseRefName')
PR_TITLE=$(echo "$PR_JSON" | jq -r '.title')
PR_BODY=$(echo "$PR_JSON" | jq -r '.body')
COMMIT_HASH=$(echo "$PR_JSON" | jq -r '.headRefOid')

# ---- save diff to file ----
mkdir -p "$DIFF_DIR"
gh pr diff "$PR_NUMBER" --repo "$REPO_FULL" > "$DIFF_FILE"
echo "${PR_BODY}" > "$BODY_FILE"
DIFF_SIZE=$(wc -c < "$DIFF_FILE")
DIFF_SIZE_HUMAN=$(awk "BEGIN { x=${DIFF_SIZE}; if(x>=1048576) printf \"%.1f MB\",x/1048576; else if(x>=1024) printf \"%.1f KB\",x/1024; else printf \"%d B\",x }")

# ---- generate markdown (stdout + file) ----
generate_markdown() {
  # header
  echo "# PR #${PR_NUMBER}: ${PR_TITLE}"
  echo ""
  echo "| 項目 | 値 |"
  echo "| ---- | -- |"
  echo "| リポジトリ | \`${ORG_ID}/${REPO_ID}\` |"
  echo "| ブランチ   | \`${BRANCH_NAME}\` → \`${BASE_BRANCH}\` |"
  echo "| 最新コミット | \`${COMMIT_HASH}\` |"
  echo ""

  # PR overview
  echo "---"
  echo ""
  echo "## PR概要"
  echo ""
  echo "_本文ファイル: \`${BODY_FILE}\`_"
  echo ""

  # conversation (issue comments)
  echo "---"
  echo ""
  echo "## Conversation"
  echo ""
  CONV=$(gh api --paginate "repos/${ORG_ID}/${REPO_ID}/issues/${PR_NUMBER}/comments" \
    | jq -s '[.[][] | select(.user.login != "linear[bot]")]')
  CONV_COUNT=$(echo "$CONV" | jq 'length')

  if [[ "$CONV_COUNT" -eq 0 ]]; then
    echo "_コメントなし_"
  else
    echo "$CONV" | jq -r '.[] | "### \(.user.login)  （\(.created_at)）\n\n" + .body + "\n"' \
      | sed 's/^#/###/'
  fi
  echo ""

  # reviews
  echo "---"
  echo ""
  echo "## レビュー"
  echo ""
  REVIEWS=$(gh api --paginate "repos/${ORG_ID}/${REPO_ID}/pulls/${PR_NUMBER}/reviews" \
    | jq -s '[.[][] | select((.body // "") != "" or .state != "COMMENTED")]')
  REVIEW_COUNT=$(echo "$REVIEWS" | jq 'length')

  if [[ "$REVIEW_COUNT" -eq 0 ]]; then
    echo "_レビューなし_"
  else
    echo "$REVIEWS" | jq -r '.[] |
      "### \(.user.login)  （\(.state) / \(.submitted_at)）\n" +
      "\n" +
      (if (.body // "") == "" then "_（本文なし）_" else .body end) +
      "\n"' | sed 's/^#/###/'
  fi
  echo ""

  # line comments
  echo "---"
  echo ""
  echo "## 行コメント"
  echo ""
  COMMENTS=$(gh api --paginate "repos/${ORG_ID}/${REPO_ID}/pulls/${PR_NUMBER}/comments" | jq -s '[.[][]]')
  COMMENT_COUNT=$(echo "$COMMENTS" | jq 'length')

  if [[ "$COMMENT_COUNT" -eq 0 ]]; then
    echo "_コメントなし_"
  else
    echo "$COMMENTS" | jq -r '
      map(. + {thread_id: (.in_reply_to_id // .id)}) |
      group_by(.thread_id) |
      .[] |
      ( (map(select(.in_reply_to_id == null))[0]) as $root |
        (map(select(.in_reply_to_id != null))) as $replies |
        "### Comment \($root.id)  （\($root.user.login) / \($root.created_at)）\n" +
        "\n" +
        "| 項目 | 値 |\n" +
        "| ---- | -- |\n" +
        "| Path | `\($root.path)` |\n" +
        "| Line | \((($root.line // $root.original_line) // "不明") | tostring) |\n" +
        "\n" +
        $root.body +
        "\n" +
        if ($replies | length) > 0 then
          "\n" + ($replies | map(
            "> **Comment \(.id)**  （\(.user.login) / \(.created_at)）\n>\n> " + (.body | gsub("\n"; "\n> ")) + "\n"
          ) | join("\n"))
        else "" end
      )'
  fi
  echo ""

  # commits
  echo "---"
  echo ""
  echo "## コミット一覧"
  echo ""
  gh api --paginate "repos/${ORG_ID}/${REPO_ID}/pulls/${PR_NUMBER}/commits" \
    | jq -rs '.[][] | "- `\(.sha[0:7])` \(.commit.message | split("\n")[0])  （\(.commit.author.name)）"'
  echo ""

  # diff summary
  echo "---"
  echo ""
  echo "## Diff"
  echo ""
  echo "| 項目 | 値 |"
  echo "| ---- | -- |"
  echo "| ファイル | \`${DIFF_FILE}\` |"
  echo "| サイズ   | ${DIFF_SIZE_HUMAN} (${DIFF_SIZE} bytes) |"
  echo ""
  echo "### 変更ファイル一覧"
  echo ""
  echo '```'
  gh api --paginate "repos/${ORG_ID}/${REPO_ID}/pulls/${PR_NUMBER}/files" \
    | jq -rs '.[][] | "\(.status)\t\(.filename)"' \
    | sed 's/^added\t/A\t/; s/^modified\t/M\t/; s/^removed\t/D\t/; s/^renamed\t/R\t/'
  echo '```'
}

generate_markdown > "$MD_FILE"
echo "Markdown saved: ${MD_FILE}"
echo "Body saved:     ${BODY_FILE}"
echo "Diff saved:     ${DIFF_FILE}"
