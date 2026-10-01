"""データ永続化モジュール (SQLite)

企画書のデータ要件:
- WBSタスクデータ（日付、親・子・孫チケットのID、タイトル、完了状態）
- 保存先: ローカルファイル (calendar_wbs.db)
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "calendar_wbs.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                level INTEGER NOT NULL,
                parent_id TEXT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(date)")
        conn.commit()


def add_task(date: str, title: str, level: int = 1, parent_id: str | None = None) -> dict[str, Any]:
    init_db()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    created_at = datetime.datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM tasks WHERE date = ? AND level = ?",
            (date, level),
        )
        sort_order = cursor.fetchone()[0]
        conn.execute(
            """
            INSERT INTO tasks (id, date, level, parent_id, title, status, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, 'todo', ?, ?)
            """,
            (task_id, date, level, parent_id, title.strip(), sort_order, created_at),
        )
        conn.commit()
    return {
        "id": task_id,
        "date": date,
        "level": level,
        "parent_id": parent_id,
        "title": title.strip(),
        "status": "todo",
        "sort_order": sort_order,
        "created_at": created_at,
    }


def toggle_task_status(task_id: str) -> dict[str, Any] | None:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        new_status = "done" if row["status"] == "todo" else "todo"
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
        conn.commit()
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        updated = dict(cursor.fetchone())
        return updated


def delete_task(task_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        # 子・孫も再帰的に削除
        # SQLite の foreign key cascade または手動削除
        cursor = conn.execute("SELECT id FROM tasks WHERE parent_id = ?", (task_id,))
        child_ids = [r["id"] for r in cursor.fetchall()]
        for cid in child_ids:
            conn.execute("DELETE FROM tasks WHERE parent_id = ?", (cid,))
        conn.execute("DELETE FROM tasks WHERE parent_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return True


def get_tasks_by_date(date: str) -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE date = ? ORDER BY level ASC, sort_order ASC, created_at ASC",
            (date,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    return rows


def get_all_task_dates() -> list[str]:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute("SELECT DISTINCT date FROM tasks ORDER BY date ASC")
        return [r["date"] for r in cursor.fetchall()]


def _parse_subtasks(subtasks_json: Any) -> list[dict[str, Any]]:
    if isinstance(subtasks_json, list):
        items = subtasks_json
    elif isinstance(subtasks_json, dict):
        items = subtasks_json.get("subtasks", [subtasks_json])
    elif isinstance(subtasks_json, str):
        cleaned = subtasks_json.strip()
        # ```json ... ``` ブロックの除去
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                items = parsed.get("subtasks", parsed.get("tasks", [parsed]))
            else:
                items = [{"title": str(parsed)}]
        except Exception:
            # 改行や箇条書きのプレーンテキストをパース
            lines = [ln.strip().lstrip("-*・ 1234567890.)") for ln in cleaned.splitlines() if ln.strip()]
            items = [{"title": ln} for ln in lines]
    else:
        items = []

    normalized: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, str):
            normalized.append({"title": it.strip(), "subtasks": []})
        elif isinstance(it, dict):
            title = it.get("title") or it.get("name") or "子タスク"
            raw_sub = it.get("subtasks") or it.get("children") or []
            grand_children: list[str] = []
            if isinstance(raw_sub, list):
                for g in raw_sub:
                    if isinstance(g, str):
                        grand_children.append(g.strip())
                    elif isinstance(g, dict):
                        grand_children.append(str(g.get("title") or g.get("name") or "孫タスク"))
            normalized.append({"title": title, "subtasks": grand_children})
    return normalized


def create_wbs_hierarchy(date: str, parent_task: str, subtasks_raw: Any) -> dict[str, Any]:
    """親・子・孫チケットの階層構造を一括登録する。"""
    init_db()
    parent = add_task(date=date, title=parent_task, level=1, parent_id=None)
    parsed_children = _parse_subtasks(subtasks_raw)

    created_children = []
    created_grand_children = []

    for child_item in parsed_children:
        child_title = child_item["title"]
        child = add_task(date=date, title=child_title, level=2, parent_id=parent["id"])
        created_children.append(child)

        for grand_title in child_item.get("subtasks", []):
            grand = add_task(date=date, title=grand_title, level=3, parent_id=child["id"])
            created_grand_children.append(grand)

    return {
        "parent": parent,
        "children": created_children,
        "grandchildren": created_grand_children,
        "total_created": 1 + len(created_children) + len(created_grand_children),
    }


def format_wbs_summary(date: str) -> str:
    """指定日のタスク一覧を階層構造のテキスト形式で返す（AI回答およびツール用）。"""
    tasks = get_tasks_by_date(date)
    if not tasks:
        return f"{date} に登録されているタスクはありません。"

    parents = [t for t in tasks if t["level"] == 1]
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    grands_by_child: dict[str, list[dict[str, Any]]] = {}

    for t in tasks:
        if t["level"] == 2 and t["parent_id"]:
            children_by_parent.setdefault(t["parent_id"], []).append(t)
        elif t["level"] == 3 and t["parent_id"]:
            grands_by_child.setdefault(t["parent_id"], []).append(t)

    lines = [f"■ {date} のタスク一覧 (全{len(tasks)}件):"]
    # 親チケットごとにツリー化
    for p in parents:
        p_status = "【完了】" if p["status"] == "done" else "【未完了】"
        lines.append(f"- [親] {p['title']} {p_status} (ID: {p['id']})")
        children = children_by_parent.get(p["id"], [])
        for c in children:
            c_status = "【完了】" if c["status"] == "done" else "【未完了】"
            lines.append(f"  └─ [子] {c['title']} {c_status} (ID: {c['id']})")
            grands = grands_by_child.get(c["id"], [])
            for g in grands:
                g_status = "【完了】" if g["status"] == "done" else "【未完了】"
                lines.append(f"      └─ [孫] {g['title']} {g_status} (ID: {g['id']})")

    # 親に紐づいていない孤立タスクがあれば追加表示
    orphans = [t for t in tasks if t["level"] != 1 and not t.get("parent_id")]
    for o in orphans:
        o_status = "【完了】" if o["status"] == "done" else "【未完了】"
        lines.append(f"- [Level {o['level']}] {o['title']} {o_status}")

    done_count = sum(1 for t in tasks if t["status"] == "done")
    progress_rate = int((done_count / len(tasks)) * 100) if tasks else 0
    lines.append(f"\n進捗状況: 完了 {done_count}件 / 全 {len(tasks)}件 (進捗率: {progress_rate}%)")
    return "\n".join(lines)


# 初期化実行
init_db()
