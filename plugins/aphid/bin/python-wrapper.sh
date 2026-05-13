#!/usr/bin/env bash
# python-wrapper.sh — 共通 Python wrapper
#
# 受け取った引数を確定済みの Python 実行環境で実行する単一の入口。
# hook / agent / skill / 内部スクリプトからの Python 実行は必ずこの wrapper を経由する
#
# 呼び出し位置の解決には `${CLAUDE_PLUGIN_ROOT}` を使う。
# hook / MCP / LSP subprocess には公式に export 保証があり、agent / skill content から呼ぶ
# 場合も inline 置換で literal なパスとして展開される。未 set は呼び出し経路の異常なので fail-fast。
#
# 使い方:
#   python-wrapper.sh <python script>.py [args...]
#   python-wrapper.sh -c '<inline code>'
#   python-wrapper.sh -m <package> <subcommand> [args...]
#
# 戻り値: 起動した Python プロセスの exit code を propagate する (exec 経由)。
#
# `<PLUGIN>_PYTHON` / `<PLUGIN>_CONDA_ENV` の確定手順:
#   1. <PLUGIN>_PYTHON が既に set かつ §2.5 検証を満たすならそのまま使う (override / cache)
#   2. ${CLAUDE_PLUGIN_DATA}/venv が存在し §2.5 を満たすならその Python を使う
#      (壊れた venv は recreate せず §2.7 setup-failed で終了。recovery は <PLUGIN>_PYTHON override)
#   3. <PLUGIN>_CONDA_ENV が既に set かつ検証を満たすならそのまま使う (cache)
#   4. plugin 固有の conda 環境が存在し検証を満たすならその環境を使う
#   5. 再利用できる環境が無ければ §2.4 の優先順位で新規作成する:
#      pyenv → install target version + venv 作成
#      conda → conda 環境作成
#      python3/python → venv 作成
#   6. どの段階でも有効な実行環境を得られなければ §2.7 固定メッセージで終了する
#
# 実行モードは venv と conda の 2 種:
#   - venv モード: ${CLAUDE_PLUGIN_DATA}/venv の Python で exec
#   - conda モード: conda run -n <env-name> python で exec

set -euo pipefail

# Plugin が使う Python target version
_PW_PYTHON_TARGET_VERSION="3.12"
# Plugin 固有の conda 環境名
_PW_CONDA_ENV_NAME="aphid-plugin"
# export する環境変数名（プロセス境界を越えるキャッシュキー）
_PW_PYTHON_VAR="APHID_PYTHON"
_PW_CONDA_ENV_VAR="APHID_CONDA_ENV"

# CLAUDE_PLUGIN_ROOTが未設定ならエラー。
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}"

# §2.7 固定メッセージ（plugin ごとに考えさせず指定文言に固定する）
_pw_print_no_runtime() {
  cat >&2 <<'MSG'
Python runtime for this plugin could not be prepared.
Install pyenv, conda, python3, or python and make it available on PATH.
MSG
}

_pw_print_setup_failed() {
  cat >&2 <<'MSG'
Python runtime for this plugin could not be prepared.
Failed to create the plugin Python environment.
MSG
}

# 候補検証
#
# shell 層 (本関数):
#   - sentinel 出力: `__plugin_python_ok__` を返す本物の Python interpreter か
#     (Windows の Microsoft Store stub や `true` shim を排除)
#   - version の早期チェック: `sys.version_info >= (3, 10)`
# Python 層 (_runtime_check.py):
#   - §2.3 の 4 条件 (ファイル存在 / version / venv / sentinel) を再検証
#
# Python 側は `sys.stdout.write` を使う (Windows native の `print()` は末尾に \r\n を
# 付けるため)。bash $(...) は trailing \n しか落とさないので、念のため shell 側でも
# `${out%$'\r'}` で CR を剥がす。
#
# 第2引数に "base" を渡すと _runtime_check.py に --base を渡し、venv 整合性チェックを
# スキップする (base Python 候補は venv 配下でないため pyvenv.cfg が存在しない)。
_pw_validate_python() {
  local candidate="$1" mode="${2:-}" out runtime_args
  [[ -z "$candidate" ]] && return 1
  out="$("$candidate" -c 'import sys; sys.stdout.write("__plugin_python_ok__"); sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null)" || return 1
  [[ "${out%$'\r'}" == "__plugin_python_ok__" ]] || return 1
  runtime_args=("$candidate")
  [[ "${mode}" == "base" ]] && runtime_args+=("--base")
  "$candidate" "${CLAUDE_PLUGIN_ROOT}/bin/_runtime_check.py" "${runtime_args[@]}" >/dev/null 2>&1
}

