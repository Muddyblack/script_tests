import datetime
import json
import os
import sqlite3
import ssl
import sys
import urllib.error
import urllib.request

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow

from src.common.config import CHRONOS_DB, CHRONOS_DIR, CHRONOS_SETTINGS
from src.common.theme import ThemeManager

os.makedirs(CHRONOS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Theme JSON → Web CSS variable mapping
# Only uses keys universal across all themes in src/themes/
# ---------------------------------------------------------------------------
WEB_CSS_MAP = {
    # Background layers
    "bg": "bg_base",
    "bg-1": "bg_base",
    "bg-2": "bg_elevated",
    "bg-3": "bg_overlay",
    "bg-4": "bg_control",
    "bg-selection": "bg_control_hov",
    # Accent
    "accent": "accent",
    "accent-bright": "accent_hover",
    "accent-primary": "accent",
    # Semantic hues mapped from theme semantics
    "gold": "warning",
    "gold-bright": "warning",
    "teal": "accent_pressed",
    "cyan": "accent_pressed",
    "rose": "danger",
    "error": "danger",
    "sage": "success",
    "mint": "success",
    "lavender": "accent_hover",
    "sky": "accent",
    # Text
    "text": "text_primary",
    "text-2": "text_secondary",
    "text-3": "text_disabled",
    "text-4": "text_disabled",
    # Borders
    "border": "border",
    "border-h": "border_light",
    "border-hh": "border_focus",
}

# Alpha variants computed from base hex colors
WEB_ALPHA_MAP = {
    "gold-dim": ("warning", 0.1),
    "gold-glow": ("warning", 0.2),
    "teal-dim": ("accent_pressed", 0.15),
    "rose-dim": ("danger", 0.15),
    "error-dim": ("danger", 0.15),
    "sage-dim": ("success", 0.15),
    "lav-dim": ("accent_hover", 0.15),
    "lavender-dim": ("accent_hover", 0.15),
    "sky-dim": ("accent", 0.15),
}


def _hex_to_rgb(h):
    """Convert '#RRGGBB' to (r, g, b). Returns None on failure."""
    h = h.lstrip("#")
    if len(h) < 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db():
    with sqlite3.connect(CHRONOS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT NOT NULL,
                impact TEXT DEFAULT 'Medium',
                notes TEXT,
                links TEXT,
                week_number INTEGER,
                year INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT NOT NULL,
                notes TEXT,
                links TEXT,
                status TEXT DEFAULT 'Pending',
                is_expanded INTEGER DEFAULT 1
            )
        """)

        # --- Migrations: achievements ---
        cursor = conn.execute("PRAGMA table_info(achievements)")
        cols = {c[1] for c in cursor.fetchall()}
        for col, spec in [("notes", "TEXT"), ("links", "TEXT")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE achievements ADD COLUMN {col} {spec}")

        # --- Migrations: tasks ---
        cursor = conn.execute("PRAGMA table_info(tasks)")
        cols = {c[1] for c in cursor.fetchall()}
        migrations = [
            ("parent_id", "INTEGER DEFAULT 0"),
            ("notes", "TEXT"),
            ("links", "TEXT"),
            ("is_expanded", "INTEGER DEFAULT 1"),
            ("priority", "TEXT DEFAULT 'Medium'"),
            ("due_date", "TEXT"),
            ("tags", "TEXT"),
            ("completed_at", "DATETIME"),
            ("is_achievement", "INTEGER DEFAULT 0"),
            ("position", "INTEGER DEFAULT 0"),
        ]
        for col, spec in migrations:
            if col not in cols:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {spec}")

        # Migrate old achievements into tasks
        ach_cursor = conn.execute(
            "SELECT content, timestamp, impact, notes, links FROM achievements"
        )
        old_achs = ach_cursor.fetchall()
        if old_achs:
            for content, ts, impact, notes, links in old_achs:
                conn.execute(
                    "INSERT INTO tasks (content, timestamp, notes, links, status, "
                    "completed_at, is_achievement, priority) "
                    "VALUES (?, ?, ?, ?, 'Completed', ?, 1, ?)",
                    (content, ts, notes, links, ts, impact or "Medium"),
                )
            conn.execute("DELETE FROM achievements")

        conn.commit()


# ---------------------------------------------------------------------------
# Backend Bridge
# ---------------------------------------------------------------------------
class ChronosBridge(QObject):
    data_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.settings = self._load_settings()

    def _load_settings(self):
        if os.path.exists(CHRONOS_SETTINGS):
            try:
                with open(CHRONOS_SETTINGS) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "obsidian_path": "",
            "sync_enabled": False,
            "reminders_enabled": True,
            "ai_url": "",
            "ai_key": "",
            "ai_model": "",
            "ai_cert_path": "",
            "world_clocks": [],
        }

    def _save_settings(self):
        with open(CHRONOS_SETTINGS, "w") as f:
            json.dump(self.settings, f)

    # --- Settings ---
    @pyqtSlot(result=str)
    def load_settings(self):
        return json.dumps(self.settings)

    @pyqtSlot(str)
    def save_settings(self, settings_json):
        self.settings = json.loads(settings_json)
        self._save_settings()
        self._trigger_sync()

    # --- Data ---
    @pyqtSlot(result=str)
    def get_all_data(self):
        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, parent_id, content, notes, links, timestamp, status, "
                "is_expanded, priority, due_date, tags, completed_at, "
                "is_achievement, position "
                "FROM tasks ORDER BY position ASC, parent_id ASC, timestamp DESC"
            )
            tasks = [
                {
                    "id": r[0],
                    "parent_id": r[1],
                    "content": r[2],
                    "notes": r[3],
                    "links": r[4],
                    "timestamp": r[5],
                    "status": r[6],
                    "is_expanded": r[7],
                    "priority": r[8] or "Medium",
                    "due_date": r[9],
                    "tags": r[10].split(",") if r[10] else [],
                    "completed_at": r[11],
                    "is_achievement": bool(r[12]),
                    "position": r[13] or 0,
                }
                for r in cursor.fetchall()
            ]
        return json.dumps({"tasks": tasks, "settings": self.settings})

    # --- Tasks ---
    @pyqtSlot(str, int, str, str, str, str, int, bool)
    def add_task(
        self, content, _dummy, notes, tags, priority, due_date, parent_id, is_ach
    ):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "INSERT INTO tasks (content, parent_id, notes, tags, priority, "
                "due_date, is_achievement) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (content, parent_id, notes, tags, priority, due_date, int(is_ach)),
            )
        self.data_updated.emit()
        self._trigger_sync()

    @pyqtSlot(int, str, str, str)
    def update_task(self, tid, content, notes, links):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "UPDATE tasks SET content=?, notes=?, links=? WHERE id=?",
                (content, notes, links, tid),
            )
        self.data_updated.emit()
        self._trigger_sync()

    @pyqtSlot(int, str)
    def update_task_status(self, tid, status):
        now = datetime.datetime.now().isoformat() if status == "Completed" else None
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
                (status, now, tid),
            )
        self.data_updated.emit()
        self._trigger_sync()

    @pyqtSlot(int, int)
    def update_task_expansion(self, tid, expanded):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("UPDATE tasks SET is_expanded=? WHERE id=?", (expanded, tid))

    @pyqtSlot(int, bool)
    def update_task_achievement(self, tid, is_ach):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "UPDATE tasks SET is_achievement=? WHERE id=?", (int(is_ach), tid)
            )
        self.data_updated.emit()

    @pyqtSlot(int)
    def delete_task(self, tid):
        with sqlite3.connect(CHRONOS_DB) as conn:
            self._delete_tree(conn, tid)
        self.data_updated.emit()
        self._trigger_sync()

    def _delete_tree(self, conn, task_id):
        children = conn.execute(
            "SELECT id FROM tasks WHERE parent_id=?", (task_id,)
        ).fetchall()
        for (child_id,) in children:
            self._delete_tree(conn, child_id)
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    # --- Export / Clear ---
    @pyqtSlot(result=str)
    def export_data(self):
        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks")
            desc = [d[0] for d in cursor.description]
            tasks = [dict(zip(desc, row, strict=False)) for row in cursor.fetchall()]
        return json.dumps(
            {
                "tasks": tasks,
                "settings": self.settings,
                "exported_at": datetime.datetime.now().isoformat(),
            },
            indent=2,
        )

    @pyqtSlot()
    def clear_completed(self):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("DELETE FROM tasks WHERE status='Completed'")
        self.data_updated.emit()

    # --- Obsidian ---
    @pyqtSlot()
    def select_obsidian_path(self):
        dir_path = QFileDialog.getExistingDirectory(None, "Select Obsidian Vault")
        if dir_path:
            self.settings["obsidian_path"] = dir_path
            self._save_settings()
            self.data_updated.emit()
            self._trigger_sync()

    # --- AI ---
    @pyqtSlot(result=str)
    def select_cert_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select CA Certificate",
            "",
            "Certificates (*.pem *.crt *.cer);;All Files (*)",
        )
        return file_path

    @pyqtSlot(result=str)
    def get_ai_models(self):
        base_url = self.settings.get("ai_url", "").rstrip("/")
        api_key = self.settings.get("ai_key", "")
        cert_path = self.settings.get("ai_cert_path", "")
        if not base_url:
            return json.dumps([])
        url = f"{base_url}/api/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            context = ssl.create_default_context()
            if cert_path and os.path.exists(cert_path):
                context.load_verify_locations(cert_path)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=context) as response:
                data = json.loads(response.read().decode())
                if isinstance(data, list):
                    return json.dumps(data)
                if "data" in data:
                    return json.dumps(
                        [m["id"] if isinstance(m, dict) else m for m in data["data"]]
                    )
                if "models" in data:
                    return json.dumps(
                        [
                            m["name"] if isinstance(m, dict) else m
                            for m in data["models"]
                        ]
                    )
                return json.dumps([str(data)])
        except Exception:
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def get_ai_recap(self, prompt):
        base_url = self.settings.get("ai_url", "").rstrip("/")
        api_key = self.settings.get("ai_key", "")
        model = self.settings.get("ai_model", "")
        cert_path = self.settings.get("ai_cert_path", "")
        if not base_url:
            return "Error: No AI API URL configured in settings."
        url = f"{base_url}/api/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0.7,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        try:
            context = ssl.create_default_context()
            if cert_path and os.path.exists(cert_path):
                context.load_verify_locations(cert_path)
            elif cert_path:
                return f"Error: Certificate not found: {cert_path}"
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, context=context) as response:
                result = json.loads(response.read().decode())
                if "choices" in result:
                    return result["choices"][0]["message"]["content"]
                if "message" in result:
                    return result["message"]["content"]
                return json.dumps(result)
        except urllib.error.URLError as e:
            return f"Connection Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    # --- Timeline Scanner ---
    @pyqtSlot(str, result=str)
    def generate_summary(self, modifier):
        try:
            now = datetime.datetime.now()
            if modifier == "daily":
                date_filter = "date(timestamp) = date('now')"
                title = f"Daily Report — {now.strftime('%b %d, %Y')}"
                period_days = 1
            elif modifier == "weekly":
                date_filter = "timestamp >= datetime('now', '-7 days')"
                title = "Weekly Report"
                period_days = 7
            elif modifier == "monthly":
                date_filter = "timestamp >= datetime('now', '-1 month')"
                title = "Monthly Report"
                period_days = 30
            else:
                date_filter = f"timestamp >= datetime('now', '{modifier}')"
                title = f"Custom Report: {modifier}"
                period_days = 1

            with sqlite3.connect(CHRONOS_DB) as conn:
                cursor = conn.cursor()

                ts_filter = date_filter.replace(
                    "timestamp", "coalesce(completed_at, timestamp)"
                )
                cursor.execute(
                    f"SELECT content, priority, notes, timestamp, completed_at "
                    f"FROM tasks WHERE status='Completed' AND {ts_filter} "
                    f"ORDER BY priority DESC"
                )
                completed = cursor.fetchall()

                cursor.execute(
                    "SELECT content, priority, due_date FROM tasks "
                    "WHERE status='Pending' ORDER BY priority DESC"
                )
                pending = cursor.fetchall()

                cursor.execute(
                    f"SELECT content, priority FROM tasks "
                    f"WHERE is_achievement=1 AND status='Completed' AND {ts_filter}"
                )
                achievements = cursor.fetchall()

            s = f"### {title}\n\n"

            n_done = len(completed)
            velocity = round(n_done / max(period_days, 1), 1)
            s += f"**{n_done}** tasks completed"
            if period_days > 1:
                s += f" ({velocity}/day)"
            s += "\n\n"

            pri_counts = {"High": 0, "Medium": 0, "Low": 0}
            completion_times = []
            for _content, pri, _notes, created, done_at in completed:
                pri_counts[pri or "Medium"] = pri_counts.get(pri or "Medium", 0) + 1
                if created and done_at:
                    try:
                        dt_c = datetime.datetime.fromisoformat(created)
                        dt_d = datetime.datetime.fromisoformat(done_at)
                        completion_times.append((dt_d - dt_c).total_seconds() / 3600)
                    except (ValueError, TypeError):
                        pass

            if any(pri_counts.values()):
                s += "**Breakdown:** "
                parts = []
                if pri_counts["High"]:
                    parts.append(f"{pri_counts['High']} high")
                if pri_counts["Medium"]:
                    parts.append(f"{pri_counts['Medium']} medium")
                if pri_counts["Low"]:
                    parts.append(f"{pri_counts['Low']} low")
                s += " / ".join(parts) + "\n\n"

            if completion_times:
                avg_h = sum(completion_times) / len(completion_times)
                if avg_h < 1:
                    s += f"**Avg completion time:** {int(avg_h * 60)} min\n\n"
                elif avg_h < 24:
                    s += f"**Avg completion time:** {avg_h:.1f} hours\n\n"
                else:
                    s += f"**Avg completion time:** {avg_h / 24:.1f} days\n\n"

            if completed:
                s += "#### Completed\n"
                for c_content, c_pri, _notes, _ts, _ca in completed:
                    marker = "!" if c_pri == "High" else "-"
                    s += f"- {marker} {c_content}\n"
                s += "\n"

            if achievements:
                s += "#### Achievements\n"
                for a_content, _pri in achievements:
                    s += f"- **{a_content}**\n"
                s += "\n"

            n_pending = len(pending)
            high_pending = [p for p in pending if p[1] == "High"]
            overdue = [p for p in pending if p[2] and p[2] < now.strftime("%Y-%m-%d")]
            s += f"#### Active ({n_pending})\n"
            if overdue:
                s += f"**{len(overdue)} overdue**\n"
            for content, _pri, _dd in high_pending[:5]:
                s += f"- **[High]** {content}\n"
            remaining = n_pending - len(high_pending[:5])
            if remaining > 0:
                s += f"- ... and {remaining} more\n"

            return s
        except Exception as e:
            import traceback

            traceback.print_exc()
            return f"Error: {e}"

    # --- World Clocks ---
    @pyqtSlot(result=str)
    def get_world_clocks(self):
        return json.dumps(self.settings.get("world_clocks", []))

    @pyqtSlot(str)
    def save_world_clocks(self, clocks_json):
        self.settings["world_clocks"] = json.loads(clocks_json)
        self._save_settings()

    # --- Obsidian Sync ---
    def _trigger_sync(self):
        if self.settings.get("sync_enabled") and self.settings.get("obsidian_path"):
            self._sync_to_obsidian()

    def _sync_to_obsidian(self):
        v_path = self.settings["obsidian_path"]
        if not os.path.exists(v_path):
            return
        base_dir = os.path.join(v_path, "Chronos_Sync")
        daily_dir = os.path.join(base_dir, "Daily")
        weekly_dir = os.path.join(base_dir, "Weekly")
        for d in [base_dir, daily_dir, weekly_dir]:
            os.makedirs(d, exist_ok=True)

        now = datetime.datetime.now()
        f_path = os.path.join(daily_dir, f"Log_{now.strftime('%Y-%m-%d')}.md")
        week_num = now.isocalendar()[1]
        w_path = os.path.join(weekly_dir, f"Week_{week_num:02d}_{now.year}.md")

        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, content, notes, priority, tags, is_achievement "
                "FROM tasks WHERE date(timestamp) = date('now') OR status='Pending'"
            )
            tasks = cursor.fetchall()
            cursor.execute(
                "SELECT content, priority FROM tasks "
                "WHERE is_achievement=1 AND status='Completed' "
                "AND date(coalesce(completed_at, timestamp)) = date('now')"
            )
            today_achs = cursor.fetchall()
            cursor.execute(
                "SELECT content, priority FROM tasks "
                "WHERE is_achievement=1 AND status='Completed' "
                "AND strftime('%%W', coalesce(completed_at, timestamp)) = ? "
                "AND strftime('%%Y', coalesce(completed_at, timestamp)) = ?",
                (f"{week_num:02d}", str(now.year)),
            )
            week_achs = cursor.fetchall()

        with open(f_path, "w", encoding="utf-8") as f:
            f.write(f"# Chronos Daily Log: {now.strftime('%A, %b %d, %Y')}\n\n")
            if today_achs:
                f.write("## Achievements\n")
                for content, pri in today_achs:
                    f.write(f"- **{content}** ({pri})\n")
                f.write("\n")
            f.write("## Tasks\n")
            for status, content, notes, priority, tags, _ia in tasks:
                check = "[x]" if status == "Completed" else "[ ]"
                pri_tag = f" [{priority}]" if priority != "Medium" else ""
                tag_str = f" #{tags}" if tags else ""
                f.write(f"- {check}{pri_tag}{tag_str} {content}\n")
                if notes:
                    f.write(f"  - {notes}\n")

        with open(w_path, "w", encoding="utf-8") as f:
            f.write(f"# Chronos Weekly: Week {week_num}, {now.year}\n\n")
            if week_achs:
                f.write(f"**Achievements:** {len(week_achs)}\n\n")
                for content, _pri in week_achs:
                    f.write(f"- {content}\n")


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class ChronosApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mgr = ThemeManager()
        init_db()
        self.setWindowTitle("Chronos")
        try:
            from src.common.config import ICON_PATH

            if os.path.exists(ICON_PATH):
                self.setWindowIcon(QIcon(ICON_PATH))
        except ImportError:
            pass
        self.resize(1200, 900)

        self.view = QWebEngineView()
        self.view.page().setBackgroundColor(QColor(self.mgr["bg_base"]))
        self.mgr.theme_changed.connect(self._apply_theme)

        attrs = self.view.settings()
        dev_attr = getattr(
            QWebEngineSettings.WebAttribute, "DeveloperExtrasEnabled", None
        )
        if dev_attr is not None:
            attrs.setAttribute(dev_attr, True)

        self.setCentralWidget(self.view)

        self.bridge = ChronosBridge()
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.shortcut = QShortcut(QKeySequence("F12"), self)
        self.shortcut.activated.connect(self._open_devtools)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(script_dir, "chronos_v4.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

        self.rem_timer = QTimer(self)
        self.rem_timer.timeout.connect(self._check_reminders)
        self.rem_timer.start(60000)
        self.last_hour = -1
        self._apply_theme()

    def _apply_theme(self):
        colors = self.mgr.theme_data.get("colors", {})
        parts = []

        # 1) All raw theme colors as CSS vars
        for name, color in colors.items():
            parts.append(f"--{name.replace('_', '-')}: {color}")

        # 2) Mapped web vars
        for css_var, theme_key in WEB_CSS_MAP.items():
            val = colors.get(theme_key)
            if val:
                parts.append(f"--{css_var}: {val}")

        # 3) Alpha variants
        for css_var, (theme_key, alpha) in WEB_ALPHA_MAP.items():
            val = colors.get(theme_key)
            if val:
                rgb = _hex_to_rgb(val)
                if rgb:
                    r, g, b = rgb
                    parts.append(f"--{css_var}: rgba({r},{g},{b},{alpha})")

        # 4) Shadows based on dark/light
        if self.mgr.is_dark:
            parts.append("--shadow-sm: 0 2px 8px rgba(0,0,0,0.6)")
            parts.append("--shadow-md: 0 8px 32px rgba(0,0,0,0.7)")
            parts.append("--shadow-lg: 0 24px 64px rgba(0,0,0,0.8)")
            parts.append("--grain-opacity: 0.025")
        else:
            parts.append("--shadow-sm: 0 2px 8px rgba(0,0,0,0.08)")
            parts.append("--shadow-md: 0 8px 32px rgba(0,0,0,0.12)")
            parts.append("--shadow-lg: 0 24px 64px rgba(0,0,0,0.18)")
            parts.append("--grain-opacity: 0.01")

        # 5) Color scheme for native inputs
        scheme = "dark" if self.mgr.is_dark else "light"
        parts.append(f"color-scheme: {scheme}")

        css_text = "; ".join(parts)
        script = f"document.documentElement.style.cssText = `{css_text}`;"
        self.view.page().runJavaScript(script)
        self.view.page().setBackgroundColor(QColor(self.mgr["bg_base"]))

    def _open_devtools(self):
        self.devtools_view = QWebEngineView()
        self.devtools_view.setWindowTitle("Chronos DevTools")
        self.devtools_view.resize(1000, 700)
        self.view.page().setDevToolsPage(self.devtools_view.page())
        self.devtools_view.show()

    def _check_reminders(self):
        if not self.bridge.settings.get("reminders_enabled"):
            return
        hr = datetime.datetime.now().hour
        if hr in [12, 17] and hr != self.last_hour:
            self.last_hour = hr
            self.view.page().runJavaScript("triggerReminderPopup()")
            self.showNormal()
            self.activateWindow()


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.chronos")
    app = QApplication(sys.argv)
    window = ChronosApp()
    window.show()
    sys.exit(app.exec())
