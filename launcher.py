from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
RUN_DIR = ROOT / ".run"
PID_FILE = RUN_DIR / "backend.pid"
OUT_LOG = RUN_DIR / "backend.log"
ERR_LOG = RUN_DIR / "backend.err.log"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"


def run_text(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True, encoding="mbcs", errors="ignore", stderr=subprocess.DEVNULL)
    except Exception:
        return ""


def port_pid() -> int | None:
    output = run_text(["netstat", "-ano"])
    marker = f":{PORT}"
    for line in output.splitlines():
        if marker in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return None


def pid_exists(pid: int) -> bool:
    output = run_text(["tasklist", "/FI", f"PID eq {pid}"])
    return str(pid) in output


def process_command(pid: int) -> str:
    output = run_text([
        "powershell",
        "-NoProfile",
        "-Command",
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction SilentlyContinue; if ($p) {{ $p.Name; $p.CommandLine }}",
    ])
    if output.strip():
        return output

    output = run_text([
        "wmic",
        "process",
        "where",
        f"ProcessId={pid}",
        "get",
        "Name,CommandLine",
        "/format:list",
    ])
    return output


def pid_from_file() -> int | None:
    try:
        raw = PID_FILE.read_text(encoding="ascii").strip()
        return int(raw) if raw.isdigit() else None
    except Exception:
        return None


def is_our_backend(pid: int) -> bool:
    saved_pid = pid_from_file()
    cmd = process_command(pid).lower()
    if saved_pid == pid and not cmd.strip():
        return True
    looks_like_backend = "python" in cmd and "uvicorn" in cmd and "main:app" in cmd and str(PORT) in cmd
    if not looks_like_backend:
        return False
    return saved_pid == pid or f"--port {PORT}" in cmd or f"--port\r\r\n{PORT}" in cmd


def wait_port(up: bool, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        active = port_pid() is not None
        if active == up:
            return True
        time.sleep(0.3)
    return False


def build_if_needed() -> None:
    index = FRONTEND / "dist" / "index.html"
    if index.exists():
        print("[web] dist ready")
        return
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js not found. Please install Node.js, then run: cd frontend && npm install && npm run build")
    if not vite.exists():
        raise RuntimeError("Frontend dependencies not found. Please run: cd frontend && npm install && npm run build")
    print("[web] dist missing, building...")
    subprocess.check_call([node, str(vite), "build"], cwd=str(FRONTEND))


def start() -> int:
    RUN_DIR.mkdir(exist_ok=True)

    current = port_pid()
    if current is not None:
        if is_our_backend(current):
            PID_FILE.write_text(str(current), encoding="ascii")
            print(f"[backend] already running, pid={current}")
            open_browser()
            return 0
        print(f"[backend] port {PORT} is occupied by another process, pid={current}")
        print("[backend] not starting, to avoid affecting other projects")
        return 1

    stale = pid_from_file()
    if stale and not pid_exists(stale):
        PID_FILE.unlink(missing_ok=True)

    build_if_needed()
    print(f"[backend] starting on {URL}")
    stdout = OUT_LOG.open("a", encoding="utf-8", errors="ignore")
    stderr = ERR_LOG.open("a", encoding="utf-8", errors="ignore")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(BACKEND),
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(proc.pid), encoding="ascii")

    if not wait_port(True, timeout=20.0):
        print(f"[backend] start timed out, check {ERR_LOG}")
        return 1

    print(f"[backend] started, pid={proc.pid}")
    open_browser()
    return 0


def stop() -> int:
    pid = pid_from_file()
    if pid is None:
        pid = port_pid()
        if pid is None:
            print("[backend] pid file not found; nothing to stop")
            print("[backend] leaving any unrelated port owner untouched")
            return 0

    if not pid_exists(pid):
        print(f"[backend] saved pid {pid} no longer exists")
        PID_FILE.unlink(missing_ok=True)
        return 0

    if not is_our_backend(pid):
        print(f"[backend] pid {pid} does not match this project's uvicorn process")
        print("[backend] refusing to stop it")
        return 1

    print(f"[backend] stopping pid={pid}")
    subprocess.call(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PID_FILE.unlink(missing_ok=True)
    wait_port(False, timeout=8.0)
    print("[backend] stopped")
    return 0


def status() -> int:
    pid = port_pid()
    saved = pid_from_file()
    if pid is None:
        print(f"[status] stopped, url={URL}")
        if saved and not pid_exists(saved):
            print(f"[status] removing stale pid file: {saved}")
            PID_FILE.unlink(missing_ok=True)
        return 0
    if is_our_backend(pid):
        print(f"[status] running, pid={pid}, url={URL}")
        return 0
    print(f"[status] port {PORT} occupied by another process, pid={pid}")
    return 1


def open_browser() -> None:
    if os.environ.get("JOB_RADAR_NO_BROWSER") == "1":
        return
    webbrowser.open(URL)


def main() -> int:
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    if action == "start":
        return start()
    if action == "stop":
        return stop()
    if action == "status":
        return status()
    print("usage: python launcher.py [start|stop|status]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
