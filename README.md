# カレンダーWBSタスクマネージャー (Calendar WBS Task Manager)

Google ADK (Agent Development Kit) と FastAPI、Google標準リッチUI（Tailwind CSS / Material Symbols / Google Fonts）で構築された、カレンダー連携型WBS階層タスクマネージャーです。

## 主な機能
- **月間カレンダー表示＆日付選択**: カレンダーから特定の日付を選択してタスクを集中管理。
- **WBS階層タスク管理**: 親チケット・子チケット・孫チケットの3階層構造で作業分解と進捗率を可視化。
- **AIアシスタント (Gemini)**:
  - `create_wbs_tasks`: 指示されたプロジェクトや作業を親・子・孫タスクに自動分解・一括登録。
  - `get_wbs_tasks`: 日付ごとの進捗サマリーやタスク一覧を即座に要約・助言。
  - `execute_task`: タスクの実行・処理支援。
- **Google標準リッチUI**: 直感的なカード型コンポーネント、リアルタイムチャットUI。

## 構成
- `agent.py`: Google ADK による AI エージェント定義と関数ツール
- `store.py`: SQLite による階層タスクデータの永続化
- `main.py`: FastAPI による Web アプリケーション＆APIサーバー
- `static/index.html`: Google標準リッチUIフロントエンド
- `tests/test_agent.py`: Pytest による受け入れテスト・関数ツールテスト

## ローカル起動
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```
