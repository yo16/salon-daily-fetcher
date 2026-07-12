# /batch-failed

タスク実行中に失敗が発生した場合の停止処理。
現在の状態を保全し、ユーザーへ通知する。

## 引数
- `$ARGUMENTS` : 失敗の理由・エラー内容（任意）

## 使用するサブエージェント
- `beads-manager` : タスクのfailedラベル付与・notes記録
- `git-manager` : 作業中の変更をcommit

## 処理フロー

### 1. 現在のブランチ確認
- `git branch --show-current` で現在のブランチを取得する

### 2. 作業中の変更を保全 → `git-manager`
- 未commitの変更がある場合、現在のブランチで `git add` → `git commit` する
- コミットメッセージ: `wip(<BeadsID>): 自動処理中断時の保全commit`

### 3. タスクのステータス記録 → `beads-manager`
- 現在実行中のタスク（in_progressのもの）がある場合:
  - `bd update <BeadsID> --add-label failed` でfailedラベルを追加する
  - `bd update <BeadsID> --notes "<エラー内容>"` でnotesにエラー内容を記録する
- タスクのcloseは行わない（人間が判断する）

### 4. devブランチへ戻る → `git-manager`
- `git checkout dev` でdevブランチに戻る

### 5. ユーザーへ通知
以下の情報をユーザーに報告する:
- **失敗したタスク**: BeadsID、タイトル
- **失敗の原因**: エラー内容の要約
- **現在の状態**: どこまで完了しているか（完了済みタスク一覧）
- **featureブランチ**: 失敗時のブランチ名（ローカルに残っている）
- **復旧の手順**: 人間が介入するためのガイダンス
  - `git checkout feature/<BeadsID>` で失敗時の状態を確認できること
  - 修正後は `/batch-start` で残りのタスクを再開できること
