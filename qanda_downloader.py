import os
import json
import tkinter as tk
import time
import sys 
import subprocess
import webbrowser
import re
import shutil
import contextlib
import threading
import stat
from tkinter import filedialog as fd
from tkinter import messagebox, ttk
from core.api import QandaAPI
from core.utils import get_activated_course_ids

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

class QandaDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Qanda Video Downloader")
        self.root.minsize(960, 640)
        self._center_window(900, 560)

        # ---- ttk theme & styles ----
        self._init_style()

        # Load temp store
        self.temp = self._load_temp_store()

        # Load configuration
        self.AppApi = None
        self.configuration = {}
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                self.configuration = json.load(f)
                vender_id = self.configuration.get("vender_id", "")
                if vender_id:
                    self.AppApi = QandaAPI(vender_id)
        except FileNotFoundError:
            # Không chặn app chạy nếu thiếu config
            self.configuration = {}
        
        if not self.AppApi:
            messagebox.showerror("Cấu hình lỗi", "Không tìm thấy cấu hình hợp lệ. Vui lòng kiểm tra")
            self.root.destroy()
            return

        self.auth = None
        self.current_frame = None

        # status bar
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self._build_statusbar()

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
        title = ttk.Label(wrapper, text="Đăng nhập", style="Title.TLabel")
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        # Email
        ttk.Label(wrapper, text="Email", style="Label.TLabel").grid(row=1, column=0, sticky="w")
        self.email_var = tk.StringVar(value=self.temp.get("last_email", ""))
        email_entry = ttk.Entry(wrapper, textvariable=self.email_var, width=36)
        email_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        # Mật khẩu
        ttk.Label(wrapper, text="Mật khẩu", style="Label.TLabel").grid(row=3, column=0, sticky="w")
        self.password_var = tk.StringVar()
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
        ttk.Checkbutton(wrapper, text="Ghi nhớ email", variable=self.remember_me).grid(
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
        if self.email_var.get():
            self.password_entry.focus_set()
        else:
            email_entry.focus_set()

        self._set_status("Nhập thông tin để đăng nhập")

    def show_course_selection(self):
        self._switch_frame(ttk.Frame(self.root, padding=24))
        wrapper = ttk.Frame(self.current_frame, style="Card.TFrame", padding=28)
        wrapper.pack(expand=True)

        ttk.Label(wrapper, text="Chọn khóa học", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        # fetch course list
        self._set_status("Đang tải danh sách khóa học…")
        code, data_courses = self.AppApi.get_user_courses(self.auth.get("user_id"), self.auth.get("access_token"))
        if code != 0:
            self._set_status("Không có khóa học trực tuyến")
            messagebox.showinfo("Thông báo", "Bạn chưa mua khóa học online nào")
            self.show_login_screen()
            return

        # Validate courses
        user_courses = list(data_courses.get("courses", []))
        activated_courses = get_activated_course_ids(self.configuration)
        user_activated_courses = [c for c in user_courses if c.get("course_id") in activated_courses]

        self.course_map = {c["course_title"]: c["course_id"] for c in user_activated_courses}
        course_titles = sorted(self.course_map.keys())

        ttk.Label(wrapper, text="Khoá học", style="Label.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.course_var = tk.StringVar()
        cmb = ttk.Combobox(wrapper, textvariable=self.course_var, values=course_titles, width=46, state="readonly")
        cmb.grid(row=2, column=0, sticky="ew")
        cmb.bind("<<ComboboxSelected>>", lambda _e: self._set_status("Đã chọn: " + self.course_var.get()))

        actions = ttk.Frame(wrapper, style="Card.TFrame")
        actions.grid(row=3, column=0, pady=(16, 0))

        # Căn giữa hàng nút
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        btn_style_common = {"width": 14, "padding": (0, 6)}

        logout_btn = ttk.Button(actions, text="Đăng xuất", style="Secondary.TButton", command=self.logout)
        logout_btn.grid(row=0, column=0, padx=(8, 8), pady=(0, 0))

        confirm_btn = ttk.Button(actions, text="Xác nhận", style="Primary.TButton", command=self._confirm_course)
        confirm_btn.grid(row=0, column=1, padx=(8, 8), pady=(0, 0))

        # Căn giữa cả cụm hai nút
        actions.grid_columnconfigure((0, 1), weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        self._set_status(f"Đã tải {len(course_titles)} khóa học")

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

        # ----- Toolbar -----
        toolbar = ttk.Frame(rootf)
        toolbar.pack(fill="x", pady=(0, 8))

        ttk.Label(toolbar, text="Tìm:").pack(side="left", padx=(0, 6))
        self._course_search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self._course_search_var, width=35)
        search_entry.pack(side="left")
        search_entry.bind("<KeyRelease>", lambda e: self._rebuild_course_tree())

        # Chỉ còn 1 bộ lọc: hiện bài có tệp
        self._show_file_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Hiện bài có tệp",
                        variable=self._show_file_var,
                        command=self._rebuild_course_tree).pack(side="left", padx=(12, 0))

        ttk.Frame(toolbar).pack(side="left", expand=True, fill="x")
        ttk.Button(toolbar, text="Mở rộng tất cả", style="Primary.TButton",
                command=lambda: self._expand_collapse_all(True)).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Thu gọn tất cả",
                command=lambda: self._expand_collapse_all(False)).pack(side="left")

        # ----- Treeview -----
        treewrap = ttk.Frame(rootf, style="Card.TFrame", padding=8)
        treewrap.pack(expand=True, fill="both")

        # Cột #0 = "Chương" (số chương)
        columns = ("title", "has_attach", "actions")
        self.course_tree = ttk.Treeview(treewrap, columns=columns, show="tree headings", height=18)

        self.course_tree.heading("#0", text="Chương")
        self.course_tree.heading("title", text="Chủ đề / Bài")
        self.course_tree.heading("has_attach", text="Có tài liệu")
        self.course_tree.heading("actions", text="Hành động")

        self.course_tree.column("#0", width=90, anchor="center", stretch=False)
        self.course_tree.column("title", width=540, stretch=True)
        self.course_tree.column("has_attach", width=110, anchor="center", stretch=False)
        self.course_tree.column("actions", width=140, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(treewrap, orient="vertical", command=self.course_tree.yview)
        hsb = ttk.Scrollbar(treewrap, orient="horizontal", command=self.course_tree.xview)
        self.course_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.course_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        treewrap.grid_rowconfigure(0, weight=1)
        treewrap.grid_columnconfigure(0, weight=1)

        # Tag màu (tùy chọn): chỉ giữ 1 màu cho hàng chứa tài liệu, video để mặc định
        self.course_tree.tag_configure("file", foreground="#0F172A")
        self.course_tree.tag_configure("plain", foreground="#0F172A")

        self._chapters_raw = self._coerce_chapters(chapters_dict)
        self._rebuild_course_tree()

        # Click vào cột Hành động -> mở popup chi tiết
        self.course_tree.bind("<Button-1>", self._on_tree_click_actions)
        self._set_status("Click 'Chi tiết' để xem & tải nội dung.", show_note=False)
    
    # ========== HANDLERS ==========

    def _handle_login(self):
        email = (self.email_var.get() or "").strip()
        password = self.password_var.get()
        if not email or not password:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ Email và Mật khẩu.")
            return

        self._set_status("Đang đăng nhập…")
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        code, login_response = self.AppApi.login(email, password)
        self.root.config(cursor="")
        if code == 0:
            self.auth = login_response
            payload = {
                "last_email": email if self.remember_me.get() else "",
                "access_token": self.auth.get("access_token"),
                "user_id": self.auth.get("user_id"),
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

    def _confirm_course(self):
        selected_course_title = self.course_var.get()
        selected_course_id = self.course_map.get(selected_course_title)
        if not (selected_course_id and selected_course_title):
            messagebox.showwarning("Thông báo", "Vui lòng chọn một khóa học.")
            return

        self._set_status("Đang tải nội dung khóa học…")
        code, chapters = self.AppApi.get_course_layout(selected_course_id, self.auth.get("access_token"))
        if code != 0:
            self._set_status("Không lấy được nội dung khóa học")
            messagebox.showerror("Lỗi", "Không lấy được nội dung khóa học.")
            return

        # Tạm thời thông báo; bạn có thể tiếp tục build UI danh sách chương/bài ở đây
        self._set_status(f"Đã chọn: {selected_course_title}")
        self.show_course_content(chapters, course_title=selected_course_title)

    def _rebuild_course_tree(self):
        q = (self._course_search_var.get() or "").strip().lower()
        show_file = self._show_file_var.get()

        self.course_tree.delete(*self.course_tree.get_children())

        chapters = sorted(self._chapters_raw.get("chapters", []),
                        key=lambda c: c.get("chapter_index", 0))

        for ch in chapters:
            ch_index = ch.get("chapter_index", "")
            ch_title = (ch.get("chapter_title") or "").strip()
            ch_iid   = f"chap:{ch.get('chapter_id')}"
            lessons  = sorted(ch.get("chapter_lessons", []),
                            key=lambda l: l.get("lesson_index", 0))

            # Lọc theo search & ONLY 'has_attachment'
            filtered_lessons = []
            for les in lessons:
                title = les.get("lesson_title") or ""
                has_att = bool(les.get("has_attachment"))
                ok_kind = (has_att if show_file else True)   # nếu bật lọc -> chỉ bài có tệp
                ok_search = (q in title.lower() or q in ch_title.lower()) if q else True
                if ok_kind and ok_search:
                    filtered_lessons.append(les)

            if not filtered_lessons and q and q not in ch_title.lower():
                continue

            # Hàng chương
            self.course_tree.insert(
                "", "end", iid=ch_iid,
                text=ch_index,
                values=(ch_title, "", ""),  # cột 2 tên chương
                tags=("plain",), open=True
            )

            # Hàng bài
            for les in filtered_lessons:
                les_iid = f"les:{les.get('lesson_id')}"
                has_att = bool(les.get("has_attachment"))
                has_text = "Có" if has_att else "Không"
                action_text = "Chi tiết"
                tag = ("file",) if has_att else ("plain",)
                self.course_tree.insert(
                    ch_iid, "end", iid=les_iid,
                    text="",
                    values=(les.get("lesson_title", ""), has_text, action_text),
                    tags=tag
                )

    def _expand_collapse_all(self, expand: bool):
        """Mở rộng/thu gọn toàn bộ chương."""
        for iid in self.course_tree.get_children(""):
            self.course_tree.item(iid, open=expand)

    def _on_tree_click_actions(self, event):
        region = self.course_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.course_tree.identify_row(event.y)
        col_id = self.course_tree.identify_column(event.x)  # '#1': title, '#2': has_attach, '#3': actions
        if not row_id or not row_id.startswith("les:"):
            return
        if col_id != "#3":
            return

        lesson_id = row_id.split("les:", 1)[1]
        # Tìm meta cơ bản để lấy tên
        meta = None
        for ch in self._chapters_raw.get("chapters", []):
            for les in ch.get("chapter_lessons", []):
                if les.get("lesson_id") == lesson_id:
                    meta = les
                    break
            if meta: break

        self._open_lesson_popup(lesson_id, meta)

    def _format_duration(self, milliseconds: int) -> str:
        try:
            s = int(milliseconds / 1000)
            h, rem = divmod(s, 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        except:
            return "00:00:00"

    def _fetch_lesson_details(self, lesson_id: str):
        """Gọi API lấy chi tiết bài học (video + syllabus)."""
        try:
            code, data = self.AppApi.get_lesson_details(lesson_id, self.auth.get("user_id"), self.auth.get("access_token"))
            return code, data
        except Exception as e:
            print("fetch lesson details error:", e)
            return -1, {"message": "Không lấy được chi tiết bài học"}

    def _open_lesson_popup(self, lesson_id: str, meta: dict | None):
        self._set_status(f"Xem chi tiết bài học {meta.get('lesson_title') if meta else ''}", show_note=False)
        code, data = self._fetch_lesson_details(lesson_id)
        if code != 0:
            messagebox.showerror("Lỗi", data.get("message", "Không lấy được chi tiết bài học"))
            self._set_status("Tải chi tiết thất bại", show_note=False)
            return

        title = data.get("title") or (meta.get("lesson_title") if meta else "Bài học")
        video = data.get("video", {}) or {}
        syllabus = list(data.get("syllabus", []) or [])

        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.minsize(720, 420)

        # --- main container ---
        container = ttk.Frame(win, padding=16)
        container.pack(expand=True, fill="both")

        # Header
        ttk.Label(container, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 8))

        # --- Video section ---
        video_frame = ttk.LabelFrame(container, text="Video bài giảng", padding=12)
        video_frame.pack(fill="x", pady=(0, 8))

        v_title = video.get("title") or "(không có)"
        v_duration = self._format_duration(video.get("duration", 0))
        ttk.Label(video_frame, text=f"Tên video: {v_title}").grid(row=0, column=0, sticky="w")
        ttk.Label(video_frame, text=f"Thời lượng: {v_duration}").grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Nút tải video
        btns_frame = ttk.Frame(video_frame)
        btns_frame.grid(row=0, column=1, rowspan=2, padx=(40, 0), sticky="n")

        btn_dl = ttk.Button(btns_frame, text="Tải video", style="Primary.TButton")
        btn_dl.pack(fill="x", pady=(0, 6))  # căn cùng chiều ngang, có khoảng cách nhỏ

        btn_cancel = ttk.Button(btns_frame, text="Huỷ", style="Secondary.TButton")
        btn_cancel.pack(fill="x")
        btn_cancel.state(["disabled"])

        # --- Khu vực trạng thái tải ---
        dl_frame = ttk.Frame(video_frame)
        dl_frame.grid(row=2, column=0, columnspan=3, pady=(8, 0), sticky="ew")
        dl_frame.grid_remove()

        # Status (spinner sẽ ghi vào đây)
        lbl_status = ttk.Label(dl_frame, text="", width=30)   # NEW: status riêng
        lbl_status.grid(row=0, column=0, sticky="w")

        # Progress bar
        pb = ttk.Progressbar(dl_frame, orient="horizontal", mode="determinate", length=260)
        pb.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # Label hiển thị dung lượng
        lbl_progress = ttk.Label(dl_frame, text="", width=24)
        lbl_progress.grid(row=1, column=1, sticky="w", padx=(8, 0))

        # --- Syllabus section ---
        syl_frame = ttk.LabelFrame(container, text="Tài liệu bài giảng", padding=12)
        syl_frame.pack(expand=True, fill="both")

        syl_columns = ("title", "act")
        syl_tree = ttk.Treeview(syl_frame, columns=syl_columns, show="headings", height=8)
        syl_tree.heading("title", text="Tiêu đề")
        syl_tree.heading("act", text="Tải")
        syl_tree.column("title", width=460, stretch=True)
        syl_tree.column("act", width=80, anchor="center", stretch=False)

        vs = ttk.Scrollbar(syl_frame, orient="vertical", command=syl_tree.yview)
        syl_tree.configure(yscrollcommand=vs.set)
        syl_tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        syl_frame.grid_rowconfigure(0, weight=1)
        syl_frame.grid_columnconfigure(0, weight=1)

        # Render syllabus rows
        for item in syllabus:
            syl_tree.insert("", "end", iid=f"syl:{item.get('id')}", values=(item.get("title",""), "Tải"))

        # Click tải từng tài liệu
        def _on_syl_click(e):
            r = syl_tree.identify_row(e.y)
            c = syl_tree.identify_column(e.x)
            if not r or c != "#2":   # '#2' là cột "Tải"
                return
            item_id = r.split("syl:", 1)[1]
            found = next((x for x in syllabus if str(x.get("id")) == item_id), None)
            if found:
                self._download_file_api(found)

        syl_tree.bind("<Button-1>", _on_syl_click)

        # NEW: trạng thái busy của popup + chặn đóng khi đang tải
        win._busy = False
        def _on_popup_close():
            if win._busy:
                messagebox.showinfo("Đang tải", "Vui lòng đợi tải xong rồi đóng cửa sổ.")
                return
            self._set_status("Click 'Chi tiết' để xem & tải nội dung.", show_note=False)
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_popup_close)

        # --- Buttons (Đóng) ---
        btns = ttk.Frame(container)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Đóng", command=_on_popup_close).pack(side="right")

        # NEW: cờ báo đã nhận progress lần đầu để tắt spinner
        download_ctx = {"total_mb": 0.0}

        def on_start():
            win._busy = True
            btn_dl.state(["disabled"]); btn_cancel.state(["!disabled"])
            dl_frame.grid()  # ⬅️ HIỆN khu vực tải khi bắt đầu
            lbl_status.config(text="Đang chuẩn bị tải")
            self._start_spinner(lbl_status, "Đang chuẩn bị tải")
            # set mặc định để progress không trống nếu chưa biết size
            download_ctx["total_mb"] = max((video.get("size", 0) or 0)/ (1024*1024), 1.0)
            pb.config(value=0.0, maximum=download_ctx["total_mb"])
            lbl_progress.config(text=f"0.0/{download_ctx['total_mb']:.1f} MB")

        def on_progress(current_mb, total_mb):
            # total_mb có thể cập nhật lần đầu -> nhớ lại để Progressbar ăn theo
            if total_mb and abs(total_mb - download_ctx["total_mb"]) > 1e-6:
                download_ctx["total_mb"] = total_mb
                pb.config(maximum=total_mb)
            # cập nhật theo GIÁ TRỊ TUYỆT ĐỐI
            current_mb = max(current_mb, 0.0)
            pb.config(value=min(current_mb, download_ctx["total_mb"]))
            lbl_progress.config(text=f"{current_mb:.1f}/{download_ctx['total_mb']:.1f} MB")
            pb.update_idletasks()  # đảm bảo vẽ ngay trên macOS

        def on_finish(ok, msg=None):
            self._stop_spinner(lbl_status)
            win._busy = False
            btn_cancel.state(["disabled"]); btn_dl.state(["!disabled"])
            if ok:
                pb.config(value=download_ctx["total_mb"])
                lbl_status.config(text="✅ Hoàn tất")
                messagebox.showinfo("Hoàn tất", msg or "Đã tải xong video.")
            else:
                pb.config(value=0)
                lbl_status.config(text="❌ Lỗi tải")
                lbl_progress.config(text=f"0.0/{download_ctx['total_mb']:.1f} MB")

        def on_cancel(proc):
            if proc and proc.poll() is None:
                proc.terminate()
            self._stop_spinner(lbl_status)
            win._busy = False
            lbl_status.config(text="🛑 Đã huỷ")
            pb.config(value=0)
            btn_cancel.state(["disabled"]); btn_dl.state(["!disabled"])
            # (tuỳ ý) Ẩn khu vực tải sau khi huỷ để gọn UI
            dl_frame.grid_remove()

        btn_dl.configure(command=lambda: self._download_video_with_ui(
            video, pb, btn_cancel, on_progress, on_start, on_finish, on_cancel, download_ctx
        ))

    def _download_video_with_ui(self, video, pb, btn_cancel,
                            on_progress, on_start, on_finish, on_cancel, download_ctx):
        link = (video or {}).get("link") or ""
        title = (video or {}).get("title") or "Video bài giảng"
        if not link:
            messagebox.showwarning("Thiếu link", "Không có đường dẫn video.")
            return

        base_url  = "https://media.izteach.vn"
        link_path = link.strip("/")
        candidates = [
            f"{base_url}/{link_path}/playlist.m3u8",
            f"{base_url}/{link_path}/720p.m3u8",
            f"{base_url}/{link_path}/480p.m3u8",
            f"{base_url}/{link_path}/playlist_drm.m3u8",
        ]

        folder = self._select_download_dir()
        if not folder:
            return
        out_final = os.path.join(folder, self._sanitize_filename(title) + ".mp4")
        out_part  = out_final + ".part"   # << dùng để poll kích thước

        # chọn ffmpeg
        ffmpeg_bin = self._ensure_ffmpeg()
        if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
            messagebox.showerror("Thiếu ffmpeg", "Không tìm thấy ffmpeg. Hãy đặt vào ffmpeg/<os>/")
            return

        # --- START UI ---
        self.root.after(0, on_start)

        # lấy tổng MB ước lượng (nếu API có size)
        est_total_mb = max((video.get("size", 0) or 0) / (1024*1024), 1.0)
        download_ctx["total_mb"] = est_total_mb
        pb.config(maximum=est_total_mb, value=0.0)
        self.root.after(120, on_progress, 0.0, est_total_mb)

        # Poll kích thước file .part
        poll_state = {"job": None, "running": True}
        def _poll_file_progress():
            if not poll_state["running"]:
                return
            try:
                if os.path.exists(out_part):
                    current_mb = os.path.getsize(out_part) / (1024*1024)
                    on_progress(current_mb, download_ctx["total_mb"])
            except Exception:
                pass
            finally:
                poll_state["job"] = self.root.after(250, _poll_file_progress)
        _poll_file_progress()

        # worker tải
        proc_ref = {"proc": None}
        def _download_thread():
            ok, used_url, err = self._download_hls_sequential_subproc_ui(
                candidates, out_final, ffmpeg_bin, video.get("size", 0), proc_ref=proc_ref
            )
            poll_state["running"] = False
            if poll_state["job"]:
                with contextlib.suppress(Exception):
                    self.root.after_cancel(poll_state["job"])
            self.root.after(0, lambda: on_finish(ok, out_final if ok else err))
        threading.Thread(target=_download_thread, daemon=True).start()

        def _cancel_action():
            poll_state["running"] = False
            if poll_state["job"]:
                with contextlib.suppress(Exception):
                    self.root.after_cancel(poll_state["job"])
            on_cancel(proc_ref.get("proc"))
        btn_cancel.configure(command=_cancel_action)

    def _download_hls_sequential_subproc_ui(self, candidates, out_final, ffmpeg_path, total_video_size,
                                        on_progress=None, proc_ref=None):
        base, ext = os.path.splitext(out_final)
        if ext.lower() != ".mp4":
            out_final = base + ".mp4"
        out_part = out_final + ".part"
        os.makedirs(os.path.dirname(out_final) or ".", exist_ok=True)

        with contextlib.suppress(Exception):
            if os.path.exists(out_part):
                os.remove(out_part)

        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        referer = "https://www.qandastudy.com"
        origin  = "https://www.qandastudy.com"
        ff_headers = f"User-Agent: {ua}\r\nReferer: {referer}\r\nOrigin: {origin}"

        for url in candidates:
            with contextlib.suppress(Exception):
                if os.path.exists(out_part):
                    os.remove(out_part)

            cmd = [
                ffmpeg_path, "-y",
                "-hide_banner",
                "-loglevel", "error",                 # yên tĩnh để không ghi pipe
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                "-headers", ff_headers,
                "-user_agent", ua,
                "-referer", referer,
                "-i", url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-f", "mp4",
                out_part,
            ]

            proc = None
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,       # không mở pipe => không kẹt buffer
                )
                if proc_ref is not None:
                    proc_ref["proc"] = proc

                rc = proc.wait()

                if rc == 0 and os.path.exists(out_part) and os.path.getsize(out_part) > 0:
                    with contextlib.suppress(FileExistsError):
                        if os.path.exists(out_final):
                            os.remove(out_final)
                    os.replace(out_part, out_final)
                    return True, url, None

            except Exception as e:
                err = str(e)
            finally:
                if proc is not None:
                    with contextlib.suppress(Exception):
                        if proc.poll() is None:
                            proc.terminate()
                    with contextlib.suppress(Exception):
                        proc.wait(timeout=2)

            with contextlib.suppress(Exception):
                if os.path.exists(out_part):
                    os.remove(out_part)

        return False, None, "Không thể tải video từ tất cả nguồn."

    def _download_file_api(self, item: dict):
        link = item.get("link") or ""
        self._open_in_chrome(link)

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
    
    def _go_back_to_course_selection(self):
        """Quay lại màn chọn khóa học."""
        confirm = messagebox.askyesno("Xác nhận", "Bạn có muốn quay lại danh sách khóa học không?")
        if confirm:
            self._set_status("Quay lại màn chọn khóa học", show_note=False)
            self.show_course_selection()
    
    # ========== UTILITIES ==========
    def _start_spinner(self, label_widget: ttk.Label, base_text: str = "Đang xử lý"):
        # quay chấm ... ... ...
        if getattr(label_widget, "_spin_job", None):
            return
        dots = {"i": 0}
        def spin():
            dots["i"] = (dots["i"] + 1) % 4
            label_widget.config(text=f"{base_text}{'.' * dots['i']}")
            label_widget._spin_job = label_widget.after(250, spin)
        spin()

    def _stop_spinner(self, label_widget: ttk.Label):
        job = getattr(label_widget, "_spin_job", None)
        if job:
            try:
                label_widget.after_cancel(job)
            except Exception:
                pass
            label_widget._spin_job = None

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
        Chuẩn hoá dữ liệu chapters về dạng {'chapters': [...]}
        để TreeView luôn đọc được, dù API trả list hay bọc trong key khác.
        """
        try:
            if isinstance(data, dict) and "chapters" in data and isinstance(data["chapters"], list):
                return data
            if isinstance(data, list):
                return {"chapters": data}
            # Một số API trả {'data': {...}} hoặc {'data': [...]}
            if isinstance(data, dict) and "data" in data:
                d = data["data"]
                if isinstance(d, dict) and "chapters" in d:
                    return {"chapters": d["chapters"]}
                if isinstance(d, list):
                    return {"chapters": d}
            # Fallback
            return {"chapters": []}
        except Exception as e:
            print("coerce chapters error:", e)
            return {"chapters": []}

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
        user_id = self.temp.get("user_id")
        if not token or not user_id:
            return False
        try:
            # Gọi API nhẹ để kiểm tra token (thay bằng endpoint check nếu bạn có)
            code, courses = self.AppApi.get_user_courses(user_id, token)
            if code == 0:
                self.auth = {"access_token": token, "user_id": user_id}
                self._set_status(f"Đã khôi phục phiên cho {self.temp.get('last_email','') or 'người dùng'}.")
                return True
            # token invalid -> xoá cache
            self._clear_temp_store()
            return False
        except Exception as e:
            print("Auto-resume error:", e)
            return False
    
    def _ensure_ffmpeg(self) -> str:
        """
        Trả về đường dẫn ffmpeg khả dụng cho mọi chế độ:
        - PyInstaller --onefile (dùng sys._MEIPASS)
        - PyInstaller --onedir (cạnh executable)
        - Dev (cạnh file .py)
        - Fallback: ffmpeg trên PATH
        Hỗ trợ Windows/Mac/Linux. Tự set quyền thực thi nếu cần.
        """
        is_win = sys.platform.startswith("win")
        bin_name = "ffmpeg.exe" if is_win else "ffmpeg"

        def _ok(p: str | None) -> str | None:
            return p if p and os.path.isfile(p) else None

        # 1) PyInstaller --onefile: sys._MEIPASS
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = _ok(os.path.join(meipass, "ffmpeg", bin_name)) \
                or _ok(os.path.join(meipass, "ffmpeg", "mac", "ffmpeg"))  # chấp nhận layout cũ
            if cand:
                try:
                    os.chmod(cand, os.stat(cand).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except Exception:
                    pass
                return cand

        # 2) Frozen (onedir) hoặc dev: cạnh executable / file .py
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))

        cand = _ok(os.path.join(base, "ffmpeg", bin_name)) \
            or _ok(os.path.join(base, "ffmpeg", "mac", "ffmpeg")) \
            or _ok(os.path.join(base, "vendor", "mac" if not is_win else "win", bin_name))
        if cand:
            try:
                os.chmod(cand, os.stat(cand).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except Exception:
                pass
            return cand

        # 3) PATH hệ thống
        ff = shutil.which("ffmpeg")
        if ff:
            return ff

        raise RuntimeError("Không tìm thấy ffmpeg.")

    def _select_download_dir(self) -> str:
        """Hỏi thư mục lưu, nhớ lại lựa chọn gần nhất trong self.temp."""
        last_dir = (self.temp or {}).get("last_download_dir", os.path.expanduser("~"))
        folder = fd.askdirectory(title="Chọn thư mục lưu video", initialdir=last_dir or os.path.expanduser("~"))
        if folder:
            # lưu nhớ
            self._save_temp_store({"last_download_dir": folder})
        return folder or ""

    def _sanitize_filename(self, name: str, default="video") -> str:
        name = (name or default).strip()
        # loại ký tự cấm trong tên file
        name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name or default

if __name__ == "__main__":
    root = tk.Tk()
    app = QandaDownloaderApp(root)
    root.mainloop()