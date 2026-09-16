#!/usr/bin/env python3
"""Jump timing assistant for a Windows overlay.

This project is intentionally conservative: it never injects code into the game,
never modifies memory, and never bypasses anti-cheat protections. The tool is a
standalone overlay that helps the player judge the right jump timing using a
configurable manual timer and a calibration loop.

Automatic in-game detection of a shrinking/size event is not implemented because
that would require unsafe or invasive integration with the game process. The
application therefore provides a reliable manual activation mode as the primary,
fully-safe fallback.
"""

from __future__ import annotations

import json
import ctypes
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
import tkinter as tk
from tkinter import BOTH, Canvas, Frame, Label, StringVar, Tk, Toplevel, colorchooser
from tkinter import ttk

import keyboard
import pystray
from PIL import Image, ImageDraw


CONFIG_PATH = Path(__file__).with_name("settings.json")
CALIBRATION_PATH = Path(__file__).with_name("calibration_data.json")

COLOR_DEFAULTS = {
    "background_color": "#111827",
    "text_color": "#f8fafc",
    "secondary_color": "#94a3b8",
    "accent_color": "#7dd3fc",
}


def default_settings() -> dict:
    return {
        "base_jump_ms": 4500,
        "jump_start_ms": 3500,
        "jump_end_ms": 4700,
        "perfect_window_ms": 180,
        "timing_offset_ms": 0,
        "manual_offset_ms": 0,
        "reaction_compensation_ms": 0,
        "toggle_hotkey": "f7",
        "activation_hotkey": "f8",
        "reset_hotkey": "f9",
        "calibration_hotkey": "f10",
        "shrink_key": "m",
        "jump_key": "space",
        "overlay_visible": True,
        "window_x": 120,
        "window_y": 120,
        "window_width": 360,
        "window_height": 220,
        **COLOR_DEFAULTS,
    }


def load_settings() -> dict:
    if not CONFIG_PATH.exists():
        settings = default_settings()
        save_settings(settings)
        return settings

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            config = json.load(fh)
    except json.JSONDecodeError:
        config = {}

    merged = default_settings()
    merged.update(config)
    if "timing_offset_ms" not in config and "manual_offset_ms" in config:
        merged["timing_offset_ms"] = config["manual_offset_ms"]
    save_settings(merged)
    return merged


def save_settings(settings: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


@dataclass
class AttemptRecord:
    start_event_ms: float
    jump_press_ms: float
    delta_ms: float
    status: str
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


def load_calibration_records() -> list:
    if not CALIBRATION_PATH.exists():
        return []
    try:
        with CALIBRATION_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_calibration_records(records: list) -> None:
    with CALIBRATION_PATH.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)


def get_target_delay_ms(base_jump_ms: float, manual_offset_ms: float = 0, reaction_comp_ms: float = 0) -> int:
    return int(round(base_jump_ms + manual_offset_ms + reaction_comp_ms))


def get_configured_target_ms(settings: dict) -> int:
    offset = settings.get("timing_offset_ms", settings.get("manual_offset_ms", 0))
    return get_target_delay_ms(settings.get("base_jump_ms", 4500), offset, settings.get("reaction_compensation_ms", 0))


def get_phase_for_elapsed(elapsed_ms: float, target_ms: float, window_ms: float) -> str:
    if elapsed_ms < target_ms - window_ms:
        return "EARLY"
    if elapsed_ms <= target_ms + window_ms:
        return "PERFECT"
    return "LATE"


def get_display_status(elapsed_ms: float, jump_start_ms: float = 3500, jump_end_ms: float = 4700) -> str:
    if elapsed_ms < jump_start_ms:
        return "WAIT"
    if elapsed_ms <= jump_end_ms:
        return "JUMP"
    return "TOO LATE"


