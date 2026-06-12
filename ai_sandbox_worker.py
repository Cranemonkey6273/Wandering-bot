"""Standalone AI sandbox worker for Wandering Bot.

Run this on a VPS or local machine that has Docker installed. The dashboard
stays on Railway as the control plane and dispatches approved jobs here.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request


APP = Flask(__name__)
WORKER_TOKEN = os.getenv("WANDERING_AI_WORKER_TOKEN", "").strip()
WORKSPACE_ROOT = Path(os.getenv("WANDERING_AI_WORKER_ROOT", "./ai-agent-workspaces")).resolve()
JOBS_FILE = Path(os.getenv("WANDERING_AI_WORKER_JOBS_FILE", "./ai_sandbox_worker_jobs.json")).resolve()
DEFAULT_DOCKER_IMAGE = os.getenv("WANDERING_AI_WORKER_DOCKER_IMAGE", "python:3.12-slim").strip() or "python:3.12-slim"
CPU_LIMIT = os.getenv("WANDERING_AI_WORKER_CPU_LIMIT", "2").strip() or "2"
MEMORY_LIMIT = os.getenv("WANDERING_AI_WORKER_MEMORY_LIMIT", "2g").strip() or "2g"
try:
    DEFAULT_TIMEOUT_SECONDS = int(float(os.getenv("WANDERING_AI_WORKER_TIMEOUT_SECONDS", "900")))
except (TypeError, ValueError):
    DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_TIMEOUT_SECONDS = max(10, min(3600, DEFAULT_TIMEOUT_SECONDS))
MAX_LOG_CHARS = 12000
SECRET_KEYS = ("token", "secret", "password", "api_key", "apikey", "authorization", "private_key")
BLOCKED_COMMAND_TERMS = (
    "docker.sock",
    "--privileged",
    " --pid=host",
    " --net=host",
    "mkfs",
    "format ",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
)
JOB_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def redact_log(value: Any) -> str:
    output = str(value or "")
    for key in SECRET_KEYS:
        pattern = re.compile(rf"({re.escape(key)}\s*[=:]\s*)([^\s,;]+)", re.IGNORECASE)
        output = pattern.sub(r"\1***", output)
    for env_key, env_value in os.environ.items():
        if not env_value or len(env_value) < 8:
            continue
        if any(secret_key in env_key.lower() for secret_key in SECRET_KEYS):
            output = output.replace(env_value, "***")
    if len(output) > MAX_LOG_CHARS:
        output = output[:MAX_LOG_CHARS].rstrip() + "\n... log truncated"
    return output


def load_jobs() -> dict[str, dict[str, Any]]:
    if not JOBS_FILE.exists():
        return {}
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_jobs(jobs: dict[str, dict[str, Any]]) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(json.dumps(jobs, indent=2, sort_keys=True), encoding="utf-8")


def update_job(job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    with JOB_LOCK:
        jobs = load_jobs()
        job = jobs.setdefault(job_id, {"id": job_id})
        job.update(updates)
        save_jobs(jobs)
        return dict(job)


def get_job(job_id: str) -> dict[str, Any] | None:
    with JOB_LOCK:
        return load_jobs().get(job_id)


def auth_ok() -> bool:
    if not WORKER_TOKEN:
        return False
    expected = f"Bearer {WORKER_TOKEN}"
    return request.headers.get("Authorization", "") == expected


@APP.before_request
def require_worker_auth():
    if request.path == "/health":
        return None
    if not WORKER_TOKEN:
        return json_error("worker token is not configured", 503)
    if not auth_ok():
        return json_error("unauthorized", 401)
    return None


def command_is_allowed(command: str) -> tuple[bool, str]:
    text = str(command or "").strip()
    lower = text.lower()
    if not text:
        return False, "command is required"
    if len(text) > 4000:
        return False, "command is too long"
    for term in BLOCKED_COMMAND_TERMS:
        if term in lower:
            return False, f"blocked unsafe command term: {term.strip()}"
    return True, ""


def workspace_path(project_path: Any = "") -> tuple[Path | None, str]:
    requested = str(project_path or "").strip().replace("\\", "/")
    workspace = (WORKSPACE_ROOT / requested).resolve() if requested else WORKSPACE_ROOT
    try:
        workspace.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None, "workspace path is outside the configured worker root"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace, ""


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    command = str(job.get("command") or "")
    allowed, reason = command_is_allowed(command)
    if not allowed:
        update_job(job_id, {"status": "blocked", "stderr": reason, "finished_at": utc_now(), "exit_code": None})
        return
    workspace, workspace_error = workspace_path(job.get("project_path"))
    if workspace_error or not workspace:
        update_job(job_id, {"status": "blocked", "stderr": workspace_error, "finished_at": utc_now(), "exit_code": None})
        return
    timeout = int(job.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    timeout = max(10, min(3600, timeout))
    docker_image = str(job.get("docker_image") or DEFAULT_DOCKER_IMAGE).strip() or DEFAULT_DOCKER_IMAGE
    update_job(job_id, {"status": "running", "started_at": utc_now(), "stdout": "", "stderr": "", "exit_code": None})
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        CPU_LIMIT,
        "--memory",
        MEMORY_LIMIT,
        "-v",
        f"{workspace}:/workspace:rw",
        "-w",
        "/workspace",
        docker_image,
        "sh",
        "-lc",
        command,
    ]
    try:
        result = subprocess.run(docker_command, capture_output=True, text=True, timeout=timeout)
        update_job(
            job_id,
            {
                "status": "done" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "stdout": redact_log(result.stdout),
                "stderr": redact_log(result.stderr),
                "finished_at": utc_now(),
            },
        )
    except subprocess.TimeoutExpired as error:
        update_job(
            job_id,
            {
                "status": "failed",
                "exit_code": None,
                "stdout": redact_log(getattr(error, "stdout", "") or ""),
                "stderr": f"Command timed out after {timeout}s.",
                "finished_at": utc_now(),
            },
        )
    except Exception as error:
        update_job(job_id, {"status": "failed", "exit_code": None, "stdout": "", "stderr": redact_log(str(error)), "finished_at": utc_now()})


@APP.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "wandering-ai-sandbox-worker",
            "token_configured": bool(WORKER_TOKEN),
            "workspace_root": str(WORKSPACE_ROOT),
            "docker_image": DEFAULT_DOCKER_IMAGE,
        }
    )


@APP.post("/api/agent/jobs")
def create_job():
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command") or "").strip()
    allowed, reason = command_is_allowed(command)
    if not allowed:
        return json_error(reason)
    job_id = str(payload.get("job_id") or f"worker-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}")
    job = {
        "id": job_id,
        "remote_job_id": job_id,
        "task_id": str(payload.get("task_id") or ""),
        "command": command,
        "project_path": str(payload.get("project_path") or ""),
        "reason": str(payload.get("reason") or ""),
        "requested_by": str(payload.get("requested_by") or ""),
        "timeout_seconds": int(payload.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
        "docker_image": str(payload.get("docker_image") or DEFAULT_DOCKER_IMAGE),
        "status": "queued",
        "created_at": utc_now(),
        "started_at": "",
        "finished_at": "",
        "exit_code": None,
        "stdout": "",
        "stderr": "",
    }
    with JOB_LOCK:
        jobs = load_jobs()
        jobs[job_id] = job
        save_jobs(jobs)
    thread = threading.Thread(target=run_job, args=(job_id,), name=f"ai-worker-{job_id}", daemon=True)
    thread.start()
    return jsonify({"ok": True, "job": job, "remote_job_id": job_id, "status": job["status"]})


@APP.get("/api/agent/jobs/<job_id>")
def read_job(job_id: str):
    job = get_job(job_id)
    if not job:
        return json_error("job not found", 404)
    return jsonify({"ok": True, "job": job, "remote_job_id": job_id, "status": job.get("status")})


@APP.post("/api/agent/jobs/<job_id>/cancel")
def cancel_job(job_id: str):
    job = get_job(job_id)
    if not job:
        return json_error("job not found", 404)
    if str(job.get("status") or "") in {"done", "failed", "blocked"}:
        return jsonify({"ok": True, "job": job, "status": job.get("status")})
    job = update_job(job_id, {"status": "cancelled", "stderr": "Cancelled by dashboard owner.", "finished_at": utc_now()})
    return jsonify({"ok": True, "job": job, "status": job.get("status")})


if __name__ == "__main__":
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("PORT", "8787"))
    APP.run(host="0.0.0.0", port=port)
