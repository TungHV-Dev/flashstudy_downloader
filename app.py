import os
import json
import tkinter as tk
import time
import sys
import subprocess
import re
import hashlib
from tkinter import messagebox, ttk, simpledialog
from core.api import FlashStudyAPI, verify_license, enqueue_download_job, get_download_statuses, get_drive_link
from core.utils import load_config, save_config, ensure_resource_dir, get_device_info

def app_root_dir() -> str:
    """
    Trả về thư mục đặt 'app_resource'.
    - Dev: thư mục chứa file .py
    - One-file/one-folder (mac/linux/win): dirname(sys.executable)
    - .app (macOS bundle): nhảy lên 3 cấp từ .../My.app/Contents/MacOS/...
    """
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        if sys.platform == "darwin" and ".app/" in exe:
            # đang chạy trong bundle .app
            return os.path.abspath(os.path.join(exe, "..", "..", ".."))
        # one-file/unix exe: dùng thư mục chứa executable
        return os.path.dirname(exe)
    # chạy từ source
    return os.path.dirname(os.path.abspath(__file__))


RESOURCE_DIR = os.path.join(app_root_dir(), "app_resource")
CONFIG_FILE_PATH = os.path.join(RESOURCE_DIR, ".conf.json")
TEMP_FILE_PATH = os.path.join(RESOURCE_DIR, ".temp.data")


class FlashStudyDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FlashStudy Downloader")
        self.root.minsize(960, 640)
        self._center_window(900, 560)

        # ---- ttk theme & styles ----
        self._init_style()

        # Load config + temp store
        ensure_resource_dir(RESOURCE_DIR)
        self.configuration = load_config(CONFIG_FILE_PATH)
        self.temp = self._load_temp_store()
        self.device_info = self._ensure_device_info()

        # API client
        self.AppApi = FlashStudyAPI()

        self.auth = None
        self.current_frame = None

        # status bar
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self._build_statusbar()

        if not self._verify_license_on_startup():
            self.root.destroy()
            return

        if self._auto_resume_session():
            # Có phiên còn hạn -> bỏ qua login
            self.show_course_selection()
            return

        self.show_login_screen()

    # ========== UI BUILDERS ==========

    def show_login_screen(self):
        self._switch_frame(ttk.Frame(self.root, padding=24))

        # outer container
        container = self.current_frame
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # centered column
        wrapper = ttk.Frame(container, style="Card.TFrame", padding=32)
        wrapper.grid(column=0, row=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # title
        title = ttk.Label(wrapper, text="Đăng nhập FlashStudy", style="Title.TLabel")
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        # SĐT
        ttk.Label(wrapper, text="Số điện thoại", style="Label.TLabel").grid(row=1, column=0, sticky="w")
        self.phone_var = tk.StringVar(value=self.temp.get("last_phone", ""))
        phone_entry = ttk.Entry(wrapper, textvariable=self.phone_var, width=36)
        phone_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        # Mật khẩu
        ttk.Label(wrapper, text="Mật khẩu", style="Label.TLabel").grid(row=3, column=0, sticky="w")
        self.password_var = tk.StringVar(value=self.temp.get("last_password", ""))
        self.password_entry = ttk.Entry(wrapper, textvariable=self.password_var, show="*", width=36)
        self.password_entry.grid(row=4, column=0, sticky="ew", pady=(4, 12))

        # toggle show password
        self._show_password = tk.BooleanVar(value=False)
        eye_btn = ttk.Checkbutton(
            wrapper,
            text="Hiện mật khẩu",
            variable=self._show_password,
            style="Switch.TCheckbutton",
            command=self._toggle_password,
        )
        eye_btn.grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        # remember me
        self.remember_me = tk.BooleanVar(value=True)
        ttk.Checkbutton(wrapper, text="Ghi nhớ mật khẩu", variable=self.remember_me).grid(
            row=5, column=0, sticky="w", pady=(0, 8)
        )

        # actions
        btn_row = ttk.Frame(wrapper)
        btn_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=0)

        login_btn = ttk.Button(btn_row, text="Đăng nhập", style="Primary.TButton", command=self._handle_login)
        login_btn.grid(row=0, column=1, sticky="e")

        # keyboard: Enter -> login
        self.root.bind("<Return>", lambda _e: self._handle_login())

        # focus
        if self.phone_var.get():
            self.password_entry.focus_set()
        else:
            phone_entry.focus_set()

        self._set_status("Nhập thông tin để đăng nhập")

    def show_course_selection(self):
        self._switch_frame(ttk.Frame(self.root, padding=24))
        wrapper = ttk.Frame(self.current_frame, style="Card.TFrame", padding=20)
        wrapper.pack(expand=True, fill="both")

        ttk.Label(wrapper, text="Danh sách khóa học", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        # fetch course list
        self._set_status("Đang tải danh sách khóa học…")
        code, courses = self.AppApi.get_my_courses()
        if code != 0:
            self._set_status("Không có khóa học trực tuyến")
            messagebox.showinfo("Thông báo", "Bạn chưa mua khóa học online nào")
            self.show_login_screen()
            return

        # Scrollable list
        list_wrap = ttk.Frame(wrapper)
        list_wrap.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        wrapper.grid_rowconfigure(1, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(list_wrap, highlightthickness=0, bg="#FFFFFF")
        vsb = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        rows_frame = tk.Frame(canvas, bg="#FFFFFF")
        rows_window = canvas.create_window((0, 0), window=rows_frame, anchor="nw")

        def _on_frame_config(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_config(e):
            canvas.itemconfigure(rows_window, width=e.width)

        rows_frame.bind("<Configure>", _on_frame_config)
        canvas.bind("<Configure>", _on_canvas_config)

        def _set_row_bg(frame, labels, bg):
            frame.configure(bg=bg)
            for lbl in labels:
                lbl.configure(bg=bg)

        for c in courses:
            row = tk.Frame(rows_frame, bg="#FFFFFF", padx=10, pady=8, highlightthickness=1, highlightbackground="#E2E8F0")
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=0)

            left = tk.Frame(row, bg="#FFFFFF")
            left.grid(row=0, column=0, sticky="w")

            title = tk.Label(
                left,
                text=c.get("course_name", ""),
                bg="#FFFFFF",
                fg="#0F172A",
                font=("SF Pro Text", 12, "bold"),
            )
            title.pack(anchor="w")

            meta_text = f"Giáo viên: {c.get('teacher_name', '')} • Hết hạn: {c.get('expired_time', '')}"
            meta = tk.Label(
                left,
                text=meta_text,
                bg="#FFFFFF",
                fg="#334155",
                font=("SF Pro Text", 10),
            )
            meta.pack(anchor="w", pady=(2, 0))

            btn = ttk.Button(
                row,
                text="Chi tiết",
                style="Primary.TButton",
                command=lambda cid=c.get("course_id"), cname=c.get("course_name", ""): self._open_course_detail(cid, cname),
            )
            btn.grid(row=0, column=1, sticky="e", padx=(12, 6))

            def _on_enter(_e, frame=row, labels=(title, meta)):
                _set_row_bg(frame, labels, "#F1F5F9")

            def _on_leave(_e, frame=row, labels=(title, meta)):
                _set_row_bg(frame, labels, "#FFFFFF")

            row.bind("<Enter>", _on_enter)
            row.bind("<Leave>", _on_leave)
            title.bind("<Enter>", _on_enter)
            title.bind("<Leave>", _on_leave)
            meta.bind("<Enter>", _on_enter)
            meta.bind("<Leave>", _on_leave)
            btn.bind("<Enter>", _on_enter)
            btn.bind("<Leave>", _on_leave)

        actions = ttk.Frame(wrapper, style="Card.TFrame")
        actions.grid(row=2, column=0, pady=(12, 0), sticky="e")
        ttk.Button(actions, text="Đăng xuất", style="Secondary.TButton", command=self.logout).pack(side="right")

        self._set_status(f"Đã tải {len(courses)} khóa học")

    def show_course_content(self, chapters_dict: dict, course_title: str = ""):
        self._switch_frame(ttk.Frame(self.root, padding=16))
        rootf = self.current_frame

        # Header
        header = ttk.Frame(rootf)
        header.pack(fill="x", pady=(0, 8))
        display_title = course_title.strip() or "Nội dung khóa học"
        ttk.Label(header, text=display_title, style="Title2.TLabel").pack(side="left")


        ttk.Button(header, text="Đăng xuất", style="Secondary.TButton", command=self.logout).pack(side="right")
        ttk.Button(header, text="⬅ Quay lại", style="Secondary.TButton", command=self._go_back_to_course_selection).pack(side="right", padx=(0, 8))

        # ----- Content list -----

        # ----- Lesson list -----
        list_wrap = ttk.Frame(rootf, style="Card.TFrame", padding=8)
        list_wrap.pack(expand=True, fill="both")

        self.lesson_canvas = tk.Canvas(list_wrap, highlightthickness=0, bg="#FFFFFF")
        vsb = ttk.Scrollbar(list_wrap, orient="vertical", command=self.lesson_canvas.yview)
        self.lesson_canvas.configure(yscrollcommand=vsb.set)
        self.lesson_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.course_items_frame = tk.Frame(self.lesson_canvas, bg="#FFFFFF")
        items_window = self.lesson_canvas.create_window((0, 0), window=self.course_items_frame, anchor="nw")

        def _on_items_config(_e):
            self.lesson_canvas.configure(scrollregion=self.lesson_canvas.bbox("all"))

        def _on_canvas_config(e):
            self.lesson_canvas.itemconfigure(items_window, width=e.width)

        self.course_items_frame.bind("<Configure>", _on_items_config)
        self.lesson_canvas.bind("<Configure>", _on_canvas_config)

        self._chapters_raw = self._coerce_chapters(chapters_dict)
        self._rebuild_course_tree()
    
    # ========== HANDLERS ==========

    def _handle_login(self):
        phone = (self.phone_var.get() or "").strip()
        password = self.password_var.get()
        if not phone or not password:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ Số điện thoại và Mật khẩu.")
            return

        self._set_status("Đang đăng nhập…")
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        code, login_response = self.AppApi.login(phone, password)
        self.root.config(cursor="")
        if code == 0:
            self.auth = {"access_token": login_response}
            payload = {
                "last_phone": phone,
                "last_password": password if self.remember_me.get() else "",
                "access_token": self.auth.get("access_token"),
                "login_at": time.time(),
            }
            self._save_temp_store(payload)
            self._set_status("Đăng nhập thành công")
            self.show_course_selection()
        else:
            self._set_status("Đăng nhập thất bại")
            messagebox.showerror(
                "Lỗi đăng nhập",
                f'Code: {login_response.get("status_code")} | Message: {login_response.get("message")}',
            )

    def _open_course_detail(self, course_id: str, course_title: str):
        code, lessons = self.AppApi.get_course_detail(course_id)
        if code != 0:
            messagebox.showerror("Lỗi", "Không lấy được nội dung khóa học.")
            return

        self._set_status(f"Đã chọn khoá + {course_title}")
        self.show_course_content(lessons, course_title=course_title)

    def _rebuild_course_tree(self):
        for w in self.course_items_frame.winfo_children():
            w.destroy()

        lessons = self._chapters_raw.get("lessons", [])
        for item in lessons:
            name = (item.get("lesson_name") or item.get("name") or "").strip()
            children = item.get("children") or []

            # Parent item (type=3)
            parent = tk.Frame(self.course_items_frame, bg="#FFFFFF", padx=10, pady=8, highlightthickness=1, highlightbackground="#E2E8F0")
            parent.pack(fill="x", pady=4)
            tk.Label(
                parent,
                text=name,
                bg="#FFFFFF",
                fg="#0F172A",
                font=("SF Pro Text", 12, "bold"),
            ).pack(anchor="w")

            for child in children:
                child_type = child.get("type")
                child_name = (child.get("lesson_name") or child.get("name") or "").strip()
                child_id = child.get("lesson_id") or child.get("id")
                child_row = tk.Frame(self.course_items_frame, bg="#FFFFFF", padx=28, pady=6)
                child_row.pack(fill="x")
                child_title = tk.Label(
                    child_row,
                    text=child_name,
                    bg="#FFFFFF",
                    fg="#0F172A",
                    font=("SF Pro Text", 11),
                )
                child_title.grid(row=0, column=0, sticky="w")
                if child_type in (1, 5):
                    btn_text = "Video và đáp án" if child_type == 1 else "Đề thi thử"
                    if child_type == 1:
                        action_cmd = lambda lid=child_id, lname=child_name: self._open_lesson_popup(
                            lid, {"lesson_title": lname}
                        )
                    else:
                        action_cmd = lambda lid=child_id: self._open_exam_link(lid)
                    action_btn = ttk.Button(
                        child_row,
                        text=btn_text,
                        style="Primary.TButton",
                        width=18,
                        command=action_cmd,
                    )
                    action_btn.grid(row=0, column=2, sticky="e", padx=(12, 6))
                child_row.grid_columnconfigure(0, weight=1)

                def _set_child_bg(frame, labels, bg):
                    frame.configure(bg=bg)
                    for lbl in labels:
                        lbl.configure(bg=bg)

                def _on_child_enter(_e, frame=child_row, labels=(child_title,)):
                    _set_child_bg(frame, labels, "#F1F5F9")

                def _on_child_leave(_e, frame=child_row, labels=(child_title,)):
                    _set_child_bg(frame, labels, "#FFFFFF")

                child_row.bind("<Enter>", _on_child_enter)
                child_row.bind("<Leave>", _on_child_leave)
                child_title.bind("<Enter>", _on_child_enter)
                child_title.bind("<Leave>", _on_child_leave)
                if child_type in (1, 5):
                    action_btn.bind("<Enter>", _on_child_enter)
                    action_btn.bind("<Leave>", _on_child_leave)

    def _fetch_lesson_details(self, lesson_id: str):
        """Gọi API lấy chi tiết bài học (video + syllabus)."""
        try:
            code, data = self.AppApi.get_lesson_detail(lesson_id)
            return code, data
        except Exception as e:
            print("fetch lesson details error:", e)
            return -1, {"message": "Không lấy được chi tiết bài học"}

    def _open_lesson_popup(self, lesson_id: str, meta: dict | None):
        code, data = self._fetch_lesson_details(lesson_id)
        if code != 0:
            messagebox.showerror("Lỗi", data.get("message", "Không lấy được chi tiết bài học"))
            return

        title = data.get("lesson_name") or (meta.get("lesson_title") if meta else "Bài học")
        video_urls = list(data.get("video_url", []) or [])
        doc_url = data.get("document_url") or ""
        doc_answer_url = data.get("document_answer_url") or ""

        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.minsize(720, 420)
        popup_bg = "#F1F5F9"
        win.configure(bg=popup_bg)
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        ww = win.winfo_width() or 720
        wh = win.winfo_height() or 420
        win.geometry(f"{ww}x{wh}+{int((sw - ww) / 2)}+{int((sh - wh) / 2.4)}")

        # --- main container ---
        container = tk.Frame(win, bg=popup_bg, padx=16, pady=16)
        container.pack(expand=True, fill="both")

        # Header
        tk.Label(container, text=title, bg=popup_bg, fg="#0F172A", font=("SF Pro Text", 20, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        # --- Video section ---
        tk.Label(container, text="File video", bg=popup_bg, fg="#0F172A", font=("SF Pro Text", 12, "bold")).pack(
            anchor="w"
        )
        video_frame = tk.Frame(container, bg="#FFFFFF", padx=12, pady=12, highlightthickness=1, highlightbackground="#E2E8F0")
        video_frame.pack(fill="x", pady=(6, 10))

        video_items = []
        for idx, url in enumerate(video_urls, start=1):
            fixed_url = self._normalize_video_url(url)
            vid = self._video_id_from_url(fixed_url)
            video_items.append({"index": idx, "url": fixed_url, "video_id": vid})

        status_map = self._fetch_download_statuses([v["video_id"] for v in video_items])

        if video_items:
            for item in video_items:
                idx = item["index"]
                url = item["url"]
                video_id = item["video_id"]
                status_info = (status_map or {}).get(video_id, {}) if video_id else {}
                status = status_info.get("status") or "not_found"
                tk.Label(video_frame, text=f"Video {idx}", bg="#FFFFFF", fg="#0F172A").grid(
                    row=idx - 1, column=0, sticky="w", pady=(0, 4)
                )
                download_btn = ttk.Button(
                    video_frame,
                    text="Tải về",
                    style="Primary.TButton",
                )
                download_btn.grid(row=idx - 1, column=1, sticky="e", padx=(16, 0), pady=(0, 4))
                download_btn.configure(
                    command=lambda u=url, idx=idx, vid=video_id, dbtn=download_btn: self._enqueue_video_job(
                        u, title, idx, lesson_id, vid, dbtn
                    )
                )

                video_items[idx - 1]["download_btn"] = download_btn

                if not url:
                    download_btn.state(["disabled"])
                else:
                    if status in ("queued", "in_progress"):
                        download_btn.config(text="Đang chờ server xử lý ...", state="disabled")
        else:
            tk.Label(video_frame, text="Video", bg="#FFFFFF", fg="#0F172A").grid(
                row=0, column=0, sticky="w", pady=(0, 4)
            )
            btn = ttk.Button(video_frame, text="Tải về", style="Primary.TButton")
            btn.state(["disabled"])
            btn.grid(row=0, column=1, sticky="e", padx=(16, 0), pady=(0, 4))
            tk.Label(video_frame, text="File chưa được up lên hệ thống", bg="#FFFFFF", fg="#64748B").grid(
                row=0, column=2, sticky="w", padx=(12, 0)
            )

        # --- Documents section ---
        tk.Label(container, text="File tài liệu", bg=popup_bg, fg="#0F172A", font=("SF Pro Text", 12, "bold")).pack(
            anchor="w"
        )
        doc_frame = tk.Frame(container, bg="#FFFFFF", padx=12, pady=12, highlightthickness=1, highlightbackground="#E2E8F0")
        doc_frame.pack(expand=True, fill="both", pady=(6, 0))

        row = 0
        tk.Label(doc_frame, text="Đề bài", bg="#FFFFFF", fg="#0F172A").grid(
            row=row, column=0, sticky="w", pady=(0, 4)
        )
        doc_btn = ttk.Button(doc_frame, text="Mở", style="Primary.TButton",
                command=lambda: self._open_in_chrome(doc_url))
        doc_btn.grid(row=row, column=1, sticky="e", padx=(16, 0), pady=(0, 4))
        if not doc_url:
            doc_btn.state(["disabled"])
            tk.Label(doc_frame, text="File chưa được up lên hệ thống", bg="#FFFFFF", fg="#64748B").grid(
                row=row, column=2, sticky="w", padx=(12, 0)
            )
        row += 1
        tk.Label(doc_frame, text="Đáp án", bg="#FFFFFF", fg="#0F172A").grid(
            row=row, column=0, sticky="w", pady=(0, 4)
        )
        ans_btn = ttk.Button(doc_frame, text="Mở", style="Primary.TButton",
                command=lambda: self._open_in_chrome(doc_answer_url))
        ans_btn.grid(row=row, column=1, sticky="e", padx=(16, 0), pady=(0, 4))
        if not doc_answer_url:
            ans_btn.state(["disabled"])
            tk.Label(doc_frame, text="File chưa được up lên hệ thống", bg="#FFFFFF", fg="#64748B").grid(
                row=row, column=2, sticky="w", padx=(12, 0)
            )

        def _on_popup_close():
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_popup_close)

        def _refresh_statuses():
            ids = [v.get("video_id") for v in video_items if v.get("video_id")]
            latest = self._fetch_download_statuses(ids)
            for v in video_items:
                vid = v.get("video_id")
                status_info = (latest or {}).get(vid, {}) if vid else {}
                status = status_info.get("status") or "not_found"
                d_btn = v.get("download_btn")
                if not d_btn:
                    continue
                if status in ("queued", "in_progress"):
                    d_btn.config(text="Đang chờ server xử lý ...", state="disabled")
                else:
                    d_btn.config(text="Tải về", state="normal")

        # --- Buttons (Đóng/Refresh) ---
        btns = tk.Frame(container, bg=popup_bg)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Reset trạng thái", command=_refresh_statuses).pack(side="left")
        ttk.Button(btns, text="Đóng", command=_on_popup_close).pack(side="right")

        # Không dùng downloader trong màn này

    def _normalize_video_url(self, url: str) -> str:
        if not url:
            return ""
        return url.replace("/Data/", "/DataNew/", 1)

    def _video_id_from_url(self, url: str) -> str:
        if not url:
            return ""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

    def _fetch_download_statuses(self, video_ids: list[str]) -> dict:
        ok, data_or_err = get_download_statuses(self.configuration, video_ids)
        if not ok:
            return {}
        return data_or_err if isinstance(data_or_err, dict) else {}

    def _enqueue_video_job(
        self,
        url: str,
        lesson_title: str,
        index: int,
        lesson_id: str,
        video_id: str,
        download_btn=None,
    ):
        fixed_url = self._normalize_video_url(url)
        if not fixed_url:
            messagebox.showwarning("Thiếu link", "Không có đường dẫn video.")
            return

        ok, data_or_err = get_drive_link(self.configuration, video_id)
        if ok:
            link = (data_or_err or {}).get("drive_link")
            if link:
                self._show_drive_link(link)
                return

        title = f"{lesson_title} - Video {index}"
        ok, data_or_err = enqueue_download_job(
            self.configuration,
            video_id,
            fixed_url,
            title=title,
            lesson_id=lesson_id,
        )
        if not ok:
            messagebox.showerror("Lỗi", data_or_err or "Không thể tạo job tải video.")
            return
        messagebox.showinfo("Thông báo", "Đã đưa video vào hàng đợi tải. Vui lòng kiểm tra trạng thái.")
        if download_btn and download_btn.winfo_exists():
            download_btn.config(text="Đang chờ server xử lý ...", state="disabled")

    def _show_drive_link(self, link: str):
        if not link:
            messagebox.showwarning("Thiếu link", "Chưa có link tải.")
            return
        try:
            import webbrowser
            webbrowser.open_new_tab(link)
        except Exception:
            pass

    def _open_exam_link(self, lesson_id: str):
        code, data = self._fetch_lesson_details(lesson_id)
        if code != 0:
            messagebox.showerror("Lỗi", data.get("message", "Không lấy được chi tiết bài học"))
            return

        pdf_url = data.get("pdf_url") or ""
        if not pdf_url:
            messagebox.showinfo("Thông báo", "Không tìm thấy link đề")
            return
        self._open_in_chrome(pdf_url)

    def _open_in_chrome(self, url: str):
        if not url:
            messagebox.showwarning("Thiếu link", "Tài liệu chưa có đường dẫn tải.")
            return
        
        try:
            # Ưu tiên mở bằng Chrome theo hệ điều hành
            if sys.platform == "darwin":  # macOS
                subprocess.Popen(["open", "-a", "Google Chrome", url])
            elif sys.platform.startswith("win"):
                # Windows
                subprocess.Popen(['cmd', '/c', 'start', 'chrome', url], shell=True)
            else:
                # Linux: thử một số tên binary phổ biến của Chrome/Chromium
                for c in ("google-chrome", "chrome", "chromium", "chromium-browser"):
                    try:
                        subprocess.Popen([c, url])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    # Fallback: mở bằng trình duyệt mặc định
                    webbrowser.open_new_tab(url)
        except Exception as e:
            # Fallback an toàn nếu Chrome không mở được
            try:
                import webbrowser
                webbrowser.open_new_tab(url)
            except Exception:
                messagebox.showerror("Lỗi", f"Không thể mở link tải.\n{e}")

    def logout(self):
        """Đăng xuất: xóa phiên, xóa token, quay lại màn đăng nhập."""
        confirm = messagebox.askyesno("Đăng xuất", "Bạn có chắc muốn đăng xuất không?")
        if not confirm:
            return

        # Xóa dữ liệu đăng nhập tạm
        self._clear_temp_store()
        self.auth = None
        self._set_status("Đã đăng xuất.", show_note=False)

        # Quay lại màn đăng nhập
        self.show_login_screen()
    
    # ========= HELPERS ==========
    def _go_back_to_course_selection(self):
        """Quay lại màn chọn khóa học."""
        self.show_course_selection()
    
    def _switch_frame(self, new_frame: ttk.Frame):
        if self.current_frame is not None:
            self.current_frame.destroy()
        self.current_frame = new_frame
        self.current_frame.pack(expand=True, fill="both")

    def _toggle_password(self):
        self.password_entry.configure(show="" if self._show_password.get() else "*")

    def _init_style(self):
        style = ttk.Style()
        # cross-platform: 'clam' thường hiện đại & nhất quán hơn trên macOS
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # màu sắc cơ bản (có thể tinh chỉnh theo brand của bạn)
        PRIMARY = "#3B82F6"   # blue-500
        PRIMARY_DARK = "#1D4ED8"
        BG = "#F5F7FB"
        CARD_BG = "#FFFFFF"
        TEXT = "#0F172A"
        MUTED = "#64748B"

        # background app
        self.root.configure(bg=BG)

        # Card container
        style.configure("Card.TFrame", background=CARD_BG, relief="flat", borderwidth=1)
        style.configure("Title.TLabel", background=CARD_BG, foreground=TEXT, font=("SF Pro Text", 20, "bold"))
        style.configure("Title2.TLabel", background=CARD_BG, foreground=TEXT, font=("SF Pro Text", 14, "bold"))
        style.configure("Label.TLabel", background=CARD_BG, foreground=MUTED, font=("SF Pro Text", 11))

        # Entry
        style.configure("TEntry", fieldbackground="#FFFFFF")
        style.map(
            "TEntry",
            bordercolor=[("focus", PRIMARY)],
            lightcolor=[("focus", PRIMARY)],
            darkcolor=[("focus", PRIMARY)],
        )

        # Buttons
        style.configure(
            "Primary.TButton",
            font=("SF Pro Text", 10, "bold"),
            foreground="#FFFFFF",
            background=PRIMARY,
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_DARK)],
            relief=[("pressed", "sunken")],
            foreground=[("disabled", "#64748B")],
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#E2E8F0")],
        )

        style.configure("Secondary.TButton",
            font=("SF Pro Text", 10),
            foreground="#334155",
            background="#E2E8F0",
            borderwidth=0,
            relief="flat",
            padding=(4, 4)
        )
        style.map("Secondary.TButton",
            background=[("active", "#CBD5E1"), ("pressed", "#CBD5E1")]
        )

        # Switch-like checkbutton (text only)
        style.configure("Switch.TCheckbutton", background=CARD_BG, foreground=TEXT)

        # Combobox
        style.configure("TCombobox", arrowsize=18)
        style.map("TCombobox", fieldbackground=[("readonly", "#FFFFFF")])

    def _build_statusbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(side="bottom", fill="x")

        ttk.Separator(self.root, orient="horizontal").pack(side="bottom", fill="x")

        # Bố cục 2 cột: bên trái là message, bên phải là ghi chú
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_columnconfigure(1, weight=0)

        # Message chính (bên trái)
        self.status_label = ttk.Label(bar, textvariable=self.status_var, anchor="w", padding=(12, 6))
        self.status_label.grid(row=0, column=0, sticky="ew")

        # Ghi chú (bên phải) — mặc định ẩn
        self.note_label = ttk.Label(
            bar,
            text="🟢 Video | ⚫ Tệp tài liệu",
            anchor="e",
            padding=(12, 6),
            foreground="#475569"
        )
        self.note_label.grid(row=0, column=1, sticky="e")
        self.note_label.grid_remove()  # Ẩn mặc định

    def _set_status(self, text: str, show_note: bool = False):
        """Cập nhật message ở thanh trạng thái. Nếu show_note=True -> hiển thị ghi chú Video/Tệp."""
        self.status_var.set(text)
        if hasattr(self, "note_label"):
            if show_note:
                self.note_label.grid()  # Hiện ghi chú
            else:
                self.note_label.grid_remove()  # Ẩn ghi chú

    def _center_window(self, w: int, h: int):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = int((sw - w) / 2)
        y = int((sh - h) / 2.4)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _coerce_chapters(self, data):
        """
        Chuẩn hoá dữ liệu lessons về dạng {'lessons': [...]}
        để TreeView luôn đọc được, dù API trả list hay bọc trong key khác.
        """
        try:
            if isinstance(data, dict) and "lessons" in data and isinstance(data["lessons"], list):
                return data
            if isinstance(data, list):
                return {"lessons": data}
            if isinstance(data, dict) and "data" in data:
                d = data["data"]
                if isinstance(d, dict) and "lessons" in d:
                    return {"lessons": d["lessons"]}
                if isinstance(d, list):
                    return {"lessons": d}
            return {"lessons": []}
        except Exception as e:
            print("coerce lessons error:", e)
            return {"lessons": []}

    def _load_temp_store(self):
        try:
            with open(TEMP_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            print("Load temp store error:", e)
            return {}

    def _save_temp_store(self, payload: dict):
        try:
            os.makedirs(RESOURCE_DIR, exist_ok=True)
            self.temp.update(payload or {})
            with open(TEMP_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.temp, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Save temp store error:", e)

    def _clear_temp_store(self):
        self.temp = {}
        try:
            if os.path.exists(TEMP_FILE_PATH):
                os.remove(TEMP_FILE_PATH)
        except Exception as e:
            print("Clear temp store error:", e)

    def _auto_resume_session(self) -> bool:
        """Nếu có token trong .temp.data thì xác thực nhanh; hợp lệ -> set self.auth."""
        token = self.temp.get("access_token")
        if not token:
            return False
        try:
            # Gọi API nhẹ để kiểm tra token (thay bằng endpoint check nếu bạn có)
            self.AppApi.token = token
            code, courses = self.AppApi.get_my_courses()
            if code == 0:
                self.auth = {"access_token": token}
                self._set_status(f"Đã khôi phục phiên cho {self.temp.get('last_phone','') or 'người dùng'}.")
                return True
            # token invalid -> xoá cache
            self._clear_temp_store()
            return False
        except Exception as e:
            print("Auto-resume error:", e)
            return False

    def _ensure_device_info(self):
        info = get_device_info()
        updated = False
        if not self.configuration.get("device_id"):
            self.configuration["device_id"] = info.get("device_id")
            updated = True
        if not self.configuration.get("device_name"):
            self.configuration["device_name"] = info.get("device_name")
            updated = True
        if not self.configuration.get("os"):
            self.configuration["os"] = info.get("os")
            updated = True
        if updated:
            save_config(CONFIG_FILE_PATH, self.configuration)
        return {
            "device_id": self.configuration.get("device_id"),
            "device_name": self.configuration.get("device_name"),
            "os": self.configuration.get("os"),
        }

    def _verify_license_on_startup(self):
        while True:
            license_key = (self.configuration or {}).get("license_key")
            if not license_key:
                new_key = simpledialog.askstring(
                    "License yêu cầu",
                    "Nhập license key để tiếp tục:",
                    parent=self.root,
                )
                if not new_key:
                    messagebox.showerror("Thiếu license", "Thiếu license key. App sẽ đóng.")
                    return False
                if not re.fullmatch(
                    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                    new_key.strip(),
                ):
                    messagebox.showerror("Cảnh báo", "License key không đúng định dạng.")
                    continue
                self.configuration["license_key"] = new_key.strip()
                save_config(CONFIG_FILE_PATH, self.configuration)
                license_key = self.configuration["license_key"]
            else:
                if not re.fullmatch(
                    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                    license_key.strip(),
                ):
                    messagebox.showerror("Cảnh báo", "License key không đúng định dạng.")
                    self.configuration["license_key"] = ""
                    save_config(CONFIG_FILE_PATH, self.configuration)
                    continue

            ok, data_or_err = verify_license(self.configuration, self.device_info)
            if ok:
                self._set_status("License hợp lệ.")
                return True

            messagebox.showerror("License không hợp lệ", data_or_err or "Vui lòng nhập license khác.")
            self.configuration["license_key"] = ""
            save_config(CONFIG_FILE_PATH, self.configuration)

if __name__ == "__main__":
    root = tk.Tk()
    app = FlashStudyDownloaderApp(root)
    root.mainloop()