class TimingController:
    def __init__(self, settings: dict):
        self.settings = settings
        self.mode = "MANUAL"
        self.running = False
        self.started_at: float | None = None
        self.target_ms = get_configured_target_ms(settings)
        self.window_ms = float(settings.get("perfect_window_ms", 180))
        self.start_event_label = "waiting for safe event"
        self.calibration_mode = False
        self.jump_pressed = False
        self.attempt_records: list = load_calibration_records()

    def apply_settings(self, settings: dict):
        self.settings = settings
        self.target_ms = get_configured_target_ms(settings)
        self.window_ms = float(settings.get("perfect_window_ms", 180))

    def start_manual(self):
        self.mode = "MANUAL"
        self.running = True
        self.started_at = time.perf_counter()
        self.jump_pressed = False
        self.start_event_label = "shrink trigger"

    def reset_timer(self):
        self.running = False
        self.started_at = None
        self.jump_pressed = False
        self.mode = "MANUAL"
        self.start_event_label = "ready"

    def get_elapsed_ms(self) -> float:
        if self.started_at is None:
            return 0.0
        return (time.perf_counter() - self.started_at) * 1000.0

    def current_status(self) -> dict:
        elapsed_ms = self.get_elapsed_ms()
        if not self.running:
            return {
                "mode": self.mode,
                "status": "WAIT",
                "timer_ms": 0.0,
                "phase": "EARLY",
                "target_ms": self.target_ms,
                "window_ms": self.window_ms,
                "start_event": self.start_event_label,
                "jump_key": self.settings.get("jump_key", "space"),
            }

        phase = get_phase_for_elapsed(elapsed_ms, self.target_ms, self.window_ms)

        return {
            "mode": self.mode,
            "status": get_display_status(
                elapsed_ms,
                self.settings.get("jump_start_ms", 3500) + self.settings.get("timing_offset_ms", 0),
                self.settings.get("jump_end_ms", 4700) + self.settings.get("timing_offset_ms", 0),
            ),
            "timer_ms": elapsed_ms,
            "phase": phase,
            "target_ms": self.target_ms,
            "window_ms": self.window_ms,
            "start_event": self.start_event_label,
            "jump_key": self.settings.get("jump_key", "space"),
        }

    def record_attempt(self, jump_press_ms: float) -> dict:
        if self.started_at is None:
            return {}

        self.jump_pressed = True
        elapsed_ms = self.get_elapsed_ms()
        status = get_phase_for_elapsed(elapsed_ms, self.target_ms, self.window_ms)
        record = AttemptRecord(
            start_event_ms=self.started_at,
            jump_press_ms=jump_press_ms,
            delta_ms=jump_press_ms - self.started_at * 1000.0,
            status=status,
        )
        self.attempt_records.append(
            {
                "timestamp": record.timestamp,
                "start_event_ms": record.start_event_ms,
                "jump_press_ms": record.jump_press_ms,
                "delta_ms": record.delta_ms,
                "status": record.status,
            }
        )
        save_calibration_records(self.attempt_records)
        return self.attempt_records[-1]


