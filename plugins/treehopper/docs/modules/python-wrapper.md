# python-wrapper

Python スクリプトを実行するための共通エントリポイント。agent・内部スクリプトからの Python 実行はすべてこの wrapper を経由する。

## 基本情報

| 項目 | 値 |
|---|---|
| 実装 | `bin/python-wrapper.sh` |
| ターゲット Python バージョン | 3.12 |
| 最低動作バージョン | 3.10 |

## 呼び出し形式

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" <script.py> [args...]
"${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" -c '<inline code>'
"${CLAUDE_PLUGIN_ROOT}/bin/python-wrapper.sh" -m <package> [args...]
```

## Python 実行環境の解決順序

起動時に以下の 2 フェーズで有効な Python 環境を探す。

### Fast path（export 済み環境の再利用）

前回実行時に export された環境変数が有効な場合はそのまま利用し、full resolution をスキップする。

| ステップ | 条件 |
|---|---|
| 1 | `TREEHOPPER_CONDA_ENV` が有効なら conda モードで即時実行 |
| 2 | `TREEHOPPER_PYTHON` が有効なら venv モードで即時実行 |

※ ask-pipeline 内の連続呼び出しでは 2 回目以降ここで終了するため full resolution は走らない。

### Full resolution（環境の新規解決）

fast path に当てはまらない場合に実行する。`TREEHOPPER_PYTHON` が設定されていたが無効だった場合は WARN を出力して次候補へ進む。

| ステップ | 条件 |
|---|---|
| 1 | `${CLAUDE_PLUGIN_DATA}/venv` が存在して有効なら `TREEHOPPER_PYTHON` に設定 |
| 2 | plugin 固有の conda 環境が存在して有効なら `TREEHOPPER_CONDA_ENV` に設定 |
| 3 | `pyenv` → `conda` → `python3` / `python` の順で新規 venv/conda env を作成（成功したら `TREEHOPPER_PYTHON` または `TREEHOPPER_CONDA_ENV` に設定） |
| 4 | いずれも失敗した場合は固定メッセージを出力して終了 |

環境が確定すると、その結果を `TREEHOPPER_PYTHON` または `TREEHOPPER_CONDA_ENV` として環境変数に export する。

venv / conda 環境が有効でないと判定された場合は自動再作成しない。

※ **「有効」の判定条件**
- `TREEHOPPER_CONDA_ENV`：変数が非空 かつ `conda` が PATH 上にある かつ その環境で Python 3.10 以上が動作する
- `TREEHOPPER_PYTHON`：
    - 実行ファイルとして存在する
    - Python 3.10 以上 かつ `venv` モジュールが利用可能
    - venv 環境の場合は `pyvenv.cfg` が存在する

## 実行モード

| モード | 実行方法 |
|---|---|
| venv モード | `TREEHOPPER_PYTHON` の値で `exec <python> <args>` |
| conda モード | `exec conda run --no-capture-output -n <env> python <args>` |

## 依存パッケージのインストール

exec 直前に `${CLAUDE_PLUGIN_ROOT}/requirements.txt` の内容を `${CLAUDE_PLUGIN_DATA}/requirements.txt`（インストール済みスナップショット）と比較し、差異があれば `pip install -r requirements.txt` を実行してスナップショットを更新する。

| 状態 | 動作 |
|---|---|
| `requirements.txt` が存在しない | 何もしない |
| スナップショットと内容が一致 | skip（毎回のオーバーヘッドなし） |
| スナップショットと内容が異なる（初回・更新時） | pip install → スナップショット上書き |

※ pip install が失敗した場合は `WARN` を stderr に出力して処理を続行する（ソフトフェイル）。

## 環境変数

| 変数 | 用途 |
|---|---|
| `CLAUDE_PLUGIN_ROOT` | 必須。wrapper 自身の位置の基準（未設定時は即終了） |
| `CLAUDE_PLUGIN_DATA` | プラグイン固有データディレクトリ。python実行環境(venv等)の管理に使用 |

## エラーメッセージ

| 状況 | メッセージ |
|---|---|
| 有効な Python が PATH 上に見つからない | `Python runtime for this plugin could not be prepared. Install pyenv, conda, python3, or python and make it available on PATH.` |
| 環境作成に失敗した | `Python runtime for this plugin could not be prepared. Failed to create the plugin Python environment.` |
