"""System-level command execution: toggles, process management, macros."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser

from PyQt6.QtCore import QTimer

from src.common.config import GHOST_TYPIST_DB


def execute_system_toggle(nexus, cmd: str) -> None:
    """Execute Windows system-level toggles and power commands.

    *nexus* is the NexusSearch instance (used for status label + theme sync).
    """
    try:
        if cmd == "toggle_dark_mode":
            import winreg

            path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                path,
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            new_state = 0 if value == 1 else 1
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, new_state)
            winreg.SetValueEx(
                key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, new_state
            )
            winreg.CloseKey(key)
            state_name = "Dark" if new_state == 0 else "Light"
            nexus.status_lbl.setText(f"🌓 System Theme set to {state_name}")
            nexus.is_light_mode = new_state == 1
            nexus.save_settings()
            nexus.apply_theme()

        elif cmd == "toggle_hidden_files":
            import winreg

            path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                path,
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            value, _ = winreg.QueryValueEx(key, "Hidden")
            new_state = 1 if value == 2 else 2
            winreg.SetValueEx(key, "Hidden", 0, winreg.REG_DWORD, new_state)
            winreg.CloseKey(key)
            subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
            subprocess.Popen(["explorer.exe"])
            state_name = "VISIBLE" if new_state == 1 else "HIDDEN"
            nexus.status_lbl.setText(f"👁️ Hidden Files: {state_name}")

        elif cmd == "toggle_desktop_icons":
            import winreg

            path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                path,
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            value, _ = winreg.QueryValueEx(key, "HideIcons")
            new_state = 1 if value == 0 else 0
            winreg.SetValueEx(key, "HideIcons", 0, winreg.REG_DWORD, new_state)
            winreg.CloseKey(key)
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    '(New-Object -ComObject Shell.Application).Namespace(0).Self.InvokeVerb("Refresh")',
                ],
                shell=True,
            )
            state_name = "HIDDEN" if new_state == 1 else "VISIBLE"
            nexus.status_lbl.setText(f"🔳 Desktop Icons: {state_name}")

        elif cmd == "toggle_mute":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "(new-object -com wscript.shell).SendKeys([char]173)",
                ],
                shell=True,
            )
            nexus.status_lbl.setText("🔇 Master Audio Toggled")

        elif cmd == "flush_dns":
            subprocess.run(["ipconfig", "/flushdns"], shell=True)
            nexus.status_lbl.setText("🌐 DNS Cache Flushed")

        elif cmd == "restart_explorer":
            subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
            subprocess.Popen(["explorer.exe"])
            nexus.status_lbl.setText("🔄 Windows Explorer Restarted")

        elif cmd == "toggle_desktop":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "(New-Object -ComObject shell.application).toggleDesktop()",
                ],
                shell=True,
            )
            nexus.status_lbl.setText("🖥️ Desktop Toggled")

        # --- POWER CONTROLS ---
        elif cmd == "cmd_lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            nexus.status_lbl.setText("🔒 Workstation Locked")

        elif cmd == "cmd_sleep":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Add-Type -Assembly System.Windows.Forms; "
                    "[System.Windows.Forms.Application]::SetSuspendState("
                    "[System.Windows.Forms.PowerState]::Suspend, $false, $false)",
                ],
                shell=True,
            )
            nexus.status_lbl.setText("💤 System Sleeping...")

        elif cmd == "cmd_restart":
            subprocess.run(["shutdown", "/r", "/t", "0"])

        elif cmd == "cmd_shutdown":
            subprocess.run(["shutdown", "/s", "/t", "0"])

        # --- SETTINGS LAUNCHERS ---
        elif cmd.startswith("ms-settings:"):
            webbrowser.open(cmd)
            setting_name = cmd.split(":")[-1].replace("-", " ").upper()
            nexus.status_lbl.setText(f"⚙️ Launched: {setting_name}")

        nexus.status_lbl.setStyleSheet("color: #a855f7; font-weight: bold;")

    except Exception as e:
        nexus.status_lbl.setText(f"Error executing toggle: {e}")
        nexus.status_lbl.setStyleSheet("color: #ef4444;")


def kill_process(nexus, pid: str, name: str) -> None:
    """Terminate a process by PID."""
    try:
        subprocess.Popen(f"taskkill /F /PID {pid}", shell=True)
        nexus.status_lbl.setText(f"💀 Terminated: {name}")
        nexus.status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
        QTimer.singleShot(500, lambda: update_process_cache(nexus, force=True))
    except Exception as e:
        nexus.status_lbl.setText(f"Error killing {name}: {e}")


def update_process_cache(nexus, force: bool = False) -> None:
    """Fetch running processes using tasklist (throttled)."""
    now = time.time()
    if not force and now - nexus.last_proc_update < 5:
        return

    try:
        output = subprocess.check_output("tasklist /fo csv /nh", shell=True).decode(
            "utf-8", errors="ignore"
        )
        lines = output.strip().split("\n")
        new_cache = []
        for line in lines:
            parts = line.replace('"', "").split(",")
            if len(parts) >= 5:
                new_cache.append({"name": parts[0], "pid": parts[1], "mem": parts[4]})
        nexus.process_cache = new_cache
        nexus.last_proc_update = now
    except Exception:
        pass


def trigger_reindex(nexus) -> None:
    """Launch X-Explorer in indexing mode."""
    nexus.status_lbl.setText("📡 Triggering File Indexer...")
    # Run as a module to handle relative imports correctly
    subprocess.Popen([sys.executable, "-m", "src.xexplorer.xexplorer"])


def run_macro(nexus, macro_id: int) -> None:
    """Execute a Ghost Typist macro in a background thread."""

    def runner():
        try:
            with sqlite3.connect(GHOST_TYPIST_DB) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT actions FROM macros WHERE id=?", (macro_id,))
                res = cursor.fetchone()
                if res:
                    import pyautogui

                    actions = json.loads(res[0])
                    time.sleep(0.3)
                    for a in actions:
                        if a["type"] == "wait":
                            time.sleep(a["value"] / 1000.0)
                        elif a["type"] == "type":
                            pyautogui.write(a["value"], interval=0.01)
                        elif a["type"] == "press":
                            pyautogui.press(a["value"])
                        elif a["type"] == "click":
                            pyautogui.click(x=a["x"], y=a["y"])
        except Exception:
            pass

    threading.Thread(target=runner, daemon=True).start()


def log_to_chronos(nexus, text: str) -> None:
    """Inject an achievement into the Chronos DB."""
    import datetime

    impact = "Medium"
    if text.startswith("!!! "):
        impact, text = "High", text[4:]
    elif text.startswith(". "):
        impact, text = "Low", text[2:]

    try:
        db_path = os.path.join(os.getenv("APPDATA", "."), "chronos_achievements.db")
        now = datetime.datetime.now()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO achievements (content, impact, week_number, year) VALUES (?, ?, ?, ?)",
                (text, impact, now.isocalendar()[1], now.year),
            )
        nexus.status_lbl.setText(f"🏆 Logged to Chronos: {text}")
        nexus.status_lbl.setStyleSheet("color: #fbbf24; font-weight: bold;")
    except Exception as e:
        nexus.status_lbl.setText(f"Chronos Log Error: {e}")
