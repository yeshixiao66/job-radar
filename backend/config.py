from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SOURCES_FILE = ROOT_DIR / "sources.yaml"
SETTINGS_FILE = DATA_DIR / "settings.json"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    request_timeout: int = 15
    llm_timeout: int = 30


def get_settings() -> Settings:
    saved = load_saved_settings()
    return Settings(
        api_key=os.getenv("OPENAI_API_KEY") or saved.get("api_key", ""),
        base_url=os.getenv("OPENAI_BASE_URL") or saved.get("base_url", ""),
        model=os.getenv("OPENAI_MODEL") or saved.get("model", ""),
        request_timeout=int(os.getenv("JOB_RADAR_TIMEOUT", "15")),
        llm_timeout=int(os.getenv("JOB_RADAR_LLM_TIMEOUT", "30")),
    )


def load_saved_settings() -> dict[str, str]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "profiles" in data:
            active_name = data.get("active_profile", "")
            profiles = data.get("profiles", [])
            active = next((item for item in profiles if item.get("name") == active_name), None)
            if active is None and profiles:
                active = profiles[0]
            data = active or {}
        return {
            "profile_name": str(data.get("name", data.get("profile_name", ""))),
            "api_key": str(data.get("api_key", "")),
            "base_url": str(data.get("base_url", "")),
            "model": str(data.get("model", "")),
        }
    except Exception:
        return {}


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = load_settings_file()
    profiles = config.get("profiles", [])
    original_name = str(payload.get("original_name", "")).strip()
    profile_name = str(payload.get("profile_name", "")).strip() or original_name or "默认 API"
    current = next(
        (item for item in profiles if item.get("name") == (original_name or profile_name)),
        {},
    )
    api_key = str(payload.get("api_key", "")).strip()
    profile = {
        "name": profile_name,
        "api_key": api_key if api_key else current.get("api_key", ""),
        "base_url": str(payload.get("base_url", "")).strip(),
        "model": str(payload.get("model", "")).strip(),
    }
    profiles = [item for item in profiles if item.get("name") not in {original_name, profile_name}]
    profiles.append(profile)
    active_profile = config.get("active_profile", "")
    if not active_profile or active_profile == original_name or current:
        active_profile = profile_name
    data = {"active_profile": active_profile, "profiles": profiles}
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return public_settings(profile)


def load_settings_file() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {"active_profile": "", "profiles": []}
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "profiles" not in data:
            name = str(data.get("profile_name", "") or "默认 API")
            normalized = {
                "active_profile": name,
                "profiles": [
                    {
                        "name": name,
                        "api_key": str(data.get("api_key", "")),
                        "base_url": str(data.get("base_url", "")),
                        "model": str(data.get("model", "")),
                    }
                ],
            }
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with SETTINGS_FILE.open("w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            return normalized
        return data
    except Exception:
        return {"active_profile": "", "profiles": []}


def set_active_profile(profile_name: str) -> dict[str, Any]:
    config = load_settings_file()
    profiles = config.get("profiles", [])
    if not any(item.get("name") == profile_name for item in profiles):
        return public_settings()
    config["active_profile"] = profile_name
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    active = next(item for item in profiles if item.get("name") == profile_name)
    return public_settings(active)


def delete_profile(profile_name: str) -> dict[str, Any]:
    profile_name = str(profile_name or "").strip()
    config = load_settings_file()
    profiles = config.get("profiles", [])
    remaining = [item for item in profiles if item.get("name") != profile_name]
    if len(remaining) == len(profiles):
        return public_settings()

    active_profile = config.get("active_profile", "")
    if active_profile == profile_name:
        active_profile = str(remaining[0].get("name", "")) if remaining else ""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump({"active_profile": active_profile, "profiles": remaining}, f, ensure_ascii=False, indent=2)
    return public_settings()


def public_settings(data: dict[str, str] | None = None) -> dict[str, Any]:
    config = load_settings_file()
    settings = data or load_saved_settings()
    key = settings.get("api_key", "")
    preview = mask_key(key)
    return {
        "profile_name": settings.get("name") or settings.get("profile_name", config.get("active_profile", "")),
        "api_key_set": bool(key),
        "api_key_preview": preview,
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
        "active_profile": config.get("active_profile", ""),
        "profiles": [
            {
                "name": item.get("name", ""),
                "api_key_set": bool(item.get("api_key", "")),
                "api_key_preview": mask_key(str(item.get("api_key", ""))),
                "base_url": item.get("base_url", ""),
                "model": item.get("model", ""),
            }
            for item in config.get("profiles", [])
        ],
    }


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * max(len(key) - 8, 8)}{key[-4:]}"


def load_sources() -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError:
        return []

    if not SOURCES_FILE.exists():
        return []

    with SOURCES_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    sources = [source for source in data.get("sources", []) if source.get("enabled", True)]
    return sorted(sources, key=lambda source: int(source.get("priority") or 0), reverse=True)
