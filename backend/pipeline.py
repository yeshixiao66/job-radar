from __future__ import annotations

import threading
from typing import Any

from agents import ClassifierAgent, CrawlerAgent, ExtractorAgent, SourceAgent, VerifierAgent
from database import add_event, add_log, set_agent_status, upsert_job


AGENTS = {
    "source": SourceAgent(),
    "crawler": CrawlerAgent(),
    "extractor": ExtractorAgent(),
    "verifier": VerifierAgent(),
    "classifier": ClassifierAgent(),
}

_lock = threading.Lock()
_running = False
_stop_event = threading.Event()


def is_running() -> bool:
    return _running


def is_stopping() -> bool:
    return _running and _stop_event.is_set()


def request_stop() -> dict[str, Any]:
    if not _running:
        return {"ok": True, "message": "Agent 当前没有运行"}
    _stop_event.set()
    add_log("System", "info", "已请求停止 Agent")
    set_agent_status("System", "停止中", "已请求停止，等待当前步骤结束", 0, 0, 0)
    return {"ok": True, "message": "已请求停止，当前步骤结束后会停下"}


def run_pipeline() -> dict[str, Any]:
    global _running
    if not _lock.acquire(blocking=False):
        return {"ok": False, "message": "Agent 正在运行中"}

    _running = True
    _stop_event.clear()
    total_jobs = 0
    failures = 0
    company_counts: dict[str, int] = {}
    set_agent_status("System", "运行中", "Agent 正在扫描来源", 0, 0, 0)

    try:
        source_result = AGENTS["source"].run()
        _record("Source Agent", source_result, len(source_result.data or []), 0)
        _event("Source Agent", {}, source_result)
        if not source_result.ok:
            return {"ok": False, "message": source_result.message}

        for source in source_result.data:
            source_stored = 0
            if _stop_event.is_set():
                message = f"Agent 已停止：已入库 {total_jobs} 条，失败 {failures} 个"
                add_log("System", "info", message)
                set_agent_status("System", "已停止", message, 0, total_jobs, failures)
                return {"ok": True, "message": "Agent 已停止", "jobs": total_jobs, "failures": failures}

            crawl_result = AGENTS["crawler"].run(source)
            _record("Crawler Agent", crawl_result, 1 if crawl_result.ok else 0, 0 if crawl_result.ok else 1)
            _event("Crawler Agent", source, crawl_result, _page_detail(crawl_result.data))
            if not crawl_result.ok:
                failures += 1
                continue

            extract_result = AGENTS["extractor"].run(crawl_result.data)
            _record(
                "Extractor Agent",
                extract_result,
                len(extract_result.data or []) if extract_result.ok else 0,
                0 if extract_result.ok else 1,
            )
            _event("Extractor Agent", source, extract_result, _jobs_detail(extract_result.data))
            if not extract_result.ok:
                failures += 1
                continue

            for job in extract_result.data:
                if _stop_event.is_set():
                    message = f"Agent 已停止：已入库 {total_jobs} 条，失败 {failures} 个"
                    add_log("System", "info", message)
                    set_agent_status("System", "已停止", message, 0, total_jobs, failures)
                    return {"ok": True, "message": "Agent 已停止", "jobs": total_jobs, "failures": failures}

                verify_result = AGENTS["verifier"].run(job, source)
                _record("Verifier Agent", verify_result, 1 if verify_result.ok else 0, 0 if verify_result.ok else 1)
                _event("Verifier Agent", source, verify_result, _job_detail(verify_result.data))
                if not verify_result.ok:
                    failures += 1
                    continue

                classify_result = AGENTS["classifier"].run(verify_result.data, source)
                _record("Classifier Agent", classify_result, 1 if classify_result.ok else 0, 0 if classify_result.ok else 1)
                _event("Classifier Agent", source, classify_result, _job_detail(classify_result.data))
                if not classify_result.ok:
                    failures += 1
                    continue

                if _should_store_job(classify_result.data) and _passes_diversity_limits(
                    classify_result.data,
                    source,
                    company_counts,
                    source_stored,
                ):
                    upsert_job(classify_result.data)
                    company = str(classify_result.data.get("company_name", "")).strip()
                    company_counts[company] = company_counts.get(company, 0) + 1
                    source_stored += 1
                    total_jobs += 1
                else:
                    add_log("System", "info", f"跳过低质量结果：{classify_result.data.get('job_title', '')[:80]}")

        message = f"本轮扫描完成：入库 {total_jobs} 条，失败 {failures} 个"
        add_log("System", "info", message)
        set_agent_status("System", "完成", message, 0, total_jobs, failures)
        return {"ok": True, "jobs": total_jobs, "failures": failures}
    except Exception as exc:
        failures += 1
        message = f"Agent 运行失败：{exc}"
        add_log("System", "error", message)
        set_agent_status("System", "失败", message, 0, total_jobs, failures)
        return {"ok": False, "message": message, "jobs": total_jobs, "failures": failures}
    finally:
        _running = False
        _stop_event.clear()
        _lock.release()


