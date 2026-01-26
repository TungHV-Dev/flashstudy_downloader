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
            return False, msg or f"License verify thất bại: status={resp.status_code}"
        data = resp.json() or {}
        if data.get("code") != 0:
            return False, data.get("message") or "License không hợp lệ"
        return True, data.get("data") or {}
    except Exception as exc:
        return False, f"Lỗi verify license: {exc}"


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
                    log_event("login", "SUCCESS")
                    return 0, token
                log_event("login", "FAIL", "missing access_token")
                return -1, {
                    "status_code": status.get("code", resp.status_code),
                    "message": "Missing access_token in response",
                }
            log_event("login", "FAIL", status.get("message", "Login failed"))
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Login failed"),
            }
        except requests.RequestException as e:
            log_event("login", "FAIL", str(e))
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            log_event("login", "FAIL", "Invalid JSON response")
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
                log_event("get_my_courses", "SUCCESS")
                return 0, results
            log_event("get_my_courses", "FAIL", status.get("message", "Fetch courses failed"))
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Fetch courses failed"),
            }
        except requests.RequestException as e:
            log_event("get_my_courses", "FAIL", str(e))
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            log_event("get_my_courses", "FAIL", "Invalid JSON response")
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
                log_event("get_course_detail", "SUCCESS")
                return 0, results
            log_event("get_course_detail", "FAIL", status.get("message", "Fetch course detail failed"))
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Fetch course detail failed"),
            }
        except requests.RequestException as e:
            log_event("get_course_detail", "FAIL", str(e))
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            log_event("get_course_detail", "FAIL", "Invalid JSON response")
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
                    log_event("get_lesson_detail", "SUCCESS")
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
                log_event("get_lesson_detail", "SUCCESS")
                return 0, result
            log_event("get_lesson_detail", "FAIL", status.get("message", "Fetch lesson detail failed"))
            return -1, {
                "status_code": status.get("code", resp.status_code),
                "message": status.get("message", "Fetch lesson detail failed"),
            }
        except requests.RequestException as e:
            log_event("get_lesson_detail", "FAIL", str(e))
            return -1, {"status_code": -1, "message": str(e)}
        except json.JSONDecodeError:
            log_event("get_lesson_detail", "FAIL", "Invalid JSON response")
            return -1, {"status_code": -1, "message": "Invalid JSON response"}
