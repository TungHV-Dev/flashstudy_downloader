import base64
import requests
import json

class QandaAPI:
    def __init__(self, vender_id):
        self.vender_id = vender_id

    # Email: thanhthuong060606@gmail.com | Password: 123456
    def login(self, email: str, password: str):
        url = f"https://q2ab84c4bh.execute-api.ap-southeast-1.amazonaws.com/prod/student/signin?vendorId={self.vender_id}"

        password_base64 = base64.b64encode(password.encode()).decode()
        payload = {
            "email": email,
            "password": password_base64,
            "vendorId": self.vender_id
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.qandastudy.com",
            "Referer": "https://www.qandastudy.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            response_data = response.json()
            access_token = response_data.get("accessToken", None)
            student_id = response_data.get("studentId", None)
            user_id = response_data.get("id", None)

            data = {
                "access_token": access_token,
                "student_id": student_id,
                "user_id": user_id
            }
            return 0, data
        else:
            response_text = json.loads(response.text)
            data = {
                "status_code": response.status_code,
                "message": response_text.get("data", None) if response_text.get("data", None) else response.text
            }
            return -1, data

    def get_user_courses(self, user_id: str, access_token: str):
        url = f"https://87rvhd1ada.execute-api.ap-southeast-1.amazonaws.com/prod/user-permission?userId={user_id}&vendorId={self.vender_id}"

        headers = {
            "Authorization": f"{access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.qandastudy.com",
            "Referer": "https://www.qandastudy.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            response_data = response.json()
            online_courses = response_data.get("onlineCourses", [])
            response_courses = []
            for course in online_courses:
                response_courses.append({
                    "course_id": course.get("id", None),
                    "course_title": course.get("title", None)   
                })
            data = {
                "courses": response_courses
            }
            return 0, data
        else:
            response_text = json.loads(response.text)
            data = {
                "status_code": response.status_code,
                "message": response_text.get("data", None) if response_text.get("data", None) else response.text
            }
            return -1, data

    def get_course_layout(self, course_id: str, access_token: str):
        url = f"https://ww1ugkewmi.execute-api.ap-southeast-1.amazonaws.com/prod/course/layout/{course_id}?&vendorId={self.vender_id}"

        headers = {
            "Authorization": f"{access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.qandastudy.com",
            "Referer": "https://www.qandastudy.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            response_data = list(response.json() or [])

            chapters = []
            for item in response_data:
                lessons = []
                chapter_lessons = item.get("children", [])
                for les in chapter_lessons:
                    lessons.append({
                        "lesson_id": les.get("id", None),
                        "lesson_index": les.get("index", None),
                        "lesson_title": les.get("title", None),
                        "has_attachment": bool(les.get("data", {}).get("hasAttachment", False))
                    })
                chapters.append({
                    "chapter_id": item.get("id", None),
                    "chapter_index": item.get("index", None),
                    "chapter_title": item.get("title", None),
                    "chapter_lessons": lessons
                })
            data = {
                "chapters": chapters
            }
            return 0, data
        else:
            response_text = json.loads(response.text)
            data = {
                "status_code": response.status_code,
                "message": response_text.get("data", None) if response_text.get("data", None) else response.text
            }
            return -1, data
        
    def get_lesson_details(self, lesson_id: str, user_id: str, access_token: str):
        url = f"https://ww1ugkewmi.execute-api.ap-southeast-1.amazonaws.com/prod/unit/{lesson_id}?userId={user_id}&_populate=video&vendorId={self.vender_id}"

        headers = {
            "Authorization": f"{access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.qandastudy.com",
            "Referer": "https://www.qandastudy.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            response_data = response.json()
            video_data = response_data.get("video", {})
            syllabus_data = list(response_data.get("syllabus", []))

            data = {
                "title": response_data.get("title", ""),
                "video": {
                    "video_id": video_data.get("id", ""),
                    "link": video_data.get("link", ""),
                    "title": video_data.get("title", ""),
                    "duration": video_data.get("duration", 0),
                    "size": video_data.get("size", 0)
                },
                "syllabus": [{
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "link": f'{item.get("origin", {}).get("bucket", "")}/{item.get("origin", {}).get("link", "")}' if item.get("origin", {}) else "",
                    "mimeType": item.get("origin", {}).get("mimeType", "") if item.get("origin", {}) else ""
                } for item in syllabus_data]
            }
            return 0, data
        else:
            response_text = json.loads(response.text)
            data = {
                "status_code": response.status_code,
                "message": response_text.get("data", None) if response_text.get("data", None) else response.text
            }
            return -1, data
    