class CalibrationDialog(Toplevel):
    def __init__(self, master, settings: dict, apply_callback):
        super().__init__(master)
        self.title("Settings / Calibration")
        self.transient(master)
        self.geometry("420x620")
        self.settings = settings
        self.apply_callback = apply_callback

        self.base_var = StringVar(value=str(int(self.settings.get("base_jump_ms", 500))))
        self.window_var = StringVar(value=str(int(self.settings.get("perfect_window_ms", 180))))
        self.offset_var = StringVar(value=str(int(self.settings.get("timing_offset_ms", self.settings.get("manual_offset_ms", 0)))))
        self.reaction_var = StringVar(value=str(int(self.settings.get("reaction_compensation_ms", 0))))
        self.jump_start_var = StringVar(value=str(int(self.settings.get("jump_start_ms", 3500))))
        self.jump_end_var = StringVar(value=str(int(self.settings.get("jump_end_ms", 4700))))
        self.shrink_key_var = StringVar(value=str(self.settings.get("shrink_key", "m")))
        self.jump_key_var = StringVar(value=str(self.settings.get("jump_key", "space")))
        self.reset_hotkey_var = StringVar(value=str(self.settings.get("reset_hotkey", "f9")))
        self.color_vars = {
            key: StringVar(value=str(self.settings.get(key, default)))
            for key, default in COLOR_DEFAULTS.items()
        }

        rows = [
            ("Base jump timing (ms)", self.base_var),
            ("Perfect window (ms)", self.window_var),
            ("Timing offset (ms)", self.offset_var),
            ("Reaction compensation (ms)", self.reaction_var),
            ("Jump starts (ms)", self.jump_start_var),
            ("Jump ends (ms)", self.jump_end_var),
            ("Shrink key", self.shrink_key_var),
            ("Jump key", self.jump_key_var),
            ("Reset hotkey", self.reset_hotkey_var),
        ]
        for label_text, variable in rows:
            frame = Frame(self)
            frame.pack(fill="x", padx=8, pady=4)
            Label(frame, text=label_text, width=22, anchor="w").pack(side="left")
            ttk.Entry(frame, textvariable=variable, width=12).pack(side="right")
        color_labels = {
            "background_color": "Overlay background",
            "text_color": "Main text",
            "secondary_color": "Secondary text",
            "accent_color": "Accent / timer",
        }
        for key, label_text in color_labels.items():
            frame = Frame(self)
            frame.pack(fill="x", padx=8, pady=4)
            Label(frame, text=label_text, width=22, anchor="w").pack(side="left")
            ttk.Button(frame, text="Choose", command=lambda name=key: self.choose_color(name)).pack(side="right")
            ttk.Entry(frame, textvariable=self.color_vars[key], width=12).pack(side="right", padx=(0, 6))
        ttk.Button(self, text="Save", command=self.save_settings).pack(pady=10)

    def choose_color(self, key):
        selected = colorchooser.askcolor(color=self.color_vars[key].get(), parent=self)
        if selected[1]:
            self.color_vars[key].set(selected[1])

    def save_settings(self):
        try:
            self.settings["base_jump_ms"] = int(self.base_var.get())
            self.settings["perfect_window_ms"] = int(self.window_var.get())
            self.settings["timing_offset_ms"] = int(self.offset_var.get())
            self.settings["manual_offset_ms"] = self.settings["timing_offset_ms"]
            self.settings["reaction_compensation_ms"] = int(self.reaction_var.get())
            self.settings["jump_start_ms"] = int(self.jump_start_var.get())
            self.settings["jump_end_ms"] = int(self.jump_end_var.get())
            self.settings["shrink_key"] = self.shrink_key_var.get().strip().lower()
            self.settings["jump_key"] = self.jump_key_var.get().strip().lower()
            self.settings["reset_hotkey"] = self.reset_hotkey_var.get().strip().lower()
            for key, variable in self.color_vars.items():
                color = variable.get().strip()
                if not color.startswith("#") or len(color) != 7:
                    raise ValueError
                int(color[1:], 16)
                self.settings[key] = color
            if self.settings["jump_end_ms"] < self.settings["jump_start_ms"]:
                raise ValueError
            save_settings(self.settings)
            self.apply_callback(self.settings)
            self.destroy()
        except ValueError:
            self.title("Calibration — invalid number")


