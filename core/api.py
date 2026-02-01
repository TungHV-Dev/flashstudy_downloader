import json
from typing import Any, Dict, Tuple

import requests

from core.utils import get_device_info, log_event


def backend_headers(config: Dict[str, Any]) -> Dict[str, str]:
    device = {"device_id": config.get("device_id") or get_device_info().get("device_id")}
    base_headers = {
        "x-api-key": config.get("api_key", ""),
        "x-license-key": config.get("license_key", ""),
        "x-app-name": config.get("app_name", ""),
        "x-device-id": device.get("device_id", ""),
    }
    return {k: v for k, v in base_headers.items() if v}


def verify_license(config: Dict[str, Any], device_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any] | str]:
    base = config.get("backend_base_url")
    if not base:
        return False, "Thiếu backend_base_url trong .conf.json"
    license_key = config.get("license_key")
    if not license_key:
        return False, "Thiếu license_key"
    try:
        resp = requests.post(
            f"{base}/license/verify",
            json={
                "license_key": license_key,
                "device_name": device_info.get("device_name"),
                "os": device_info.get("os"),
            },
            headers=backend_headers(config),
            timeout=20,
        )
        if resp.status_code != 200:
            try:
                msg = (resp.json() or {}).get("message")
            except Exception:
                msg = None
            log_event("ext_verify_license", "FAIL", msg or f"status={resp.status_code}")
            return False, msg or f"License verify thất bại: status={resp.status_code}"
        data = resp.json() or {}
        if data.get("code") != 0:
            log_event("ext_verify_license", "FAIL", data.get("message") or "invalid")
            return False, data.get("message") or "License không hợp lệ"
        log_event("ext_verify_license", "SUCCESS")
        return True, data.get("data") or {}
    except Exception as exc:
        log_event("ext_verify_license", "FAIL", str(exc))
        return False, f"Lỗi verify license: {exc}"

def enqueue_download_job(
    config: Dict[str, Any],
    video_id: str,
    video_url: str,
    title: str | None = None,
    lesson_id: str | None = None,
    course_id: str | None = None,
    video_key_token: str | None = None,
) -> Tuple[bool, Dict[str, Any] | str]:
    base = config.get("backend_base_url")
    if not base:
        return False, "Thiếu backend_base_url trong .conf.json"
    if not video_id or not video_url:
        return False, "Thiếu video_id hoặc video_url"
    payload = {
        "video_id": video_id,
        "video_url": video_url,
        "title": title,
        "lesson_id": lesson_id,
        "course_id": course_id,
        "video_key_token": video_key_token or config.get("video_key_token"),
    }
    try:
        resp = requests.post(
            f"{base}/flashstudy/download/enqueue",
            json=payload,
            headers=backend_headers(config),
            timeout=20,
        )
        if resp.status_code != 200:
            try:
                msg = (resp.json() or {}).get("message")
            except Exception:
                msg = None
            log_event("ext_enqueue_download", "FAIL", msg or f"status={resp.status_code}")
            return False, msg or f"Enqueue thất bại: status={resp.status_code}"
        data = resp.json() or {}
        if data.get("code") != 0:
            log_event("ext_enqueue_download", "FAIL", data.get("message") or "failed")
            return False, data.get("message") or "Enqueue thất bại"
        log_event("ext_enqueue_download", "SUCCESS")
        return True, data.get("data") or {}
    except Exception as exc:
        log_event("ext_enqueue_download", "FAIL", str(exc))
        return False, f"Lỗi enqueue download: {exc}"


def get_download_statuses(
    config: Dict[str, Any], video_ids: list[str]
) -> Tuple[bool, Dict[str, Any] | str]:
    base = config.get("backend_base_url")
    if not base:
        return False, "Thiếu backend_base_url trong .conf.json"
    if not video_ids:
        return True, {}
    try:
        resp = requests.post(
            f"{base}/flashstudy/download/status-by-video",
            json={"video_ids": video_ids},
            headers=backend_headers(config),
            timeout=20,
        )
        if resp.status_code != 200:
            try:
                msg = (resp.json() or {}).get("message")
            except Exception:
                msg = None
            log_event("ext_get_status", "FAIL", msg or f"status={resp.status_code}")
            return False, msg or f"Lỗi lấy status: status={resp.status_code}"
        data = resp.json() or {}
        if data.get("code") != 0:
            log_event("ext_get_status", "FAIL", data.get("message") or "failed")
            return False, data.get("message") or "Lỗi lấy status"
        log_event("ext_get_status", "SUCCESS")
        return True, data.get("data") or {}
    except Exception as exc:
        log_event("ext_get_status", "FAIL", str(exc))
        return False, f"Lỗi lấy status: {exc}"


def get_drive_link(config: Dict[str, Any], video_id: str) -> Tuple[bool, Dict[str, Any] | str]:
    base = config.get("backend_base_url")
    if not base:
        return False, "Thiếu backend_base_url trong .conf.json"
    if not video_id:
        return False, "Thiếu video_id"
    try:
        resp = requests.get(
            f"{base}/flashstudy/download/link/{video_id}",
            headers=backend_headers(config),
            timeout=20,
        )
        if resp.status_code != 200:
            try:
                msg = (resp.json() or {}).get("message")
            except Exception:
                msg = None
            log_event("ext_get_link", "FAIL", msg or f"status={resp.status_code}")
            return False, msg or f"Lỗi lấy link: status={resp.status_code}"
        data = resp.json() or {}
        if data.get("code") != 0:
            log_event("ext_get_link", "FAIL", data.get("message") or "failed")
            return False, data.get("message") or "Lỗi lấy link"
        log_event("ext_get_link", "SUCCESS")
        return True, data.get("data") or {}
    except Exception as exc:
        log_event("ext_get_link", "FAIL", str(exc))
        return False, f"Lỗi lấy link: {exc}"


