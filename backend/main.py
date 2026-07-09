from __future__ import annotations

import threading
from pathlib import Path

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import ROOT_DIR, delete_profile, get_settings, load_sources, public_settings, save_settings, set_active_profile
from database import add_log, get_agent_status, get_events, get_filter_options, get_logs, init_db, list_jobs, set_agent_status
from agents import empty_llm_content_message, llm_create_kwargs, llm_message_text
from pipeline import is_running, is_stopping, request_stop, run_pipeline


app = FastAPI(title="Job Radar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

web_dir = ROOT_DIR / "frontend" / "dist"
dev_web_dir = ROOT_DIR / "frontend"


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/jobs")
def api_jobs(
    keyword: str = "",
    industry: str = "",
    company_type: str = "",
    batch: str = "",
    location: str = "",
    confidence: str = "",
    status: str = "",
):
    return list_jobs(
        {
            "keyword": keyword,
            "industry": industry,
            "company_type": company_type,
            "batch": batch,
            "location": location,
            "confidence": confidence,
            "status": status,
        }
    )


@app.get("/api/filters")
def api_filters():
    return get_filter_options()


@app.get("/api/sources")
def api_sources():
    return load_sources()


@app.get("/api/settings")
def api_settings():
    return public_settings()


@app.get("/api/llm/status")
def api_llm_status():
    settings = get_settings()
    logs = get_logs(200)
    last_llm = next((log for log in logs if "LLM" in str(log.get("message", ""))), None)
    return {
        "used_by": ["Extractor Agent", "Classifier Agent"],
        "api_key_set": bool(settings.api_key),
        "base_url": settings.base_url,
        "model": settings.model,
        "last_message": last_llm.get("message", "") if last_llm else "",
        "last_time": last_llm.get("created_at", "") if last_llm else "",
    }


@app.post("/api/llm/test")
def api_llm_test():
    settings = get_settings()
    if not (settings.api_key and settings.base_url and settings.model):
        message = "LLM 测试失败：请先配置 API Key、Base URL 和 Model"
        add_log("LLM", "error", message)
        return {"ok": False, "message": message}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.llm_timeout)
        response = client.chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": "你是 API 连通性测试助手，只输出短文本。"},
                {"role": "user", "content": "请只回复 OK"},
            ],
            temperature=0,
            **llm_create_kwargs(settings, max_tokens=64),
        )
        choices = getattr(response, "choices", None) or []
        content = ""
        if choices and getattr(choices[0], "message", None) is not None:
            content = llm_message_text(choices[0].message)
        if not content:
            detail = empty_llm_content_message(choices[0]) if choices else "API 响应不含 choices"
            message = f"LLM 测试失败：{detail}"
            add_log("LLM", "error", message)
            return {"ok": False, "message": message}
        message = f"LLM 测试成功：{content.strip()}"
        add_log("LLM", "info", message)
        return {"ok": True, "message": message}
    except Exception as exc:
        message = f"LLM 测试失败：{exc}"
        add_log("LLM", "error", message)
        return {"ok": False, "message": message}


@app.put("/api/settings")
def api_update_settings(payload: dict = Body(...)):
    settings = save_settings(payload)
    add_log("LLM", "info", f"LLM 配置已保存：{settings.get('profile_name', '')}")
    return settings


@app.put("/api/settings/active")
def api_set_active_settings(payload: dict = Body(...)):
    settings = set_active_profile(str(payload.get("profile_name", "")))
    add_log("LLM", "info", f"LLM 当前配置已切换：{settings.get('profile_name', '')}")
    return settings


@app.delete("/api/settings/{profile_name}")
def api_delete_settings(profile_name: str):
    settings = delete_profile(profile_name)
    add_log("LLM", "info", f"LLM 配置已删除：{profile_name}")
    return settings


@app.post("/api/run")
def api_run():
    if is_running():
        return {"ok": False, "message": "Agent 正在运行中"}

    set_agent_status("System", "运行中", "Agent 已启动，正在扫描来源", 0, 0, 0)
    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return {"ok": True, "message": "Agent 已启动"}


@app.post("/api/stop")
def api_stop():
    return request_stop()


@app.get("/api/status")
def api_status():
    if not is_running() and not is_stopping():
        system = next((agent for agent in get_agent_status() if agent.get("agent") == "System"), None)
        if system and system.get("status") == "停止中":
            set_agent_status("System", "已停止", "Agent 当前没有运行", 0, 0, 0)
    return {"running": is_running(), "stopping": is_stopping(), "agents": get_agent_status()}


@app.get("/api/logs")
def api_logs(limit: int = Query(100, ge=1, le=500)):
    return get_logs(limit)


@app.get("/api/events")
def api_events(agent: str = "", limit: int = Query(200, ge=1, le=500)):
    return get_events(agent, limit)


if web_dir.exists():
    app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")


@app.get("/{path:path}")
def frontend(path: str):
    index_file = web_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    fallback = dev_web_dir / "index.html"
    if fallback.exists():
        return FileResponse(fallback)

    return {"message": "Job Radar backend is running", "frontend": "not built"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8765, reload=True)
