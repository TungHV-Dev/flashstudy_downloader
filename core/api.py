import requests
import json

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