# conda 環境の検証
# conda run の exit code は信頼できない場合がある (conda/conda#9599) ため
# sentinel 出力のみで判定する。
_pw_validate_conda_env() {
  local env_name="$1" out
  out="$(conda run -n "${env_name}" python -c \
    'import sys; sys.stdout.write("__plugin_python_ok__" if sys.version_info >= (3, 10) else "")' \
    2>/dev/null)" || true
  [[ "${out%$'\r'}" == "__plugin_python_ok__" ]]
}

# conda 環境の存在確認
_pw_conda_env_exists() {
  local env_name="$1"
  conda env list 2>/dev/null | grep -q "^${env_name}[[:space:]]"
}

# venv レイアウト (POSIX → Windows) から Python 実行ファイルを探す
_pw_locate_venv_python() {
  local venv_root="$1" rel
  for rel in bin/python3 bin/python Scripts/python.exe; do
    if [[ -f "${venv_root}/${rel}" ]]; then
      printf '%s' "${venv_root}/${rel}"
      return 0
    fi
  done
  return 1
}

# pyenv から plugin target version の Python を取得する
# 未インストールの場合は pyenv install を試みる。
# .python-version の影響を受けないよう PYENV_VERSION で明示指定する。
#
# pyenv-win 互換性:
#   - `pyenv versions --bare` が使えない場合 `pyenv versions` をパースする
#   - `pyenv install -s` が使えない場合 `pyenv install` にフォールバック
_pw_pyenv_find_python() {
  local installed_ver install_ver candidate shim target_re

  # 正規表現用に . をエスケープ (3.12 → 3\.12)
  target_re="${_PW_PYTHON_TARGET_VERSION//./\\.}"

  # 既にインストール済みの target version を探す
  # pyenv versions --bare が使えない場合は pyenv versions をパース
  installed_ver="$(
    { pyenv versions --bare 2>/dev/null \
      || pyenv versions 2>/dev/null | sed 's/^[* ]*//' | sed 's/ .*//'; } \
    | grep -E "^${target_re}\.[0-9]+$" | tail -1
  )" || true

  if [[ -z "${installed_ver}" ]]; then
    # 利用可能な最新パッチ version を特定してインストール
    install_ver="$(pyenv install -l 2>/dev/null \
      | sed 's/^[[:space:]]*//' \
      | grep -E "^${target_re}\.[0-9]+$" | tail -1)" || true
    [[ -z "${install_ver}" ]] && return 1
    # -s (skip-existing) は pyenv-win で未サポートの場合があるためフォールバック
    pyenv install -s "${install_ver}" >/dev/null 2>&1 \
      || pyenv install "${install_ver}" >/dev/null 2>&1 \
      || return 1
    installed_ver="${install_ver}"
  fi

  # PYENV_VERSION で .python-version を上書きして python path を取得
  for shim in python3 python; do
    candidate="$(PYENV_VERSION="${installed_ver}" pyenv which "${shim}" 2>/dev/null || true)"
    if _pw_validate_python "${candidate}" base; then
      printf '%s' "${candidate}"
      return 0
    fi
  done
  return 1
}

