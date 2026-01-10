import base64

def get_activated_course_ids(configuration: dict) -> list[str]:
    """Lấy danh sách course_id đã kích hoạt từ cấu hình."""
    course_keys = list(configuration.get("course_keys", []))
    vender_id = configuration.get("vender_id", "")

    course_ids = []
    for key in course_keys:
        try:
            decoded_bytes = base64.b64decode(key)
            decoded_str = decoded_bytes.decode("utf-8")

            course_id = decoded_str.split(";")[0]
            vender_id_in_key = decoded_str.split(";")[1]

            if vender_id_in_key == vender_id:
                course_ids.append(course_id)
        except (base64.binascii.Error, UnicodeDecodeError, IndexError):
            continue
    return course_ids