def _record(agent: str, result, success_count: int, failure_count: int) -> None:
    status = "完成" if result.ok else "失败"
    set_agent_status(agent, status, result.message, result.latency_ms, success_count, failure_count)
    add_log(agent, "info" if result.ok else "error", result.message, result.latency_ms)


def _event(agent: str, source: dict[str, str], result, detail: str = "") -> None:
    add_event(
        agent=agent,
        source_name=source.get("name", "系统"),
        source_url=source.get("url", ""),
        status="成功" if result.ok else "失败",
        message=result.message,
        detail=detail,
        latency_ms=result.latency_ms,
    )


def _page_detail(page) -> str:
    if not isinstance(page, dict):
        return ""
    return f"标题：{page.get('title', '')}\n链接数：{len(page.get('links', []))}\n正文预览：{page.get('content', '')[:300]}"


def _jobs_detail(jobs) -> str:
    if not isinstance(jobs, list):
        return ""
    lines = []
    for job in jobs[:5]:
        lines.append(f"{job.get('company_name', '')} | {job.get('job_title', '')} | {job.get('apply_url', '')}")
    return "\n".join(lines)


def _job_detail(job) -> str:
    if not isinstance(job, dict):
        return ""
    keys = ["company_name", "job_title", "industry", "company_type", "batch", "location", "confidence", "status"]
    return "\n".join(f"{key}: {job.get(key, '')}" for key in keys)


def _should_store_job(job) -> bool:
    if not isinstance(job, dict):
        return False
    title = str(job.get("job_title", "")).strip()
    status = str(job.get("status", ""))
    confidence = str(job.get("confidence", ""))
    if not title or not job.get("announcement_url"):
        return False
    company = str(job.get("company_name", "")).strip()
    source_name = str(job.get("source_name", "")).strip()
    if not company or company == source_name or "就业信息网" in company or "就业指导" in company:
        return False
    if confidence == "低" or "入口页" in status or "待深挖" in status:
        return False
    generic_titles = ["首页", "主页", "校园招聘", "校招", "招聘官网", "招聘平台", "加入我们", "人才招聘"]
    role_keywords = [
        "工程师",
        "开发",
        "算法",
        "产品",
        "运营",
        "测试",
        "数据",
        "研究员",
        "实习生",
        "管培",
        "销售",
        "市场",
        "财务",
        "人力",
        "法务",
        "供应链",
        "运维",
        "硬件",
        "电气",
        "机械",
    ]
    if any(keyword in title for keyword in generic_titles) and not any(keyword in title for keyword in role_keywords):
        return False
    return True


def _passes_diversity_limits(
    job: dict[str, Any],
    source: dict[str, Any],
    company_counts: dict[str, int],
    source_stored: int,
) -> bool:
    company = str(job.get("company_name", "")).strip()
    max_per_company = int(source.get("max_per_company") or 3)
    max_jobs_per_run = int(source.get("max_jobs_per_run") or 12)
    if source_stored >= max_jobs_per_run:
        return False
    if company_counts.get(company, 0) >= max_per_company:
        return False
    return True