# <PLUGIN>_PYTHON / <PLUGIN>_CONDA_ENV の確定
# 成功時: <PLUGIN>_PYTHON (venv モード) または <PLUGIN>_CONDA_ENV (conda モード) を設定する。
# 親シェルで直接呼び出すこと ($() 経由で呼ぶとサブシェルになり変数が伝搬しない)。
_pw_resolve_python() {
  local preset_python="${!_PW_PYTHON_VAR:-}" candidate base venv_root cmd found_any_base=false

  unset "${_PW_PYTHON_VAR}" "${_PW_CONDA_ENV_VAR}"

  # 1. 既存 <PLUGIN>_PYTHON (env override or cache)
  if [[ -n "${preset_python}" ]]; then
    if _pw_validate_python "${preset_python}"; then
      printf -v "${_PW_PYTHON_VAR}" '%s' "${preset_python}"
      return 0
    fi
    printf "WARN: %s='%s' is not a valid Python 3.10+ interpreter; falling through\n" "${_PW_PYTHON_VAR}" "${preset_python}" >&2
  fi

  if [[ -z "${CLAUDE_PLUGIN_DATA:-}" ]]; then
    cat >&2 <<'MSG'
Python runtime for this plugin could not be prepared.
CLAUDE_PLUGIN_DATA is not set. Ensure the plugin data directory is available
(e.g. export CLAUDE_PLUGIN_DATA in the agent prompt).
MSG
    return 1
  fi
  venv_root="${CLAUDE_PLUGIN_DATA}/venv"

  # 2. 既存 plugin venv (§2.3 step 1)
  if candidate="$(_pw_locate_venv_python "${venv_root}")"; then
    if _pw_validate_python "${candidate}"; then
      printf -v "${_PW_PYTHON_VAR}" '%s' "${candidate}"
      return 0
    fi
    # 壊れた venv は recreate しない (§1.3 recovery via <PLUGIN>_PYTHON override)
    _pw_print_setup_failed
    return 1
  fi

  # 3. 既存 plugin conda 環境 (§2.3 step 2)
  if command -v conda >/dev/null 2>&1; then
    if _pw_conda_env_exists "${_PW_CONDA_ENV_NAME}"; then
      if _pw_validate_conda_env "${_PW_CONDA_ENV_NAME}"; then
        printf -v "${_PW_CONDA_ENV_VAR}" '%s' "${_PW_CONDA_ENV_NAME}"
        return 0
      fi
      # 壊れた conda 環境は recreate しない
      _pw_print_setup_failed
      return 1
    fi
  fi

  # 4. 新規環境作成 (§2.4)

  # 4a. pyenv → target version を install し venv 作成
  if command -v pyenv >/dev/null 2>&1; then
    if base="$(_pw_pyenv_find_python)"; then
      found_any_base=true
      rm -rf "${venv_root}" 2>/dev/null || true
      rm -f "${CLAUDE_PLUGIN_DATA}/requirements.txt" 2>/dev/null || true
      if "${base}" -m venv "${venv_root}" >/dev/null 2>&1; then
        if candidate="$(_pw_locate_venv_python "${venv_root}")"; then
          if _pw_validate_python "${candidate}"; then
            printf -v "${_PW_PYTHON_VAR}" '%s' "${candidate}"
            return 0
          fi
        fi
        # 作成直後の venv が壊れている → 片付けて次候補へ
        rm -r "${venv_root}" 2>/dev/null || true
      fi
    fi
  fi

  # 4b. conda → plugin 固有の conda 環境を作成
  if command -v conda >/dev/null 2>&1; then
    found_any_base=true
    rm -rf "${venv_root}" 2>/dev/null || true
    rm -f "${CLAUDE_PLUGIN_DATA}/requirements.txt" 2>/dev/null || true
    if conda create -y -q -n "${_PW_CONDA_ENV_NAME}" "python=${_PW_PYTHON_TARGET_VERSION}" >/dev/null 2>&1; then
      if _pw_validate_conda_env "${_PW_CONDA_ENV_NAME}"; then
        printf -v "${_PW_CONDA_ENV_VAR}" '%s' "${_PW_CONDA_ENV_NAME}"
        return 0
      fi
      # 作成直後の conda 環境が壊れている → 片付けて次候補へ
      conda env remove -y -n "${_PW_CONDA_ENV_NAME}" >/dev/null 2>&1 || true
    fi
  fi

  # 4c-d. PATH 上の python3 / python → venv 作成
  #       python3 を先に試すのは macOS / 古い Linux で `python` が 2.x を指す環境に備えるため。
  for cmd in python3 python; do
    base="$(command -v "${cmd}" 2>/dev/null || true)"
    if _pw_validate_python "${base}" base; then
      found_any_base=true
      rm -rf "${venv_root}" 2>/dev/null || true
      rm -f "${CLAUDE_PLUGIN_DATA}/requirements.txt" 2>/dev/null || true
      if "${base}" -m venv "${venv_root}" >/dev/null 2>&1; then
        if candidate="$(_pw_locate_venv_python "${venv_root}")"; then
          if _pw_validate_python "${candidate}"; then
            printf -v "${_PW_PYTHON_VAR}" '%s' "${candidate}"
            return 0
          fi
        fi
        rm -r "${venv_root}" 2>/dev/null || true
      fi
    fi
  done

  if "${found_any_base}"; then
    _pw_print_setup_failed
  else
    _pw_print_no_runtime
  fi
  return 1
}

