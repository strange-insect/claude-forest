#!/usr/bin/env python3
"""get-pr-info: PR の情報を取得して Markdown にまとめる。

呼び出し:
    get-pr-info.py pr_number=<PR_NUMBER> [repository=<ORG/REPO>]

出力（stdout）:
    保存したファイルパスのみ。
    Markdown は <tempdir>/pull-requests/<repo>_pr_<PR_NUMBER>.md に保存。
    Diff は <tempdir>/pull-requests/<repo>_pr_<PR_NUMBER>.diff に保存。

実装方針: jq / sed 等の外部 CLI 依存を Python stdlib (json / re) に寄せる。
gh CLI のみ shell から呼び出す（GitHub API のクライアントとして利用）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def die(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def run_gh(args: list[str], *, capture: bool = True) -> str:
    """gh コマンドを起動して stdout を返す。失敗時は die する。

    gh の JSON / Markdown 出力は UTF-8 前提なので、Windows ネイティブ Python の
    locale (cp932 等) によるデコード退行を避けるため encoding を明示する。
    """
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        die("'gh' コマンドが見つかりません。GitHub CLI をインストールしてください。")
    if result.returncode != 0:
        stderr = result.stderr.strip() if capture else ""
        die(f"gh {' '.join(args)} に失敗しました。{stderr}")
    return result.stdout


def parse_args(argv: list[str]) -> tuple[str, str]:
    pr_number = ""
    repo_full = ""
    for arg in argv:
        if arg.startswith("pr_number="):
            pr_number = arg[len("pr_number=") :]
        elif arg.startswith("repository="):
            repo_full = arg[len("repository=") :]
        else:
            die(
                f"unknown argument '{arg}'\n"
                "Usage: get-pr-info.py pr_number=<PR_NUMBER> [repository=<ORG/REPO>]"
            )
    if not pr_number:
        die("Usage: get-pr-info.py pr_number=<PR_NUMBER> [repository=<ORG/REPO>]")
    if not pr_number.isdigit():
        die("PR_NUMBER must be numeric")
    return pr_number, repo_full


def gh_api_paginate(path: str) -> list[Any]:
    """gh api --paginate の結果を JSON 配列として読む。"""
    raw = run_gh(["api", "--paginate", path])
    items: list[Any] = []
    decoder = json.JSONDecoder()
    idx = 0
    text = raw.strip()
    # gh --paginate は連続した JSON ドキュメントを返すことがあるので順次デコードする
    while idx < len(text):
        # skip whitespace
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = decoder.raw_decode(text, idx)
        idx = end
        if isinstance(obj, list):
            items.extend(obj)
        else:
            items.append(obj)
    return items


def humanize_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def lift_headings(text: str) -> str:
    """コメント本文中の Markdown 見出しを +3 段下げる（# → ####）。

    サブタイトルが h3 なので、本文由来の見出しは h4 以下に潜らせる。
    """
    return re.sub(r"^(#+)", lambda m: "#" * (len(m.group(1)) + 3), text, flags=re.MULTILINE)


def status_label(status: str) -> str:
    return {"added": "A", "modified": "M", "removed": "D", "renamed": "R"}.get(
        status, status
    )


def main() -> int:
    pr_number, repo_full = parse_args(sys.argv[1:])

    if not repo_full:
        out = run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
        repo_full = out.strip()
        if not repo_full:
            die("カレントディレクトリの GitHub リポジトリを取得できませんでした")

    if "/" not in repo_full:
        die("REPO must be in 'ORG/REPO' format (e.g. myorg/myrepo)")
    org_id, _, repo_id = repo_full.partition("/")

    diff_dir = Path(tempfile.gettempdir()) / "pull-requests"
    diff_dir.mkdir(parents=True, exist_ok=True)
    repo_slug = repo_full.replace("/", "_")
    diff_file = diff_dir / f"{repo_slug}_pr_{pr_number}.diff"
    md_file = diff_dir / f"{repo_slug}_pr_{pr_number}.md"
    body_file = diff_dir / f"{repo_slug}_pr_{pr_number}_body.md"

    pr_json_text = run_gh(
        [
            "pr",
            "view",
            pr_number,
            "--repo",
            repo_full,
            "--json",
            "author,state,headRefName,baseRefName,title,body,headRefOid",
        ]
    )
    try:
        pr_json = json.loads(pr_json_text)
    except json.JSONDecodeError:
        die(f"PR #{pr_number} not found in {repo_full}")
        return 1

    branch_name = pr_json.get("headRefName", "")
    base_branch = pr_json.get("baseRefName", "")
    pr_title = pr_json.get("title", "")
    pr_body = pr_json.get("body", "") or ""
    commit_hash = pr_json.get("headRefOid", "")
    pr_state = pr_json.get("state", "")
    pr_author = (pr_json.get("author") or {}).get("login", "")

    # diff を保存（メモリスパイクを避けるため stdout を直接ファイルへ流す）
    with diff_file.open("wb") as fp:
        try:
            diff_proc = subprocess.run(
                ["gh", "pr", "diff", pr_number, "--repo", repo_full],
                stdout=fp,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError:
            die("'gh' コマンドが見つかりません。GitHub CLI をインストールしてください。")
    if diff_proc.returncode != 0:
        # 失敗時は部分書き込みされた diff_file を残さない
        diff_file.unlink(missing_ok=True)
        stderr = diff_proc.stderr.decode("utf-8", errors="replace").strip()
        die(f"gh pr diff に失敗しました。{stderr}")
    body_file.write_text(pr_body + "\n", encoding="utf-8")
    diff_size = diff_file.stat().st_size

    lines: list[str] = []

    # header
    lines.append(f"# PR #{pr_number}: {pr_title}")
    lines.append("")
    lines.append("| 項目 | 値 |")
    lines.append("| ---- | -- |")
    lines.append(f"| リポジトリ | `{org_id}/{repo_id}` |")
    lines.append(f"| 状態 | {pr_state} |")
    lines.append(f"| 作成者 | {pr_author} |")
    lines.append(f"| ブランチ   | `{branch_name}` → `{base_branch}` |")
    lines.append(f"| 最新コミット | `{commit_hash}` |")
    lines.append("")

    # PR overview
    lines.append("---")
    lines.append("")
    lines.append("## PR概要")
    lines.append("")
    lines.append(f"_本文ファイル: `{body_file}`_")
    lines.append("")

    # conversation
    lines.append("---")
    lines.append("")
    lines.append("## Conversation")
    lines.append("")
    conv = gh_api_paginate(f"repos/{org_id}/{repo_id}/issues/{pr_number}/comments")
    conv = [
        c
        for c in conv
        if isinstance(c, dict) and c.get("user", {}).get("login") != "linear[bot]"
    ]
    if not conv:
        lines.append("_コメントなし_")
    else:
        for c in conv:
            user = c.get("user", {}).get("login", "")
            created = c.get("created_at", "")
            body = c.get("body", "") or ""
            lines.append(f"### {user}  （{created}）")
            lines.append("")
            lines.append(lift_headings(body))
            lines.append("")
    lines.append("")

    # reviews
    lines.append("---")
    lines.append("")
    lines.append("## レビュー")
    lines.append("")
    reviews_raw = gh_api_paginate(f"repos/{org_id}/{repo_id}/pulls/{pr_number}/reviews")
    reviews = [
        r
        for r in reviews_raw
        if isinstance(r, dict)
        and ((r.get("body") or "") != "" or r.get("state") != "COMMENTED")
    ]
    if not reviews:
        lines.append("_レビューなし_")
    else:
        for r in reviews:
            user = r.get("user", {}).get("login", "")
            state = r.get("state", "")
            submitted = r.get("submitted_at", "")
            body = r.get("body") or ""
            lines.append(f"### {user}  （{state} / {submitted}）")
            lines.append("")
            lines.append(lift_headings(body) if body else "_（本文なし）_")
            lines.append("")
    lines.append("")

    # line comments
    lines.append("---")
    lines.append("")
    lines.append("## 行コメント")
    lines.append("")
    raw_comments = gh_api_paginate(f"repos/{org_id}/{repo_id}/pulls/{pr_number}/comments")
    comments = [c for c in raw_comments if isinstance(c, dict)]
    if not comments:
        lines.append("_コメントなし_")
    else:
        # in_reply_to_id をキーにスレッドへ束ねる。
        # 旧 shell の `jq group_by` は thread_id 昇順で出力するため、辞書挿入順ではなくキーでソートする。
        threads: dict[Any, list[dict]] = {}
        for c in comments:
            tid = c.get("in_reply_to_id") or c.get("id")
            threads.setdefault(tid, []).append(c)
        for tid in sorted(threads.keys()):
            thread = threads[tid]
            roots = [c for c in thread if c.get("in_reply_to_id") is None]
            replies = [c for c in thread if c.get("in_reply_to_id") is not None]
            if not roots:
                continue
            root = roots[0]
            user = root.get("user", {}).get("login", "")
            created = root.get("created_at", "")
            path = root.get("path", "")
            line_no = root.get("line") or root.get("original_line") or "不明"
            body = root.get("body", "") or ""
            lines.append(f"### Comment {root.get('id', '')}  （{user} / {created}）")
            lines.append("")
            lines.append("| 項目 | 値 |")
            lines.append("| ---- | -- |")
            lines.append(f"| Path | `{path}` |")
            lines.append(f"| Line | {line_no} |")
            lines.append("")
            lines.append(lift_headings(body))
            lines.append("")
            for rep in replies:
                ruser = rep.get("user", {}).get("login", "")
                rcreated = rep.get("created_at", "")
                rbody = (rep.get("body", "") or "").replace("\n", "\n> ")
                lines.append(f"> **Comment {rep.get('id', '')}**  （{ruser} / {rcreated}）")
                lines.append(">")
                lines.append(f"> {rbody}")
                lines.append("")
    lines.append("")

    # commits
    lines.append("---")
    lines.append("")
    lines.append("## コミット一覧")
    lines.append("")
    commits = gh_api_paginate(f"repos/{org_id}/{repo_id}/pulls/{pr_number}/commits")
    for c in commits:
        if not isinstance(c, dict):
            continue
        sha = (c.get("sha") or "")[:7]
        commit = c.get("commit", {}) or {}
        msg = (commit.get("message", "") or "").split("\n", 1)[0]
        author = (commit.get("author", {}) or {}).get("name", "")
        lines.append(f"- `{sha}` {msg}  （{author}）")
    lines.append("")

    # diff summary
    lines.append("---")
    lines.append("")
    lines.append("## Diff")
    lines.append("")
    lines.append("| 項目 | 値 |")
    lines.append("| ---- | -- |")
    lines.append(f"| ファイル | `{diff_file}` |")
    lines.append(f"| サイズ   | {humanize_size(diff_size)} ({diff_size} bytes) |")
    lines.append("")
    lines.append("### 変更ファイル一覧")
    lines.append("")
    lines.append("```")
    files = gh_api_paginate(f"repos/{org_id}/{repo_id}/pulls/{pr_number}/files")
    for f in files:
        if not isinstance(f, dict):
            continue
        st = status_label(f.get("status", ""))
        fn = f.get("filename", "")
        lines.append(f"{st}\t{fn}")
    lines.append("```")

    md_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Markdown saved: {md_file}")
    print(f"Body saved:     {body_file}")
    print(f"Diff saved:     {diff_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
