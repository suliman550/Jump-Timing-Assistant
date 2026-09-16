from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from tkinter import Tk, messagebox
import win32com.client


def main() -> None:
    install_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JumpTimingAssistant"
    payload = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "payload" / "JumpTimingAssistant.exe"
    target = install_dir / "JumpTimingAssistant.exe"
    desktop = Path.home() / "Desktop"
    desktop_exe = desktop / "Jump Timing Assistant.exe"
    shortcut_path = desktop / "Jump Timing Assistant.lnk"
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payload, target)
        shutil.copy2(target, desktop_exe)
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = str(desktop_exe)
        shortcut.WorkingDirectory = str(desktop)
        shortcut.IconLocation = f"{desktop_exe},0"
        shortcut.Save()
        os.startfile(str(target))
    except Exception as exc:
        root = Tk()
        root.withdraw()
        messagebox.showerror("Jump Timing Assistant Setup", f"Installation failed:\n{exc}", parent=root)
        root.destroy()
        raise
    else:
        root = Tk()
        root.withdraw()
        messagebox.showinfo("Jump Timing Assistant Setup", "Installed to your desktop.", parent=root)
        root.destroy()


if __name__ == "__main__":
    main()
