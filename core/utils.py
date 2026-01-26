import json
import os
import time
import hashlib
import platform
import uuid


def ensure_resource_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_config(config_path: str) -> dict:
    if not config_path or not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(config_path: str, data: dict) -> None:
    payload = data if isinstance(data, dict) else {}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def log_event(action: str, status: str, message: str = "") -> None:
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        log_path = os.path.join(base_dir, "app_resource", ".log")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{ts}\t{action}\t{status}"
        if message:
            msg = f"{msg}\t{message}"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def append_download_log(status: str, url: str, output_path: str, error: str):
    details = f"output={output_path}\turl={url}"
    if error:
        details = f"{details}\terror={error}"
    log_event("download_video", status, details)


def get_device_info() -> dict:
    hostname = platform.node() or os.getenv("COMPUTERNAME") or "unknown-device"
    os_name = platform.system().lower() or "unknown-os"
    os_version = platform.release() or ""
    raw_id = f"{uuid.getnode()}-{hostname}-{platform.platform()}"
    device_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:32]

    return {
        "device_id": device_id,
        "device_name": hostname,
        "os": f"{os_name} {os_version}".strip(),
    }