class OverlayWindow:
    def __init__(self, controller: TimingController):
        self.controller = controller
        self.root = Tk()
        self.root.title("Jump Timing Assistant")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg=COLOR_DEFAULTS["background_color"])

        self.root.geometry(f"{controller.settings.get('window_width', 360)}x{controller.settings.get('window_height', 220)}+{controller.settings.get('window_x', 120)}+{controller.settings.get('window_y', 120)}")
        self.root.bind("<ButtonPress-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.drag)
        self.root.bind("<ButtonPress-3>", self.start_resize)
        self.root.bind("<B3-Motion>", self.resize)

        self.status_var = StringVar(value="WAIT…")
        self.mode_var = StringVar(value="AUTO")
        self.timer_var = StringVar(value="0.000 s")
        self.shrink_var = StringVar(value="SHRINK: M")
        self.jump_var = StringVar(value="JUMP: SPACE")
        self.target_var = StringVar(value="TARGET: 4500 ms")
        self.elapsed_var = StringVar(value="ELAPSED: 0 ms")
        self.open_settings_callback = lambda: None

        self.build_ui()
        self.apply_colors()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_tray_icon()
        self.root.after(0, self.configure_taskbar_window)

    def configure_taskbar_window(self):
        if sys.platform != "win32":
            return
        self.root.update_idletasks()
        hwnd = self.root.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
        border_styles = 0x00CF0000
        ctypes.windll.user32.SetWindowLongW(hwnd, -16, style & ~border_styles)
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        app_window_style = 0x00040000
        tool_window_style = 0x00000080
        ctypes.windll.user32.SetWindowLongW(
            hwnd,
            -20,
            (ex_style & ~tool_window_style) | app_window_style,
        )
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

    def start_tray_icon(self):
        image = Image.new("RGBA", (64, 64), (17, 24, 39, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(125, 211, 252, 255))
        draw.rectangle((18, 29, 46, 35), fill=(17, 24, 39, 255))
        self.tray_icon = pystray.Icon(
            "JumpTimingAssistant",
            image,
            "Jump Timing Assistant",
            menu=pystray.Menu(
                pystray.MenuItem("Show / Hide", self.tray_toggle),
                pystray.MenuItem("Settings", self.tray_settings),
                pystray.MenuItem("Exit", self.tray_exit),
            ),
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def tray_toggle(self, icon, item):
        self.root.after(0, self.toggle_visibility)

    def tray_settings(self, icon, item):
        self.root.after(0, self.open_settings_callback)

    def tray_exit(self, icon, item):
        self.root.after(0, self.on_close)

    def toggle_visibility(self):
        if self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()

    def build_ui(self):
        colors = self.controller.settings
        outer = Frame(self.root, bg=colors["background_color"], padx=12, pady=8)
        outer.pack(fill=BOTH, expand=True)
        notch = Canvas(outer, width=142, height=24, bg=colors["background_color"], highlightthickness=0)
        notch.pack(anchor="center")
        notch.create_rectangle(20, 2, 122, 22, fill="#050608", outline="")
        notch.create_oval(10, 2, 30, 22, fill="#050608", outline="")
        notch.create_oval(112, 2, 132, 22, fill="#050608", outline="")
        notch.create_oval(10, 8, 16, 14, fill=colors["secondary_color"], outline="")
        notch.create_oval(22, 8, 28, 14, fill=colors["background_color"], outline=colors["secondary_color"])
        notch.create_rectangle(44, 9, 98, 13, fill=colors["secondary_color"], outline="")

        Label(outer, textvariable=self.status_var, fg=colors["text_color"], bg=colors["background_color"], font=("Segoe UI", 21, "bold")).pack(anchor="center", pady=(2, 0))
        Label(outer, textvariable=self.timer_var, fg=colors["accent_color"], bg=colors["background_color"], font=("Segoe UI", 12, "bold")).pack(anchor="center")
        Label(outer, textvariable=self.shrink_var, fg=colors["secondary_color"], bg=colors["background_color"], font=("Segoe UI", 8)).pack(anchor="center")
        self.reset_button = ttk.Button(outer, text="RESET", command=self.reset_timer)

    def apply_colors(self):
        colors = {**COLOR_DEFAULTS, **self.controller.settings}
        self.root.configure(bg=colors["background_color"])
        for child in self.root.winfo_children():
            child.destroy()
        self.build_ui()

    def start_drag(self, event):
        self.drag_start = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def drag(self, event):
        if self.drag_start is None:
            return
        dx = event.x_root - self.drag_start[0]
        dy = event.y_root - self.drag_start[1]
        self.root.geometry(f"+{self.drag_start[2] + dx}+{self.drag_start[3] + dy}")

    def start_resize(self, event):
        self.resize_start = (event.x_root, event.y_root)
        self.resize_origin = (self.root.winfo_width(), self.root.winfo_height())

    def resize(self, event):
        if self.resize_start is None:
            return
        dx = event.x_root - self.resize_start[0]
        dy = event.y_root - self.resize_start[1]
        width = max(280, self.resize_origin[0] + dx)
        height = max(180, self.resize_origin[1] + dy)
        self.root.geometry(f"{int(width)}x{int(height)}")

    def update(self):
        info = self.controller.current_status()
        self.mode_var.set(f"MODE: {info['mode']}")
        self.status_var.set(info["status"])
        self.timer_var.set(f"TIMER: {info['timer_ms'] / 1000.0:.3f} s")
        self.elapsed_var.set(f"ELAPSED: {int(info['timer_ms'])} ms")
        self.shrink_var.set(f"SHRINK: {self.controller.settings.get('shrink_key', 'm').upper()}")
        self.target_var.set(f"TARGET: {info['target_ms']} ms")
        self.jump_var.set(f"JUMP: {info['jump_key'].upper()}")
        if self.controller.jump_pressed:
            if not self.reset_button.winfo_ismapped():
                self.reset_button.pack(pady=(3, 0))
        elif self.reset_button.winfo_ismapped():
            self.reset_button.pack_forget()
        self.root.after(20, self.update)

    def reset_timer(self):
        self.controller.reset_timer()

    def on_close(self):
        if hasattr(self, "tray_icon"):
            self.tray_icon.stop()
        self.root.destroy()


def prompt_calibration(settings: dict, apply_callback):
    root = Tk()
    root.withdraw()
    CalibrationDialog(root, settings, apply_callback)
    root.mainloop()


def register_keybinds(controller: TimingController, overlay: OverlayWindow):
    if not hasattr(overlay, "hotkey_handles"):
        overlay.hotkey_handles = []
    for handle in overlay.hotkey_handles:
        keyboard.remove_hotkey(handle)
    overlay.hotkey_handles.clear()

    def toggle_overlay():
        if overlay.root.winfo_viewable():
            overlay.root.withdraw()
        else:
            overlay.root.deiconify()

    def start_manual():
        controller.start_manual()

    def reset_timer():
        controller.reset_timer()

    def open_calibration():
        def apply_settings(settings):
            controller.apply_settings(settings)
            overlay.apply_colors()
            register_keybinds(controller, overlay)

        new_dialog = CalibrationDialog(overlay.root, controller.settings, apply_settings)
        new_dialog.focus_set()

    overlay.open_settings_callback = open_calibration

    def record_jump():
        controller.record_attempt(time.perf_counter() * 1000.0)

    overlay.hotkey_handles = [
        keyboard.add_hotkey(controller.settings.get("toggle_hotkey", "f7"), toggle_overlay),
        keyboard.add_hotkey(controller.settings.get("shrink_key", "m"), start_manual),
        keyboard.add_hotkey(controller.settings.get("activation_hotkey", "f8"), start_manual),
        keyboard.add_hotkey(controller.settings.get("reset_hotkey", "f9"), reset_timer),
        keyboard.add_hotkey(controller.settings.get("calibration_hotkey", "f10"), open_calibration),
        keyboard.add_hotkey("home", open_calibration),
        keyboard.add_hotkey("end", open_calibration),
        keyboard.add_hotkey(controller.settings.get("jump_key", "space"), record_jump),
    ]


def main():
    settings = load_settings()
    controller = TimingController(settings)
    overlay = OverlayWindow(controller)
    register_keybinds(controller, overlay)
    overlay.root.after(0, overlay.update)
    overlay.root.deiconify()
    overlay.root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - runtime safety for a GUI app.
        print(f"Jump Timing Assistant failed to start: {exc}")
        raise
