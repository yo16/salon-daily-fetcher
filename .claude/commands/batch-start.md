# /batch-start

全オープンタスクを一括実行するエントリーポイント。
依存関係順にタスクを実行し、全完了後にPRを作成する。

## 引数
なし

## 前提条件
- `/batch-design` による設計が完了し、`docs/design.md` と `docs/db-design.md` が存在すること
- `task-decomposer` によるタスク分解が完了し、Beadsタスクが登録されていること

## 使用するサブエージェント
- `task-planner` : 実行計画の作成
- `beads-manager` : タスクステータス管理
- `git-manager` : ローカルgit操作
- `github-manager` : GitHub push・PR作成

## 処理フロー

### 1. 前提確認
- `git branch --show-current` で現在 `dev` ブランチにいることを確認する
- `dev` ブランチにいない場合はエラーで停止する
- `docs/design.md` と `docs/db-design.md` の存在を確認する（存在しない場合は `/batch-design` の実行を案内して停止する）

### 2. 実行計画の作成 → `task-planner`
- オープンなBeadsタスクを取得する
- 依存関係に基づいてトポロジカルソートし、実行順序を決定する
- オープンタスクが0件の場合は「実行対象なし」として終了する
- 循環依存がある場合はエラーで停止する

### 3. タスクの順次実行
- 実行計画の順序に従い、各タスクについて `/batch-task-execute <BeadsID>` の処理を実行する
- 1タスクが完了（devへのマージまで）してから次のタスクに進む
- いずれかのタスクで失敗した場合は `/batch-failed` の処理を実行して停止する

### 4. GitHub push・PR作成 → `/batch-push-pr`
- 全タスクが正常完了した場合のみ実行する
- devブランチをGitHubへpushし、`dev → main` のPRを作成する

### 5. 完了報告
- 実行したタスクの一覧と結果をユーザーに報告する
- 作成したPRのURLを表示する