def schedule_cleanup(config: Dict[str, Any], video_id: str) -> Tuple[bool, Dict[str, Any] | str]:
    base = config.get("backend_base_url")
    if not base:
        return False, "Thiếu backend_base_url trong .conf.json"
    if not video_id:
        return False, "Thiếu video_id"
    try:
        resp = requests.post(
            f"{base}/flashstudy/download/schedule-cleanup",
            json={"video_id": video_id},
            headers=backend_headers(config),
            timeout=20,
        )
        if resp.status_code != 200:
            try:
                msg = (resp.json() or {}).get("message")
            except Exception:
                msg = None
            log_event("ext_schedule_cleanup", "FAIL", msg or f"status={resp.status_code}")
            return False, msg or f"Lỗi schedule cleanup: status={resp.status_code}"
        data = resp.json() or {}
        if data.get("code") != 0:
            log_event("ext_schedule_cleanup", "FAIL", data.get("message") or "failed")
            return False, data.get("message") or "Lỗi schedule cleanup"
        log_event("ext_schedule_cleanup", "SUCCESS")
        return True, data.get("data") or {}
    except Exception as exc:
        log_event("ext_schedule_cleanup", "FAIL", str(exc))
        return False, f"Lỗi schedule cleanup: {exc}"


class FlashStudyAPI:
    def __init__(self):
        self.token = ""

    def login(self, phone: str, password: str):
        url = "https://api.flashstudy.vn/api/v1/client/auth/login"
        payload = {"phone": phone, "password": password}
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            status = (data or {}).get("status") or {}
            if status.get("code") == 200:
                token = ((data or {}).get("data") or {}).get("access_token")
                if token:
                    self.token = token
                    return 0, token
                return -1, {
                    "status_code": status.get("code", resp.status_code),
                    "message": "Missing access_token in response",
                }
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Login failed"),
            }
        except requests.RequestException as e:
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            return -1, {"status_code": -1, "message": "Invalid JSON response"}
        
    def get_my_courses(self):
        url = "https://api.flashstudy.vn/api/v1/client/my-course"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            status = (data or {}).get("status") or {}
            if status.get("code") == 200:
                courses = ((data or {}).get("data") or {}).get("courses", []) or []
                results = []
                for course in courses:
                    teachers = course.get("teachers") or []
                    teacher_name = ""
                    if teachers and isinstance(teachers, list):
                        teacher_name = teachers[0].get("name") or ""
                    results.append(
                        {
                            "course_id": course.get("id"),
                            "course_name": course.get("name") or "",
                            "teacher_name": teacher_name,
                            "expired_time": course.get("expired_time") or "",
                        }
                    )
                return 0, results
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Fetch courses failed"),
            }
        except requests.RequestException as e:
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            return -1, {"status_code": -1, "message": "Invalid JSON response"}

    def get_course_detail(self, course_id: int):
        url = f"https://api.flashstudy.vn/api/v1/client/my-course/detail-lesson-in-course/{course_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            status = (data or {}).get("status") or {}
            if status.get("code") == 200:
                lessons = ((data or {}).get("data") or {}).get("lessons", []) or []
                results = []
                for lesson in lessons:
                    children = lesson.get("children") or []
                    child_items = []
                    if isinstance(children, list):
                        for child in children:
                            child_items.append(
                                {
                                    "lesson_id": child.get("id"),
                                    "lesson_name": child.get("name") or "",
                                    "type": child.get("type"),
                                }
                            )
                    results.append(
                        {
                            "lesson_id": lesson.get("id"),
                            "lesson_name": lesson.get("name") or "",
                            "type": lesson.get("type"),
                            "children": child_items,
                        }
                    )
                return 0, results
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Fetch course detail failed"),
            }
        except requests.RequestException as e:
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            return -1, {"status_code": -1, "message": "Invalid JSON response"}

    def get_lesson_detail(self, lesson_id: int):
        url = f"https://api.flashstudy.vn/api/v1/client/my-course/lesson/{lesson_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            status = (data or {}).get("status") or {}
            if status.get("code") == 200:
                lesson = ((data or {}).get("data") or {}).get("lesson") or {}
                lesson_type = lesson.get("type")
                if lesson_type == 5:
                    return 0, {
                        "lesson_id": lesson.get("id"),
                        "lesson_name": lesson.get("name") or "",
                        "pdf_url": lesson.get("pdf_url") or "",
                    }
                video_urls = []
                for v in lesson.get("video_url") or []:
                    if v.get("type") == "vn" and v.get("url"):
                        video_urls.append(v.get("url"))
                result = {
                    "lesson_id": lesson.get("id"),
                    "lesson_name": lesson.get("name") or "",
                    "video_url": video_urls,
                    "document_url": lesson.get("document_url") or "",
                    "document_answer_url": lesson.get("document_answer_url") or "",
                }
                return 0, result
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Fetch lesson detail failed"),
            }
        except requests.RequestException as e:
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            return -1, {"status_code": -1, "message": "Invalid JSON response"}
