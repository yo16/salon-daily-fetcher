# /batch-push-pr

全タスク完了後に、devブランチをGitHubへpushし、PRを作成する。

## 引数
なし

## 使用するサブエージェント
- `beads-manager` : 完了タスクの情報取得
- `github-manager` : push・PR作成

## 処理フロー

### 1. 前提確認
- `git branch --show-current` で現在 `dev` ブランチにいることを確認する

### 2. 完了タスク情報の収集 → `beads-manager`
- 今回のバッチで完了した（statusが `done` の）タスクの一覧を取得する
- 各タスクのtitle, notesから変更概要を収集する

### 3. push → `github-manager`
- `git push origin dev` でdevブランチをリモートにpushする
- pushが失敗した場合は `/batch-failed` を実行して停止する

### 4. PR作成 → `github-manager`
- `gh pr create --base main --head dev` でPRを作成する
- PRタイトル: バッチ実行の概要（例: `feat: タスクN件の一括実装`）
- PR本文に含める内容:
  - 実行したタスクの一覧（BeadsID + タイトル）
  - 各タスクの変更概要（beads-managerが収集した情報）
  - テスト結果のサマリー

### 5. PR URL報告
- 作成したPRのURLをユーザーに表示する
