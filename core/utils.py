import json
import os
import time


def load_config(config_path: str) -> dict:
    if not config_path or not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def append_download_log(log_path: str, status: str, url: str, output_path: str, error: str):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{ts}\t{status}\t{output_path}\t{url}"
        if error:
            msg = f"{msg}\t{error}"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
