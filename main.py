"""カレンダーWBSタスクマネージャー - FastAPI Webアプリケーション

エンドポイント:
- GET  /health: 死活監視用
- POST /chat: AIチャット（ADK root_agentを実行）
- GET  /api/tasks?date=YYYY-MM-DD: 指定日付のタスク一覧
- POST /api/tasks: タスク追加（手動）
- POST /api/tasks/{task_id}/toggle: 完了/未完了トグル
- DELETE /api/tasks/{task_id}: タスク削除
- GET  /api/calendar/dates: タスクが存在する日付一覧
- /: static/index.html を配信
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import credentials
credentials.configure()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from agent import root_agent
import store

APP_NAME = "calendar_wbs_agent"
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")

app = FastAPI(title="カレンダーWBSタスクマネージャー")
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
_sessions: dict[str, str] = {}


async def _session_id_for(user_id: str) -> str:
    sid = _sessions.get(user_id)
    if sid:
        sess = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=sid)
        if sess is not None:
            return sid
    sess = await session_service.create_session(app_name=APP_NAME, user_id=user_id)
    _sessions[user_id] = sess.id
    return sess.id


@app.get("/health")
async def health():
    return {"status": "ok", "agent": root_agent.name}


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = str(body.get("message", "")).strip()
    user_id = str(body.get("user_id") or "web-user")
    if not _USER_ID_RE.match(user_id):
        user_id = "web-user"
    if not message:
        return JSONResponse({"reply": "", "parts": []})

    session_id = await _session_id_for(user_id)
    content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
    final_text = ""
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        if event.content and event.author == root_agent.name:
            texts = [p.text for p in (event.content.parts or []) if getattr(p, "text", None)]
            if texts:
                final_text = "\n".join(texts)

    if not final_text:
        final_text = "承知いたしました。タスクの処理を行いました。"

    return JSONResponse({
        "reply": final_text,
        "parts": [{"kind": "text", "text": final_text}],
    })


@app.get("/api/tasks")
async def get_tasks(date: str):
    if not date:
        raise HTTPException(status_code=400, detail="日付(date)を指定してください")
    tasks = store.get_tasks_by_date(date)
    return {"date": date, "tasks": tasks}


class CreateTaskRequest(BaseModel):
    date: str
    title: str
    level: int = 1
    parent_id: str | None = None


@app.post("/api/tasks")
async def create_task(req: CreateTaskRequest):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="タイトルを入力してください")
    task = store.add_task(date=req.date, title=req.title, level=req.level, parent_id=req.parent_id)
    return {"status": "ok", "task": task}


@app.post("/api/tasks/{task_id}/toggle")
async def toggle_task(task_id: str):
    updated = store.toggle_task_status(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    return {"status": "ok", "task": updated}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    store.delete_task(task_id)
    return {"status": "ok"}


@app.get("/api/calendar/dates")
async def get_calendar_dates():
    dates = store.get_all_task_dates()
    return {"dates": dates}


static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