# plugin requirements のインストール (requirements.txt が存在する場合のみ)
# ${CLAUDE_PLUGIN_DATA}/requirements.txt をインストール済み状態のスナップショットとして使う。
# プラグインの requirements.txt と内容が一致すれば skip、異なれば pip install して上書きコピーする。
_pw_install_requirements() {
  local req_file="${CLAUDE_PLUGIN_ROOT}/requirements.txt"
  [[ -f "${req_file}" ]] || return 0
  [[ -z "${CLAUDE_PLUGIN_DATA:-}" ]] && return 0

  local installed_req="${CLAUDE_PLUGIN_DATA}/requirements.txt"
  cmp -s "${req_file}" "${installed_req}" && return 0

  if [[ -n "${!_PW_CONDA_ENV_VAR:-}" ]]; then
    conda run -n "${!_PW_CONDA_ENV_VAR}" python -m pip install \
      -r "${req_file}" -q >/dev/null 2>&1 \
      || { printf 'WARN: pip install failed; some features may be unavailable\n' >&2; return 0; }
  elif [[ -n "${!_PW_PYTHON_VAR:-}" ]]; then
    "${!_PW_PYTHON_VAR}" -m pip install \
      -r "${req_file}" -q >/dev/null 2>&1 \
      || { printf 'WARN: pip install failed; some features may be unavailable\n' >&2; return 0; }
  else
    return 0
  fi

  cp "${req_file}" "${installed_req}"
}

# Fast paths: 既に確定済みの環境が valid なら再利用する。
# 子プロセスへの export で連続呼び出しでは 1 回目以降 resolve が走らない。
if [[ -n "${!_PW_CONDA_ENV_VAR:-}" ]] && command -v conda >/dev/null 2>&1 \
   && _pw_validate_conda_env "${!_PW_CONDA_ENV_VAR}"; then
  _pw_install_requirements
  exec conda run -n "${!_PW_CONDA_ENV_VAR}" python "$@"
fi
if [[ -n "${!_PW_PYTHON_VAR:-}" ]] && _pw_validate_python "${!_PW_PYTHON_VAR}"; then
  _pw_install_requirements
  exec "${!_PW_PYTHON_VAR}" "$@"
fi

# Full resolution
if ! _pw_resolve_python; then
  exit 1
fi

if [[ -n "${!_PW_CONDA_ENV_VAR:-}" ]]; then
  export "${_PW_CONDA_ENV_VAR}"
  unset "${_PW_PYTHON_VAR}"
  _pw_install_requirements
  exec conda run -n "${!_PW_CONDA_ENV_VAR}" python "$@"
fi

export "${_PW_PYTHON_VAR}"
unset "${_PW_CONDA_ENV_VAR}"
_pw_install_requirements
exec "${!_PW_PYTHON_VAR}" "$@"
