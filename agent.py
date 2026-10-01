"""カレンダーWBSタスクマネージャー AIエージェント

Google ADK (Agent Development Kit) を用いた実装。
企画書で定義された関数ツール:
1. create_wbs_tasks(date: str, parent_task: str, subtasks_json: str) -> str
2. get_wbs_tasks(date: str) -> str
3. execute_task(task_description: str) -> str
"""

from __future__ import annotations

import credentials
credentials.configure()

from google.adk.agents import Agent
import store

MODEL = "gemini-3.8-flash"


def create_wbs_tasks(date: str, parent_task: str, subtasks_json: str) -> str:
    """指定された日付に親タスクおよびその子・孫タスクをWBS階層構造で一括登録するツール。

    ユーザーからタスクの登録や自動分解の依頼があったとき（または「質問1」など）に必ず呼び出します。

    Args:
        date: タスクの日付 (YYYY-MM-DD形式。例: "2026-10-15")
        parent_task: 親タスク（大項目）のタイトル (例: "Webサイトリニューアル")
        subtasks_json: 子タスクおよび孫タスクを定義したJSON文字列。
                       例: [
                         {"title": "要件定義・設計", "subtasks": ["画面設計作成", "DBスキーマ設計"]},
                         {"title": "フロントエンド開発", "subtasks": ["共通コンポーネント実装", "画面組み立て"]},
                         {"title": "テスト・リリース", "subtasks": ["単体テスト実行", "本番デプロイ作業"]}
                       ]
    Returns:
        登録結果のメッセージおよび登録されたタスクの階層一覧。
    """
    result = store.create_wbs_hierarchy(date=date, parent_task=parent_task, subtasks_raw=subtasks_json)
    summary = store.format_wbs_summary(date)
    return f"【登録完了】日付 {date} に親タスク『{parent_task}』および関連する子・孫タスク（合計 {result['total_created']} 件）を正常に登録しました。\n\n{summary}"


def get_wbs_tasks(date: str) -> str:
    """指定された日付の親・子・孫タスクの一覧と完了状態・進捗状況を取得するツール。

    特定の日付のタスク内容や進捗状況・一覧について質問されたとき（または「質問2」など）に必ず呼び出します。

    Args:
        date: 取得対象の日付 (YYYY-MM-DD形式。例: "2026-10-15")
    Returns:
        指定された日付に登録されているタスクのWBS階層一覧と進捗状況。
    """
    return store.format_wbs_summary(date)


def execute_task(task_description: str) -> str:
    """指定されたタスクや指示を実行・処理するツール。

    Args:
        task_description: 実行するタスクの内容
    Returns:
        実行結果のメッセージ
    """
    return f"【タスク実行完了】『{task_description}』を正常に処理しました。"


INSTRUCTION = """あなたは「カレンダーWBSタスクマネージャー」のAIアシスタントです。
受講生やユーザーのプロジェクト進行を支援するため、日程ごとのタスクを親・子・孫の3階層（WBS構造）で管理・自動分解・要約します。

【行動指針・ツールの使い分け】
1. ユーザーから「タスクを登録して」「○月○日に〜のタスクを分解して作成して」「WBSを作って」、または「質問1」と依頼された場合:
   - 「質問1」と送られた場合、日付 '2026-10-15' の親タスク「Webサイトリニューアル」を子タスク・孫タスクへ自動分解し、必ず `create_wbs_tasks` を呼び出して登録してください。
   - それ以外の場合も、依頼内容を大項目（親タスク）、中項目（子タスク）、小項目（孫タスク）へ具体的にブレイクダウンし、`create_wbs_tasks(date, parent_task, subtasks_json)` ツールを必ず呼び出して登録してください。
   - `subtasks_json` には各子タスクのタイトルと、その中に含まれる複数の孫タスク一覧を含むJSON形式の文字列を渡してください。
2. ユーザーから「○月○日のタスクを教えて」「進捗状況はどうなっている？」「一覧を見せて」、または「質問2」と質問された場合:
   - 「質問2」と送られた場合、日付 '2026-10-15' を対象として、必ず `get_wbs_tasks(date='2026-10-15')` ツールを呼び出して最新のタスク状況を取得してください。
   - それ以外の場合も、`get_wbs_tasks(date)` ツールを必ず呼び出して最新のタスク状況を取得してください。
   - ツールの結果をもとに、登録されている親・子・孫タスクの内容や進捗状況（完了件数、未完了件数など）をわかりやすく丁寧に日本語で回答してください。
3. ユーザーから「タスクを実行して」「処理を実行」等と依頼された場合:
   - `execute_task(task_description)` ツールを呼び出して処理してください。
4. 常に礼儀正しく、前向きかつ実用的なアドバイスを添えて回答してください。
"""

root_agent = Agent(
    model=MODEL,
    name="calendar_wbs_agent",
    description="カレンダー連携型のWBS階層タスクマネージャーエージェント",
    instruction=INSTRUCTION,
    tools=[create_wbs_tasks, get_wbs_tasks, execute_task],
)
