"""Ghate Product Studio — always-visible folder controls, responsive, smooth UI."""

from __future__ import annotations

import math
import os
import threading
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from dotenv import load_dotenv

from .batch import (
    BatchConfig,
    BatchState,
    build_timing_stats,
    force_stop,
    list_images,
    run_batch,
)
from .free_pipeline import FREE_PIPELINE_VERSION
from .prompt import FAL_MODEL_ID, PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

PURPLE = "#7c3aed"
PURPLE_HOVER = "#6d28d9"
PURPLE_SOFT = "#2e1065"
PURPLE_GLOW = "#a78bfa"
GREEN = "#22c55e"

THEMES = {
    "dark": {
        "bg": "#000000",
        "sidebar": "#121212",
        "panel": "#1a1a1a",
        "panel_alt": "#222222",
        "border": "#2a2a2a",
        "text": "#ffffff",
        "muted": "#9ca3af",
    },
    "light": {
        "bg": "#f4f4f5",
        "sidebar": "#ffffff",
        "panel": "#ffffff",
        "panel_alt": "#f4f4f5",
        "border": "#e4e4e7",
        "text": "#18181b",
        "muted": "#71717a",
    },
}

LOG_MAX_LINES = 800
SIDEBAR_W = 340


class GhateApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ghate Product Studio")
        self._fit_initial_geometry()
        self.minsize(720, 560)

        self._theme = "dark"
        self._engine = "free"
        self._worker: threading.Thread | None = None
        self._state = BatchState()
        self._anim_phase = 0.0
        self._animating = False
        self._log_queue: deque[str] = deque()
        self._log_flush_scheduled = False
        self._progress_target = 0.0
        self._progress_display = 0.0
        self._count_token = 0
        self._last_ui_progress = 0.0
        self._pending_progress_msg = ""

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Pack layout: topbar + (sidebar | main) — never hides folder controls
        self.topbar = ctk.CTkFrame(self, height=56, corner_radius=0)
        self.topbar.pack(side="top", fill="x")
        self.topbar.pack_propagate(False)

        self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.body.pack(side="top", fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(self.body, width=SIDEBAR_W, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.main = ctk.CTkFrame(self.body, corner_radius=0)
        self.main.pack(side="left", fill="both", expand=True)

        self._build_topbar()
        self._build_sidebar()
        self._build_workspace()
        self._apply_theme()

        self._refresh_file_count()
        self._enqueue_log(self._ready_message())
        self._enqueue_log(
            "How to use: 1) Browse Input folder (raw photos)  "
            "2) Browse Output folder (edited JPGs)  3) Start Batch\n"
        )
        self._tick_animation()

    def _fit_initial_geometry(self) -> None:
        self.update_idletasks()
        sw = max(self.winfo_screenwidth(), 1024)
        sh = max(self.winfo_screenheight(), 700)
        w = min(1200, max(900, int(sw * 0.85)))
        h = min(780, max(600, int(sh * 0.82)))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _t(self) -> dict[str, str]:
        return THEMES[self._theme]

    def _ready_message(self) -> str:
        if self._engine == "free":
            return (
                f"Free Adaptive · {FREE_PIPELINE_VERSION} · $0 "
                "(auto-fallback for difficult white/metallic products)\n"
            )
        return (
            f"Pro tier · {FAL_MODEL_ID} · prompt {PROMPT_VERSION} · needs FAL_KEY\n"
        )

    def _build_topbar(self) -> None:
        brand = ctk.CTkFrame(self.topbar, fg_color="transparent")
        brand.pack(side="left", padx=14, pady=10)
        self.logo = ctk.CTkLabel(
            brand,
            text="G",
            width=32,
            height=32,
            corner_radius=8,
            fg_color=PURPLE,
            text_color="#ffffff",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.logo.pack(side="left")
        self.brand_label = ctk.CTkLabel(
            brand,
            text="  Ghate Product Studio",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.brand_label.pack(side="left")

        right = ctk.CTkFrame(self.topbar, fg_color="transparent")
        right.pack(side="right", padx=14)
        self.theme_btn = ctk.CTkButton(
            right,
            text="Light",
            width=68,
            height=30,
            corner_radius=16,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            text_color="#ffffff",
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="left", padx=(0, 8))

        self.status_pill = ctk.CTkFrame(right, corner_radius=20, border_width=1)
        self.status_pill.pack(side="left", padx=(0, 8))
        self.status_dot = ctk.CTkLabel(
            self.status_pill, text="●", text_color=GREEN, width=16, font=ctk.CTkFont(size=10)
        )
        self.status_dot.pack(side="left", padx=(8, 0), pady=5)
        self.key_label = ctk.CTkLabel(
            self.status_pill, text="", font=ctk.CTkFont(size=11)
        )
        self.key_label.pack(side="left", padx=(2, 10), pady=5)

        self.avatar = ctk.CTkLabel(
            right,
            text="G",
            width=30,
            height=30,
            corner_radius=15,
            fg_color=PURPLE,
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.avatar.pack(side="left")

    def _build_sidebar(self) -> None:
        scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", corner_radius=0
        )
        scroll.pack(fill="both", expand=True)
        self.side_scroll = scroll

        head = ctk.CTkFrame(scroll, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(16, 8))
        self.head_label = ctk.CTkLabel(
            head,
            text="SELECT FOLDERS",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.head_label.pack(side="left")
        self.count_label = ctk.CTkLabel(head, text="(0 photos)", font=ctk.CTkFont(size=12))
        self.count_label.pack(side="right")

        # --- INPUT ---
        self._label(scroll, "1. Input folder (raw photos)")
        self.in_card = ctk.CTkFrame(scroll, corner_radius=12, border_width=1)
        self.in_card.pack(fill="x", padx=16, pady=(0, 12))
        self.in_var = tk.StringVar()
        self.in_var.trace_add("write", lambda *_: self._refresh_file_count())
        self.in_entry = ctk.CTkEntry(
            self.in_card,
            textvariable=self.in_var,
            placeholder_text="Folder with raw product images…",
            height=38,
        )
        self.in_entry.pack(fill="x", padx=10, pady=(10, 6))
        self.in_browse = ctk.CTkButton(
            self.in_card,
            text="Browse input folder…",
            height=40,
            corner_radius=10,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._browse_in,
        )
        self.in_browse.pack(fill="x", padx=10, pady=(0, 10))

        # --- OUTPUT ---
        self._label(scroll, "2. Output folder (edited JPGs)")
        self.out_card = ctk.CTkFrame(scroll, corner_radius=12, border_width=1)
        self.out_card.pack(fill="x", padx=16, pady=(0, 12))
        self.out_var = tk.StringVar()
        self.out_entry = ctk.CTkEntry(
            self.out_card,
            textvariable=self.out_var,
            placeholder_text="Where finished images are saved…",
            height=38,
        )
        self.out_entry.pack(fill="x", padx=10, pady=(10, 6))
        self.out_browse = ctk.CTkButton(
            self.out_card,
            text="Browse output folder…",
            height=40,
            corner_radius=10,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._browse_out,
        )
        self.out_browse.pack(fill="x", padx=10, pady=(0, 10))

        # --- ENGINE ---
        self._label(scroll, "3. Engine")
        self.tier_frame = ctk.CTkFrame(scroll, corner_radius=12, border_width=1)
        self.tier_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.engine_seg = ctk.CTkSegmentedButton(
            self.tier_frame,
            values=["Free", "Pro"],
            command=self._on_engine,
            selected_color=PURPLE,
            selected_hover_color=PURPLE_HOVER,
            unselected_color="#222222",
            unselected_hover_color="#333333",
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
        )
        self.engine_seg.set("Free")
        self.engine_seg.pack(fill="x", padx=10, pady=10)
        self.engine_hint = ctk.CTkLabel(
            self.tier_frame,
            text="Free = local Adaptive rembg ($0) · Pro = fal Kontext",
            font=ctk.CTkFont(size=11),
            wraplength=280,
            justify="left",
        )
        self.engine_hint.pack(anchor="w", padx=12, pady=(0, 10))

        # --- SETTINGS ---
        self._label(scroll, "Settings")
        self.settings = ctk.CTkFrame(scroll, corner_radius=12, border_width=1)
        self.settings.pack(fill="x", padx=16, pady=(0, 12))
        row = ctk.CTkFrame(self.settings, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(12, 6))
        self.conc_label = ctk.CTkLabel(row, text="Workers", font=ctk.CTkFont(size=12))
        self.conc_label.pack(side="left")
        self.conc_var = tk.StringVar(value="1")
        self.conc_entry = ctk.CTkEntry(row, textvariable=self.conc_var, width=56, height=32)
        self.conc_entry.pack(side="right")
        self.workers_hint = ctk.CTkLabel(
            self.settings,
            text="Free: always 1 GPU worker · Pro: API concurrency (max 4)",
            font=ctk.CTkFont(size=10),
            wraplength=280,
            justify="left",
        )
        self.workers_hint.pack(anchor="w", padx=12, pady=(0, 4))
        self.shadow_var = tk.BooleanVar(value=False)
        self.shadow_chk = ctk.CTkCheckBox(
            self.settings,
            text="Optional contact shadow (off by default)",
            variable=self.shadow_var,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
        )
        self.shadow_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self.mode_label = ctk.CTkLabel(
            self.settings, text="Free mode", font=ctk.CTkFont(size=12), anchor="w"
        )
        self.mode_label.pack(fill="x", padx=12, pady=(4, 2))
        self.mode_seg = ctk.CTkSegmentedButton(
            self.settings,
            values=["Adaptive", "Fast", "Quality"],
            selected_color=PURPLE,
            selected_hover_color=PURPLE_HOVER,
            unselected_color="#222222",
            unselected_hover_color="#333333",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
        )
        self.mode_seg.set("Adaptive")
        self.mode_seg.pack(fill="x", padx=12, pady=(0, 4))
        self.mode_hint = ctk.CTkLabel(
            self.settings,
            text="Adaptive = fast + auto rescue for white/metallic (recommended)",
            font=ctk.CTkFont(size=10),
            wraplength=280,
            justify="left",
        )
        self.mode_hint.pack(anchor="w", padx=12, pady=(0, 12))
        # legacy alias kept for older call sites
        self.quality_var = tk.BooleanVar(value=False)
        self.quality_chk = self.mode_seg  # type: ignore[assignment]

        prog = ctk.CTkFrame(scroll, fg_color="transparent")
        prog.pack(fill="x", padx=16, pady=(4, 4))
        top = ctk.CTkFrame(prog, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Progress", font=ctk.CTkFont(size=11)).pack(side="left")
        self.pct_label = ctk.CTkLabel(top, text="0%", font=ctk.CTkFont(size=12))
        self.pct_label.pack(side="right")
        self.progress = ctk.CTkProgressBar(
            prog, height=10, corner_radius=5, progress_color=PURPLE
        )
        self.progress.pack(fill="x", pady=(4, 0))
        self.progress.set(0)

        self.timing_card = ctk.CTkFrame(scroll, corner_radius=12, border_width=1)
        self.timing_card.pack(fill="x", padx=16, pady=(8, 4))
        self.timing_title = ctk.CTkLabel(
            self.timing_card,
            text="SPEED & TIME",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        )
        self.timing_title.pack(fill="x", padx=12, pady=(10, 2))
        self.count_progress_label = ctk.CTkLabel(
            self.timing_card,
            text="0 / 0 images",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self.count_progress_label.pack(fill="x", padx=12, pady=(0, 2))
        self.bucket_label = ctk.CTkLabel(
            self.timing_card,
            text="Approved: 0  ·  Review: 0  ·  Failed: 0",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.bucket_label.pack(fill="x", padx=12, pady=(0, 2))
        self.speed_label = ctk.CTkLabel(
            self.timing_card,
            text="Speed: —  ·  — s/img",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.speed_label.pack(fill="x", padx=12, pady=(0, 2))
        self.elapsed_label = ctk.CTkLabel(
            self.timing_card,
            text="Elapsed: 0:00",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.elapsed_label.pack(fill="x", padx=12, pady=(0, 2))
        self.eta_label = ctk.CTkLabel(
            self.timing_card,
            text="Remaining: --:--",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.eta_label.pack(fill="x", padx=12, pady=(0, 10))

        self.start_btn = ctk.CTkButton(
            scroll,
            text="✦  Start Batch",
            height=50,
            corner_radius=12,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start,
        )
        self.start_btn.pack(fill="x", padx=16, pady=(12, 8))
        self.stop_btn = ctk.CTkButton(
            scroll,
            text="Stop",
            height=40,
            corner_radius=12,
            state="disabled",
            command=self._stop,
        )
        self.stop_btn.pack(fill="x", padx=16, pady=(0, 8))
        self.review_btn = ctk.CTkButton(
            scroll,
            text="Open Review Folder",
            height=36,
            corner_radius=12,
            fg_color="#333333",
            hover_color="#444444",
            command=self._open_review_folder,
        )
        self.review_btn.pack(fill="x", padx=16, pady=(0, 6))
        self.review_orig_btn = ctk.CTkButton(
            scroll,
            text="Open Review Originals",
            height=36,
            corner_radius=12,
            fg_color="#333333",
            hover_color="#444444",
            command=self._open_review_originals,
        )
        self.review_orig_btn.pack(fill="x", padx=16, pady=(0, 20))

    def _label(self, parent: ctk.CTkFrame, text: str) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        )
        lbl.pack(fill="x", padx=16, pady=(4, 4))
        return lbl

    def _build_workspace(self) -> None:
        self.canvas = ctk.CTkFrame(self.main, corner_radius=16, border_width=1)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=16)

        self.empty = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.empty.pack(fill="x", padx=28, pady=(28, 8))
        self.empty_icon = ctk.CTkLabel(self.empty, text="▣", font=ctk.CTkFont(size=32))
        self.empty_icon.pack()
        self.empty_title = ctk.CTkLabel(
            self.empty,
            text="Create Digikala-ready product shots",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.empty_title.pack(pady=(8, 4))
        self.empty_sub = ctk.CTkLabel(
            self.empty,
            text=(
                "Use the LEFT panel:\n"
                "① Browse input folder  →  ② Browse output folder  →  ③ Start Batch"
            ),
            font=ctk.CTkFont(size=13),
            justify="center",
        )
        self.empty_sub.pack()

        self.log_frame = ctk.CTkFrame(self.canvas, corner_radius=12)
        self.log_frame.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.log_title = ctk.CTkLabel(
            self.log_frame,
            text="Activity log",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        )
        self.log_title.pack(fill="x", padx=12, pady=(8, 0))
        self.log = ctk.CTkTextbox(
            self.log_frame,
            wrap="word",
            border_width=0,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log.pack(fill="both", expand=True, padx=6, pady=(2, 6))

    def _apply_theme(self) -> None:
        t = self._t()
        ctk.set_appearance_mode("dark" if self._theme == "dark" else "light")
        self.configure(fg_color=t["bg"])
        self.topbar.configure(fg_color=t["bg"])
        self.body.configure(fg_color=t["bg"])
        self.sidebar.configure(fg_color=t["sidebar"])
        self.side_scroll.configure(fg_color=t["sidebar"])
        self.main.configure(fg_color=t["bg"])
        self.brand_label.configure(text_color=t["text"])
        self.head_label.configure(text_color=t["text"])
        self.count_label.configure(text_color=t["muted"])
        self.key_label.configure(text_color=t["muted"])
        self.status_pill.configure(fg_color=t["panel"], border_color=t["border"])
        self.theme_btn.configure(text="Light" if self._theme == "dark" else "Dark")

        for card in (
            self.in_card,
            self.out_card,
            self.tier_frame,
            self.settings,
            self.canvas,
            self.timing_card,
        ):
            card.configure(fg_color=t["panel"], border_color=t["border"])
        self.log_frame.configure(fg_color=t["panel_alt"])
        self.log.configure(fg_color=t["panel_alt"], text_color=t["text"])
        self.log_title.configure(text_color=t["muted"])
        self.empty_icon.configure(text_color=t["muted"])
        self.empty_title.configure(text_color=t["text"])
        self.empty_sub.configure(text_color=t["muted"])
        self.engine_hint.configure(text_color=t["muted"])
        if hasattr(self, "workers_hint"):
            self.workers_hint.configure(text_color=t["muted"])
        if hasattr(self, "mode_hint"):
            self.mode_hint.configure(text_color=t["muted"])
        if hasattr(self, "mode_label"):
            self.mode_label.configure(text_color=t["text"])
        self.pct_label.configure(text_color=t["muted"])
        self.conc_label.configure(text_color=t["muted"])
        self.progress.configure(fg_color=t["panel_alt"])
        self.timing_title.configure(text_color=t["muted"])
        self.count_progress_label.configure(text_color=t["text"])
        if hasattr(self, "bucket_label"):
            self.bucket_label.configure(text_color=t["muted"])
        self.speed_label.configure(text_color=t["muted"])
        self.elapsed_label.configure(text_color=t["muted"])
        self.eta_label.configure(text_color=t["muted"])

        for entry in (self.in_entry, self.out_entry, self.conc_entry):
            entry.configure(
                fg_color=t["panel_alt"], border_color=t["border"], text_color=t["text"]
            )
        self.stop_btn.configure(
            fg_color=t["panel_alt"],
            hover_color=t["border"],
            text_color=t["text"],
            border_width=1,
            border_color=t["border"],
        )
        self.engine_seg.configure(
            unselected_color=t["panel_alt"],
            unselected_hover_color=t["border"],
            text_color="#ffffff" if self._theme == "dark" else t["text"],
        )
        self._update_status_pill()

    def _toggle_theme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        self._apply_theme()
        self._pulse_logo()

    def _pulse_logo(self) -> None:
        self.logo.configure(fg_color=PURPLE_HOVER)
        self.after(90, lambda: self.logo.configure(fg_color=PURPLE_GLOW))
        self.after(180, lambda: self.logo.configure(fg_color=PURPLE))

    def _tick_animation(self) -> None:
        self._anim_phase += 0.14
        diff = self._progress_target - self._progress_display
        if abs(diff) > 0.0008:
            self._progress_display += diff * 0.28
            self.progress.set(max(0.0, min(1.0, self._progress_display)))
            self.pct_label.configure(text=f"{self._progress_display * 100:.0f}%")

        # While batching: light animation only (don't fight CPU with the worker)
        interval = 100 if self._animating else 33
        if self._animating:
            wave = 0.5 + 0.5 * math.sin(self._anim_phase)
            self.progress.configure(
                progress_color=PURPLE if wave > 0.55 else PURPLE_GLOW
            )
            # Live elapsed clock between image completions
            if self._state.started_at:
                try:
                    self._update_timing_ui(build_timing_stats(self._state))
                except Exception:
                    pass
        else:
            self.progress.configure(progress_color=PURPLE)
            self.logo.configure(fg_color=PURPLE)
            wave = 0.5 + 0.5 * math.sin(self._anim_phase)
            self.empty_icon.configure(
                text_color=PURPLE_GLOW if wave > 0.85 else self._t()["muted"]
            )
        self.after(interval, self._tick_animation)

    def _on_engine(self, value: str) -> None:
        self._engine = "free" if value == "Free" else "pro"
        if self._engine == "free":
            self.engine_hint.configure(
                text="Free = local rembg ($0) · Adaptive recommended"
            )
            self.conc_var.set("1")
            self.shadow_chk.configure(state="normal")
            self.mode_seg.configure(state="normal")
        else:
            self.engine_hint.configure(text="Pro needs FAL_KEY in .env · ~$0.04 / image")
            self.conc_var.set("2")
            self.shadow_chk.configure(state="disabled")
            self.mode_seg.configure(state="disabled")
        self._update_status_pill()
        self._enqueue_log(self._ready_message())
        self._pulse_logo()

    def _update_status_pill(self) -> None:
        if self._engine == "free":
            self.key_label.configure(text="Free · local")
            self.status_dot.configure(text_color=GREEN)
        elif os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY"):
            self.key_label.configure(text="Pro · ready")
            self.status_dot.configure(text_color=GREEN)
        else:
            self.key_label.configure(text="Pro · no key")
            self.status_dot.configure(text_color="#f59e0b")

    def _enqueue_log(self, msg: str) -> None:
        self._log_queue.append(msg.rstrip())
        if not self._log_flush_scheduled:
            self._log_flush_scheduled = True
            self.after(40, self._flush_logs)

    def _flush_logs(self) -> None:
        self._log_flush_scheduled = False
        if not self._log_queue:
            return
        chunk: list[str] = []
        while self._log_queue and len(chunk) < 40:
            chunk.append(self._log_queue.popleft())
        self.log.insert("end", "\n".join(chunk) + "\n")
        try:
            end_line = int(float(self.log.index("end-1c").split(".")[0]))
            if end_line > LOG_MAX_LINES:
                self.log.delete("1.0", f"{end_line - LOG_MAX_LINES}.0")
        except Exception:
            pass
        self.log.see("end")
        if self._log_queue:
            self._log_flush_scheduled = True
            self.after(40, self._flush_logs)

    def _refresh_file_count(self) -> None:
        path_str = self.in_var.get().strip()
        self._count_token += 1
        token = self._count_token
        if not path_str:
            self.count_label.configure(text="(0 photos)")
            return
        path = Path(path_str)

        def work() -> None:
            n = len(list_images(path)) if path.is_dir() else 0
            if token == self._count_token:
                self.after(0, lambda: self.count_label.configure(text=f"({n} photos)"))

        threading.Thread(target=work, daemon=True).start()

    def _browse_in(self) -> None:
        path = filedialog.askdirectory(title="Select INPUT folder (raw photos)")
        if path:
            self.in_var.set(path)
            self._enqueue_log(f"Input folder: {path}")
            self._pulse_logo()

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Select OUTPUT folder (edited images)")
        if path:
            self.out_var.set(path)
            self._enqueue_log(f"Output folder: {path}")
            self._pulse_logo()

    def _set_progress(self, pct: float, msg: str, stats: dict | None = None) -> None:
        self._progress_target = max(0.0, min(1.0, pct / 100.0))
        self._pending_progress_msg = msg
        if stats:
            self._update_timing_ui(stats)
        # Throttle log spam: only every ~2% or at 100%
        if pct - self._last_ui_progress >= 2.0 or pct >= 99.9:
            self._last_ui_progress = pct
            self._enqueue_log(msg)

    def _update_timing_ui(self, stats: dict) -> None:
        processed = stats.get("processed", 0)
        total = stats.get("total", 0)
        left = stats.get("left", max(0, total - processed))
        approved = stats.get("approved", stats.get("succeeded", 0))
        reviewed = stats.get("reviewed", 0)
        failed = stats.get("failed", 0)
        self.count_progress_label.configure(
            text=f"{processed} / {total} images  ({left} left)"
        )
        self.bucket_label.configure(
            text=f"Approved: {approved}  ·  Review: {reviewed}  ·  Failed: {failed}"
        )
        sec = stats.get("sec_per_img", 0.0) or 0.0
        ipm = stats.get("imgs_per_min", 0.0) or 0.0
        if ipm > 0 or sec > 0:
            self.speed_label.configure(
                text=f"Speed: {ipm:.1f} img/min  ·  {sec:.1f} s/img"
            )
        else:
            self.speed_label.configure(text="Speed: measuring…")
        self.elapsed_label.configure(text=f"Elapsed: {stats.get('elapsed', '0:00')}")
        eta = stats.get("eta", "--:--")
        if processed <= 0:
            self.eta_label.configure(text="Remaining: calculating…")
        elif left <= 0:
            self.eta_label.configure(text="Remaining: 0:00 (done)")
        else:
            self.eta_label.configure(text=f"Remaining: {eta}")

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if self._engine == "pro" and not (
            os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
        ):
            messagebox.showerror(
                "Missing API key",
                "Pro tier needs FAL_KEY in .env. Or switch to Free tier.",
            )
            return
        in_dir = Path(self.in_var.get().strip())
        out_dir = Path(self.out_var.get().strip())
        if not in_dir.is_dir():
            messagebox.showerror(
                "Input folder",
                "Click “Browse input folder…” on the left and choose your raw photos folder.",
            )
            return
        if not self.out_var.get().strip():
            messagebox.showerror(
                "Output folder",
                "Click “Browse output folder…” on the left and choose where to save edited images.",
            )
            return
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            concurrency = max(1, int(self.conc_var.get().strip() or "1"))
        except ValueError:
            concurrency = 1
        # Free path never runs multiple AI model copies (4GB VRAM).
        if self._engine == "free":
            concurrency = 1

        self._state = BatchState()
        self._animating = True
        self._progress_target = 0.0
        self._progress_display = 0.0
        self._last_ui_progress = 0.0
        self.start_btn.configure(state="disabled", fg_color=PURPLE_SOFT)
        self.stop_btn.configure(state="normal")
        self.engine_seg.configure(state="disabled")
        self.conc_entry.configure(state="disabled")
        self.mode_seg.configure(state="disabled")
        self.shadow_chk.configure(state="disabled")
        self.key_label.configure(text="Running…")
        self.count_progress_label.configure(text="0 / … images")
        self.speed_label.configure(text="Speed: measuring…")
        self.elapsed_label.configure(text="Elapsed: 0:00")
        self.eta_label.configure(text="Remaining: calculating…")
        self._pulse_logo()

        mode_ui = (self.mode_seg.get() or "Adaptive").strip().lower()
        free_mode = {"adaptive": "adaptive", "fast": "fast", "quality": "quality"}.get(
            mode_ui, "adaptive"
        )
        self._enqueue_log(
            f"Processing in background — Free mode: {free_mode}. "
            "Adaptive auto-retries difficult white/metallic products.\n"
        )

        cfg = BatchConfig(
            input_dir=in_dir,
            output_dir=out_dir,
            concurrency=concurrency,
            engine=self._engine,  # type: ignore[arg-type]
            with_shadow=bool(self.shadow_var.get()),
            free_mode=free_mode,  # type: ignore[arg-type]
            free_quality=(free_mode == "quality"),
            free_use_process=None,  # auto: GPU in-process, CPU child process
        )

        def worker() -> None:
            def log(msg: str) -> None:
                self.after(0, lambda m=msg: self._enqueue_log(m))

            def progress(pct: float, msg: str, stats: dict | None = None) -> None:
                self.after(
                    0,
                    lambda p=pct, m=msg, s=stats or {}: self._set_progress(p, m, s),
                )

            try:
                run_batch(cfg, self._state, log=log, on_progress=progress)
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda e=exc: self._enqueue_log(f"FATAL: {e}"))
            finally:
                self.after(0, self._on_done)

        self._worker = threading.Thread(target=worker, daemon=True, name="ghate-batch")
        self._worker.start()

    def _open_review_folder(self) -> None:
        out = self.out_var.get().strip()
        if not out:
            messagebox.showinfo(
                "Review folder",
                "Select an output folder first. Review layout:\n"
                "<output>\\Review\\Edited\n"
                "<output>\\Review\\Original\n"
                "<output>\\Review\\review_manifest.csv",
            )
            return
        from .review_io import ensure_output_layout, review_edited_dir

        ensure_output_layout(Path(out))
        path = review_edited_dir(Path(out))
        try:
            os.startfile(str(path))  # noqa: S606 — Windows Explorer
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Review folder", f"Could not open:\n{path}\n\n{exc}")

    def _open_review_originals(self) -> None:
        out = self.out_var.get().strip()
        if not out:
            messagebox.showinfo(
                "Review originals",
                "Select an output folder first.\n"
                "Paired originals are copied only for Review items:\n"
                "<output>\\Review\\Original\\{same_id}.HEIC/JPG",
            )
            return
        from .review_io import ensure_output_layout, review_original_dir

        ensure_output_layout(Path(out))
        path = review_original_dir(Path(out))
        try:
            os.startfile(str(path))  # noqa: S606
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Review originals", f"Could not open:\n{path}\n\n{exc}")

    def _stop(self) -> None:
        force_stop(self._state)
        self._enqueue_log("Stop: killing worker now (current image may abort)…")
        self.key_label.configure(text="Stopping…")

    def _on_done(self) -> None:
        self._animating = False
        self.start_btn.configure(state="normal", fg_color=PURPLE)
        self.stop_btn.configure(state="disabled")
        self.engine_seg.configure(state="normal")
        self.conc_entry.configure(state="normal")
        self.mode_seg.configure(state="normal" if self._engine == "free" else "disabled")
        self.shadow_chk.configure(state="normal")
        self._update_status_pill()
        self._enqueue_log("Idle.")
        self._pulse_logo()


def main() -> None:
    app = GhateApp()
    app.mainloop()


if __name__ == "__main__":
    main()
