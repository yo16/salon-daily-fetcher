# /batch-task-execute

単一タスクの実行。featureブランチ作成 → コーディング → テスト → devへのマージまでを行う。

## 引数
- `$ARGUMENTS` : BeadsID（例: `t-abc`）

## 使用するサブエージェント
- `beads-manager` : タスク情報取得・ステータス更新・retry管理
- `git-manager` : featureブランチ作成・commit・devへのマージ
- `coder` : コード実装（APIエンドポイント、ビジネスロジック）
- `db-coder` : DB操作関数の実装（coderからの委譲）
- `supabase-specialist` : Supabase固有機能の実装（必要な場合）
- `tester` : テスト実行・結果分析
- `test-reviewer` : テストの十分性レビュー（testerとは独立した第三者評価）

## 処理フロー

### 1. タスク情報取得 → `beads-manager`
- `bd show $ARGUMENTS --json` でタスク情報を取得する
- タスクが存在しない場合はエラーで停止する

### 2. featureブランチ作成 → `git-manager`
- 現在 `dev` ブランチにいることを確認する（いなければエラー）
- `git checkout -b feature/$ARGUMENTS` でfeatureブランチを作成・チェックアウトする

### 3. ステータス更新 → `beads-manager`
- `bd update $ARGUMENTS --status in_progress` でステータスを更新する

### 4. コーディング → `coder` + `db-coder` + `supabase-specialist`
- Beadsタスクのtitle, description, notesを渡し、タスク内容を伝える
- `docs/specification.md` を参照し、関連する仕様を理解させる
- `docs/design.md` を参照し、アプリケーション設計を理解させる
- `docs/db-design.md` を参照し、DB設計・API仕様を理解させる
- `coder` がタスクの実装を主導する:
  - APIエンドポイント、ビジネスロジック、フロントエンドの実装
  - DB操作が必要な箇所は `db-coder` に実装を委譲する
  - Supabase固有機能が必要な箇所は `supabase-specialist` に実装を委譲する
- 編集後のlint hookでエラーがあれば修正する
- 完了後、変更ファイルリストを受け取る（全エージェントの変更を含む）

### 5. テスト → `tester`
- `coder`、`db-coder`、`supabase-specialist` から受け取った変更ファイルリストを渡す
- テストが成功したらステップ5.5に進む
- テストが失敗した場合:
  - `tester` からテスト結果レポートを受け取る
  - レポートの「修正担当」に基づき、該当エージェント（`coder` / `db-coder` / `supabase-specialist`）に修正依頼を出す
  - 修正後、再度 `tester` でテスト実行
  - このループは最大3回まで
  - `beads-manager` でretryカウントを記録（`bd update $ARGUMENTS --notes "retry_count: N"`）
  - 3回超過で `/batch-failed` を実行して停止する

### 5.5. テストレビュー → `test-reviewer`
- テストが全パスした後、テストの**十分性**を第三者視点で評価する
- `test-reviewer` に以下の情報を渡す:
  - Beadsタスク情報（title, description, notes）
  - 変更ファイルリスト（coder / db-coder / supabase-specialist の全変更）
  - テストファイルリスト（testerの成功報告に含まれるもの）
- `test-reviewer` が「十分」と判定したらステップ6に進む
- `test-reviewer` が「不十分」と判定した場合:
  - レポートの「担当エージェント」に基づき、該当エージェントにテスト追加を依頼する
  - テスト追加後、再度 `tester` でテスト実行（ステップ5に戻る）
  - テスト全パス後、再度 `test-reviewer` でレビュー
  - このループ（ステップ5 → 5.5）は最大3回まで（ステップ5のリトライ回数とは別カウント）
  - 3回超過で `/batch-failed` を実行して停止する
  - `beads-manager` でレビューリトライカウントを記録（`bd update $ARGUMENTS --notes "review_retry_count: N"`）

### 6. commit → `git-manager`
- `git add` で変更をステージング（.beadsの変更も含む）
- Beadsタスクの内容に基づいた適切なコミットメッセージを生成する
- `git commit` でコミットする

### 7. devへのマージ → `git-manager`
- `git checkout dev` でdevブランチに移動する
- `git merge feature/$ARGUMENTS` で通常マージする（squashしない）
- featureブランチは削除しない

### 8. タスククローズ → `beads-manager`
- 実施内容の要約をnotesに記録する（変更ファイル一覧、テストファイル一覧を含む）
- `bd close $ARGUMENTS` でタスクをクローズする
