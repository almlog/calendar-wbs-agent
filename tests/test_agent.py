"""カレンダーWBSタスクマネージャー 自動テスト (T-4)

テスト項目:
1. 企画書の各機能（受け入れ条件）の検証:
   - F1: 基本機能（動作すること）/ カレンダー日付選択とタスク取得
   - F2: WBS階層タスク管理（親・子・孫チケットの追加、完了トグル、削除）
   - F3: 関数ツールによるWBS自動分解・一括登録 (create_wbs_tasks)
   - F4: 関数ツールによる進捗要約・タスク検索 (get_wbs_tasks)
2. 関数ツールの振る舞い検証:
   - execute_task が引数に応じて異なる正しい結果を返すこと
   - create_wbs_tasks が引数に応じて正しく登録・返却すること
   - get_wbs_tasks が日付ごとに正しい進捗サマリーを返すこと
3. 画面用データAPI（FastAPI TestClient）の検証:
   - GET  /health (HTTP 200)
   - GET  /api/calendar/dates (HTTP 200)
   - GET  /api/tasks (HTTP 200, 日付指定)
   - POST /api/tasks (HTTP 200, タスク作成)
   - POST /api/tasks/{task_id}/toggle (HTTP 200, 完了切り替え)
   - DELETE /api/tasks/{task_id} (HTTP 200, 削除)
   - GET  / (HTTP 200, static index.html)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# モジュール検索パスに calendar_wbs_agent を追加
AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import store
from agent import create_wbs_tasks, execute_task, get_wbs_tasks
from main import app


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """各テストで独立したテスト用 SQLite データベースを使用する。"""
    test_db = tmp_path / "test_calendar_wbs.db"
    monkeypatch.setattr(store, "DB_PATH", test_db)
    store.init_db()
    yield


client = TestClient(app)


# ==============================================================================
# 1. 企画書機能の受け入れ条件テスト
# ==============================================================================

def test_f1_basic_functionality_and_calendar():
    """F1: 基本機能が動作し、日付ごとのタスク取得・カレンダー連携ができること。"""
    date = "2026-10-15"
    store.add_task(date=date, title="基本動作確認タスク", level=1)
    
    dates = store.get_all_task_dates()
    assert date in dates

    tasks = store.get_tasks_by_date(date)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "基本動作確認タスク"
    assert tasks[0]["level"] == 1


def test_f2_wbs_hierarchy_management():
    """F2: 親・子・孫チケットの階層構造でタスクの追加・完了状態の切り替え・削除ができること。"""
    date = "2026-10-15"
    
    # 親チケット (Level 1)
    parent = store.add_task(date=date, title="親: システム開発", level=1)
    assert parent["id"]
    assert parent["status"] == "todo"

    # 子チケット (Level 2)
    child = store.add_task(date=date, title="子: フロントエンド", level=2, parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]
    assert child["level"] == 2

    # 孫チケット (Level 3)
    grand = store.add_task(date=date, title="孫: ボタン実装", level=3, parent_id=child["id"])
    assert grand["parent_id"] == child["id"]
    assert grand["level"] == 3

    # ステータスのトグル（完了切り替え）
    updated = store.toggle_task_status(grand["id"])
    assert updated["status"] == "done"
    
    # 再度トグルで戻る
    reverted = store.toggle_task_status(grand["id"])
    assert reverted["status"] == "todo"

    # 削除の検証
    store.delete_task(parent["id"])
    remaining = store.get_tasks_by_date(date)
    assert len(remaining) == 0


def test_f3_create_wbs_tasks_tool():
    """F3: create_wbs_tasks ツールが親・子・孫チケットを自動分解・一括登録すること。"""
    date = "2026-10-20"
    subtasks = [
        {"title": "設計工程", "subtasks": ["画面ワイヤー", "API設計"]},
        {"title": "開発工程", "subtasks": ["UIコーディング", "サーバー実装"]}
    ]
    result = create_wbs_tasks(date=date, parent_task="新規アプリ企画", subtasks_json=json.dumps(subtasks))
    
    assert "登録完了" in result
    assert "新規アプリ企画" in result
    assert "設計工程" in result
    assert "画面ワイヤー" in result

    tasks = store.get_tasks_by_date(date)
    # 親1 + 子2 + 孫4 = 7件
    assert len(tasks) == 7


def test_f4_get_wbs_tasks_tool():
    """F4: get_wbs_tasks ツールが指定日のタスク一覧および進捗状況を取得・要約すること。"""
    date = "2026-10-25"
    p = store.add_task(date=date, title="親タスクA", level=1)
    c = store.add_task(date=date, title="子タスクB", level=2, parent_id=p["id"])
    store.toggle_task_status(p["id"])  # 1件完了

    summary = get_wbs_tasks(date)
    assert "親タスクA" in summary
    assert "子タスクB" in summary
    assert "進捗状況: 完了 1件 / 全 2件" in summary
    assert "50%" in summary


# ==============================================================================
# 2. 関数ツールの入力応酬・ダミー排除テスト
# ==============================================================================

def test_execute_task_returns_dynamic_results():
    """関数ツール execute_task が入力引数に応じて異なる正しい結果を返すこと。"""
    res1 = execute_task("データベースのバックアップ作成")
    res2 = execute_task("ログファイルのクリーンアップ")

    assert "データベースのバックアップ作成" in res1
    assert "ログファイルのクリーンアップ" in res2
    assert res1 != res2


def test_create_wbs_tasks_with_different_inputs():
    """create_wbs_tasks が異なる引数で呼び出されたときに異なる結果を返すこと。"""
    r1 = create_wbs_tasks("2026-11-01", "プロジェクトAlpha", json.dumps([{"title": "タスクA", "subtasks": ["A-1"]}]))
    r2 = create_wbs_tasks("2026-11-02", "プロジェクトBeta", json.dumps([{"title": "タスクB", "subtasks": ["B-1", "B-2"]}]))

    assert "プロジェクトAlpha" in r1
    assert "プロジェクトBeta" in r2
    assert "2026-11-01" in r1
    assert "2026-11-02" in r2
    assert r1 != r2


# ==============================================================================
# 3. 画面用データ API (FastAPI TestClient) の検証
# ==============================================================================

def test_api_health():
    """GET /health が HTTP 200 と ok ステータスを返すこと。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_tasks_crud():
    """タスク作成、一覧取得、ステータストグル、削除の API がすべて正常に動作すること。"""
    date = "2026-12-01"

    # 作成
    create_resp = client.post("/api/tasks", json={
        "date": date,
        "title": "API経由タスク",
        "level": 1
    })
    assert create_resp.status_code == 200
    task_id = create_resp.json()["task"]["id"]

    # 一覧取得
    get_resp = client.get(f"/api/tasks?date={date}")
    assert get_resp.status_code == 200
    tasks = get_resp.json()["tasks"]
    assert any(t["id"] == task_id for t in tasks)

    # トグル
    toggle_resp = client.post(f"/api/tasks/{task_id}/toggle")
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["task"]["status"] == "done"

    # カレンダー日付一覧
    dates_resp = client.get("/api/calendar/dates")
    assert dates_resp.status_code == 200
    assert date in dates_resp.json()["dates"]

    # 削除
    del_resp = client.delete(f"/api/tasks/{task_id}")
    assert del_resp.status_code == 200

    # 削除後の確認
    after_resp = client.get(f"/api/tasks?date={date}")
    assert not any(t["id"] == task_id for t in after_resp.json()["tasks"])


def test_static_index_html_served():
    """GET / で static/index.html が HTTP 200 で返されること。"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "カレンダーWBSタスクマネージャー" in resp.text
