from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DATA_DIR


DB_PATH = DATA_DIR / "job_radar.db"

VISIBLE_JOB_WHERE = "status not like '%入口页%' and status not like '%待抓取岗位%'"

CITY_NAMES = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "成都",
    "杭州",
    "南京",
    "武汉",
    "西安",
    "重庆",
    "天津",
    "苏州",
    "无锡",
    "宁波",
    "厦门",
    "福州",
    "合肥",
    "长沙",
    "郑州",
    "济南",
    "青岛",
    "大连",
    "沈阳",
    "长春",
    "哈尔滨",
    "石家庄",
    "太原",
    "南昌",
    "南宁",
    "昆明",
    "贵阳",
    "兰州",
    "西宁",
    "银川",
    "乌鲁木齐",
    "海口",
    "珠海",
    "东莞",
    "佛山",
    "中山",
    "惠州",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def split_locations(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text in {"不限", "全国", "多地", "全国多地"}:
        return []
    if "远程" in text:
        return ["远程"]
    if "海外" in text:
        return ["海外"]
    found: list[str] = []
    for city in CITY_NAMES:
        if city in text and city not in found:
            found.append(city)
    if found:
        return found
    return []


def display_location(value: Any) -> str:
    locations = split_locations(value)
    if not locations:
        return "不限"
    return locations[0] if len(locations) == 1 else "多地"


def stored_location(value: Any) -> str:
    locations = split_locations(value)
    if locations:
        return "/".join(locations)
    return "不限"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            create table if not exists job_summary (
                id text primary key,
                publish_date text,
                company_name text,
                job_title text,
                announcement_url text,
                apply_url text,
                industry text,
                company_type text,
                batch text,
                location text,
                hot_score integer,
                source_name text,
                source_type text,
                confidence text,
                status text,
                raw_summary text,
                last_updated text
            )
            """
        )
        conn.execute(
            """
            create table if not exists agent_status (
                agent text primary key,
                status text,
                latency_ms integer,
                success_count integer,
                failure_count integer,
                last_message text,
                updated_at text
            )
            """
        )
        conn.execute(
            """
            create table if not exists agent_logs (
                id integer primary key autoincrement,
                agent text,
                level text,
                message text,
                latency_ms integer,
                created_at text
            )
            """
        )
        conn.execute(
            """
            create table if not exists agent_events (
                id integer primary key autoincrement,
                agent text,
                source_name text,
                source_url text,
                status text,
                latency_ms integer,
                message text,
                detail text,
                created_at text
            )
            """
        )
        conn.commit()


def upsert_job(job: dict[str, Any]) -> None:
    values = {
        "id": job["id"],
        "publish_date": job.get("publish_date") or "",
        "company_name": job.get("company_name") or "",
        "job_title": job.get("job_title") or "",
        "announcement_url": job.get("announcement_url") or "",
        "apply_url": job.get("apply_url") or "",
        "industry": job.get("industry") or "",
        "company_type": job.get("company_type") or "",
        "batch": job.get("batch") or "",
        "location": stored_location(job.get("location")),
        "hot_score": int(job.get("hot_score") or 1),
        "source_name": job.get("source_name") or "",
        "source_type": job.get("source_type") or "",
        "confidence": job.get("confidence") or "待核验",
        "status": job.get("status") or "待核验",
        "raw_summary": job.get("raw_summary") or "",
        "last_updated": now_text(),
    }
    with connect() as conn:
        conn.execute(
            """
            insert into job_summary (
                id, publish_date, company_name, job_title, announcement_url,
                apply_url, industry, company_type, batch, location, hot_score,
                source_name, source_type, confidence, status, raw_summary,
                last_updated
            ) values (
                :id, :publish_date, :company_name, :job_title, :announcement_url,
                :apply_url, :industry, :company_type, :batch, :location, :hot_score,
                :source_name, :source_type, :confidence, :status, :raw_summary,
                :last_updated
            )
            on conflict(id) do update set
                publish_date=excluded.publish_date,
                company_name=excluded.company_name,
                job_title=excluded.job_title,
                announcement_url=excluded.announcement_url,
                apply_url=excluded.apply_url,
                industry=excluded.industry,
                company_type=excluded.company_type,
                batch=excluded.batch,
                location=excluded.location,
                hot_score=excluded.hot_score,
                source_name=excluded.source_name,
                source_type=excluded.source_type,
                confidence=excluded.confidence,
                status=excluded.status,
                raw_summary=excluded.raw_summary,
                last_updated=excluded.last_updated
            """,
            values,
        )
        conn.commit()


def list_jobs(filters: dict[str, str]) -> list[dict[str, Any]]:
    sql = f"select * from job_summary where {VISIBLE_JOB_WHERE}"
    params: dict[str, Any] = {}
    for field in ["industry", "company_type", "batch", "location", "confidence", "status"]:
        value = filters.get(field)
        if value:
            sql += f" and {field} like :{field}"
            params[field] = f"%{value}%"
    keyword = filters.get("keyword")
    if keyword:
        sql += " and (company_name like :keyword or job_title like :keyword)"
        params["keyword"] = f"%{keyword}%"
    sql += " order by publish_date desc, last_updated desc limit 500"
    with connect() as conn:
        rows = []
        for row in conn.execute(sql, params).fetchall():
            item = dict(row)
            item["location"] = display_location(item.get("location"))
            rows.append(item)
        return rows


def get_filter_options() -> dict[str, list[str]]:
    fields = ["industry", "company_type", "batch", "location", "confidence", "status"]
    result: dict[str, list[str]] = {}
    with connect() as conn:
        for field in fields:
            rows = conn.execute(
                f"select distinct {field} as value from job_summary where {VISIBLE_JOB_WHERE} and {field} != '' order by {field}"
            ).fetchall()
            if field == "location":
                locations: set[str] = set()
                for row in rows:
                    parts = split_locations(row["value"])
                    if parts:
                        locations.update(parts)
                    elif row["value"] and row["value"] not in {"不限", "多地"}:
                        locations.add(row["value"])
                result[field] = sorted(locations)
            else:
                result[field] = [row["value"] for row in rows]
    return result


def set_agent_status(
    agent: str,
    status: str,
    message: str,
    latency_ms: int = 0,
    success_count: int = 0,
    failure_count: int = 0,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into agent_status (
                agent, status, latency_ms, success_count, failure_count,
                last_message, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?)
            on conflict(agent) do update set
                status=excluded.status,
                latency_ms=excluded.latency_ms,
                success_count=excluded.success_count,
                failure_count=excluded.failure_count,
                last_message=excluded.last_message,
                updated_at=excluded.updated_at
            """,
            (agent, status, latency_ms, success_count, failure_count, message, now_text()),
        )
        conn.commit()


def add_log(agent: str, level: str, message: str, latency_ms: int = 0) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into agent_logs (agent, level, message, latency_ms, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (agent, level, message, latency_ms, now_text()),
        )
        conn.commit()


def add_event(
    agent: str,
    source_name: str,
    source_url: str,
    status: str,
    message: str,
    detail: str = "",
    latency_ms: int = 0,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into agent_events (
                agent, source_name, source_url, status, latency_ms,
                message, detail, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (agent, source_name, source_url, status, latency_ms, message, detail, now_text()),
        )
        conn.commit()


def get_agent_status() -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(row) for row in conn.execute("select * from agent_status order by agent").fetchall()]


def get_logs(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "select * from agent_logs order by id desc limit ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_events(agent: str = "", limit: int = 200) -> list[dict[str, Any]]:
    sql = "select * from agent_events where 1=1"
    params: list[Any] = []
    if agent:
        sql += " and agent = ?"
        params.append(agent)
    sql += " order by id desc limit ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
