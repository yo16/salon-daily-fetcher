# Salon.JP Daily Fetcher

Salon.JP の会員ページに自動ログインし、特定サロンの**記事一覧と本文テキスト**を毎日取得して、ローカルに蓄積・アーカイブする個人向けツールです。Windows のショートカットから起動し、原則無人で取得・保存して終了します。

- 詳細仕様: [`docs/requirements.md`](docs/requirements.md)（要件定義 v1.0）
- 設計: [`docs/design.md`](docs/design.md)（設計 v1.0）

> **利用範囲**: 本ツールは、利用者本人が正規に閲覧権限を持つコンテンツを私的にアーカイブ／閲覧効率化する目的に限定します。コンテンツの再配布は行わず、過剰アクセスを避け、サイトの利用規約に反しない範囲で利用してください。

---

## 1. 必要環境

- Windows 10 / 11
- conda（Anaconda / Miniconda）
- Python 3.11 以上（動作確認は 3.14）

## 2. セットアップ

### 2.1 conda 環境の作成と有効化
```powershell
conda create -n 202606_salon_fetcher python=3.12 -y
conda activate 202606_salon_fetcher
```
> 環境名は任意ですが、`run.bat` の既定は `202606_salon_fetcher` です。別名にする場合は `run.bat` の `CONDA_ENV` か、環境変数 `SDF_PYTHON`（python.exe のフルパス）で上書きしてください。

### 2.2 依存パッケージの導入
```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```
> 開発・テストも行う場合は `python -m pip install -r requirements-dev.txt`（pytest を含む）。

## 3. 設定

設定は2ファイルに分かれます。**秘密情報は `.env.local`、それ以外は `config.yaml`**。

### 3.1 認証情報 `.env.local`（コミット禁止）
雛形をコピーして実値を入れます。
```powershell
copy .env.local.example .env.local
```
```
SALON_EMAIL=あなたのメールアドレス
SALON_PASSWORD=あなたのパスワード
```
`.env.local` は `.gitignore` 済みです。**絶対にコミットしないでください。**

### 3.2 取得設定 `config.yaml`
`<...>` のプレースホルダを、**ログイン後の実画面を確認して実値に置き換えます**（残っていると起動時に設定エラーで停止します）。

| キー | 説明 |
|---|---|
| `list_url` | 取得対象サロンの記事一覧ページURL |
| `selectors.logged_in_mark` | ログイン後にだけ表示される要素（ログイン判定に使用） |
| `selectors.list_item` | 一覧の各記事の繰り返し単位 |
| `selectors.item_link` / `item_title` / `item_date` | 各記事のリンク / タイトル / 日時 |
| `selectors.body` | 記事ページの本文コンテナ |

セレクタの調べ方: ブラウザで対象ページを開き、開発者ツール（F12）で要素を選択 → コピー → 「セレクターをコピー」。サイト構造が変わったときも、この `config.yaml` を直すだけで復旧でき、本体コードの修正は不要です。

その他の主な動作設定（既定値）: `headless: true` / `timeout_ms: 15000` / `throttle_seconds: 2`（記事間の待機）/ `max_items_per_run: 50`（1実行の本文取得上限）/ `output_csv: false` / `body_as_markdown: false`。

## 4. 実行

### 4.1 コマンドで実行
```powershell
python -m src.main
```

### 4.2 ショートカットから実行（推奨）
1. エクスプローラで `run.bat` を右クリック → 「ショートカットの作成」
2. 作成したショートカットをデスクトップへ移動
3. ダブルクリックで起動 → 自動でログイン・取得・保存して終了

`run.bat` は conda 環境の Python を自動で見つけて `python -m src.main` を実行します。エラー時はログの場所を表示して一時停止します（自動実行時は環境変数 `SDF_NO_PAUSE=1` で無効化）。

## 5. 出力物

すべて `data/` 配下に蓄積されます（`.gitignore` 済み）。

| 出力 | 形式 | 用途 |
|---|---|---|
| `data/index.json` | JSON | 取得済み記事の管理マスタ（id をキーに累積マージ・履歴保持） |
| `data/articles/<日付>/<id>.md` | Markdown | 本文（人が読む用。先頭にメタ情報のフロントマター） |
| `data/corpus.jsonl` | JSONL | AI/LLM 取り込み用（1行1記事 `{id,title,date,url,body}`） |
| `data/index.csv` | CSV | 一覧の表計算用（`output_csv: true` のときのみ生成） |

取得は「当日から過去へ遡り、未取得分のみ」。何度実行しても重複せず、前回の続きから蓄積されます（冪等）。

## 6. ログとトラブルシュート

- 実行ログ: `logs/run-YYYY-MM-DD.log`（日次）＋ コンソール出力。末尾に取得件数のサマリが出ます。
- 失敗時のデバッグ成果物: `logs/debug/<時刻>/` にスクリーンショットとページHTMLを保存します（`save_debug_on_error: true` のとき）。

### 終了コード
| コード | 意味 | 対処 |
|---|---|---|
| 0 | 成功（部分成功含む。詳細はログの `status`） | — |
| 1 | 想定外のエラー | ログ・デバッグ成果物を確認 |
| 2 | 設定 / 認証エラー | `config.yaml` のプレースホルダ未設定や `.env.local` の不備を確認 |
| 3 | ログイン失敗 | 認証情報、`login_*`/`logged_in_mark` セレクタを確認 |
| 4 | 多重起動 | 別の実行が動作中。終了後に再実行（`data/.lock`） |

### よくある停止理由
- **「プレースホルダ '<...>' が未設定です」**: `config.yaml` の `<...>` を実値に置き換えてください。
- **ログイン後要素が表示されません**: `logged_in_mark` セレクタが実画面と一致しているか確認してください。

## 7. 開発（テスト）

サイト非依存の純粋ロジックは pytest で検証できます。
```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

## 8. ディレクトリ構成

```
salon-daily-fetcher/
├─ src/            # 本体（main / config / session / fetch / output / logger / models / textutil）
├─ tests/          # pytest（サイト非依存ロジック）
├─ config.yaml     # URL・セレクタ・動作設定（秘密情報は含めない）
├─ .env.local      # 認証情報（コミット禁止）
├─ data/           # 出力（index.json / articles / corpus.jsonl）※gitignore
├─ logs/           # ログ・デバッグ成果物 ※gitignore
├─ session/        # ログインセッション（storage state）※gitignore
├─ run.bat         # 起動スクリプト（ショートカットから実行）
└─ docs/           # requirements.md / design.md
```

## 9. 仕組み（概要）

1. `.env.local` を読み込み、保存済みセッションがあれば復元（無ければ自動ログインしてセッション保存）
2. `list_url` の一覧から各記事のメタ（タイトル/日時/URL）を抽出
3. `index.json` と突き合わせ、当日から過去へ遡って未取得分のみ本文を取得（上限件数まで・記事間は待機）
4. 本文を Markdown 保存、`index.json` を累積マージ、`corpus.jsonl` を再生成
5. ログにサマリを出力して終了
