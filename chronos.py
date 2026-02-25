import sys
import os
import sqlite3
import json
import datetime
import urllib.request
import urllib.error
import ssl
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWebEngineCore import QWebEngineSettings

# --- CONFIGURATION ---
APPDATA = os.getenv("APPDATA", os.path.expanduser("~"))
CHRONOS_DIR = os.path.join(APPDATA, ".chronos_app")
if not os.path.exists(CHRONOS_DIR):
    os.makedirs(CHRONOS_DIR)

CHRONOS_DB = os.path.join(CHRONOS_DIR, "chronos_data.db")
SETTINGS_FILE = os.path.join(CHRONOS_DIR, "chronos_settings.json")


def init_db():
    with sqlite3.connect(CHRONOS_DB) as conn:
        # Achievements Table
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
        # Missions Table (Google Tasks style)
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

        # Schema Migrations
        cursor = conn.execute("PRAGMA table_info(achievements)")
        cols = [c[1] for c in cursor.fetchall()]
        if "notes" not in cols:
            conn.execute("ALTER TABLE achievements ADD COLUMN notes TEXT")
        if "links" not in cols:
            conn.execute("ALTER TABLE achievements ADD COLUMN links TEXT")

        cursor = conn.execute("PRAGMA table_info(tasks)")
        cols = [c[1] for c in cursor.fetchall()]
        if "parent_id" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN parent_id INTEGER DEFAULT 0")
        if "notes" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
        if "links" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN links TEXT")
        if "is_expanded" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN is_expanded INTEGER DEFAULT 1")

        conn.commit()


# --- BACKEND BRIDGE ---
class ChronosBridge(QObject):
    data_updated = pyqtSignal()
    reminder_triggered = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()

    @pyqtSlot(result=str)
    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "obsidian_path": "",
            "sync_enabled": False,
            "reminders_enabled": True,
            "ai_url": "http://localhost:11434",  # Default for local Ollama/similar
            "ai_key": "",
            "ai_model": "",
            "ai_cert_path": "",
        }

    @pyqtSlot(str)
    def save_settings(self, settings_json):
        self.settings = json.loads(settings_json)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f)
        self.trigger_sync()

    @pyqtSlot(result=str)
    def get_all_data(self):
        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, content, timestamp, impact, notes, links FROM achievements ORDER BY timestamp DESC"
            )
            achs = [
                {
                    "id": r[0],
                    "content": r[1],
                    "timestamp": r[2],
                    "impact": r[3],
                    "notes": r[4],
                    "links": r[5],
                }
                for r in cursor.fetchall()
            ]

            cursor.execute(
                "SELECT id, parent_id, content, notes, links, timestamp, status, is_expanded FROM tasks ORDER BY parent_id ASC, timestamp DESC"
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
                }
                for r in cursor.fetchall()
            ]

        return json.dumps(
            {"achievements": achs, "tasks": tasks, "settings": self.settings}
        )

    @pyqtSlot(str, str, str, str)
    def add_achievement(self, content, impact, notes, links):
        now = datetime.datetime.now()
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "INSERT INTO achievements (content, impact, notes, links, week_number, year) VALUES (?, ?, ?, ?, ?, ?)",
                (content, impact, notes, links, now.isocalendar()[1], now.year),
            )
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(int, str, str, str, str)
    def update_achievement(self, aid, content, impact, notes, links):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "UPDATE achievements SET content=?, impact=?, notes=?, links=? WHERE id=?",
                (content, impact, notes, links, aid),
            )
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(str, int, str, str)
    def add_task(self, content, parent_id, notes, links):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "INSERT INTO tasks (content, parent_id, notes, links) VALUES (?, ?, ?, ?)",
                (content, parent_id, notes, links),
            )
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(int, str, str, str)
    def update_task(self, tid, content, notes, links):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "UPDATE tasks SET content=?, notes=?, links=? WHERE id=?",
                (content, notes, links, tid),
            )
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(int, str)
    def update_task_status(self, tid, status):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid))
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(int, int)
    def update_task_expansion(self, tid, expanded):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("UPDATE tasks SET is_expanded=? WHERE id=?", (expanded, tid))
        self.data_updated.emit()

    @pyqtSlot(int, str)
    def delete_item(self, iid, itype):
        table = "achievements" if itype == "achievement" else "tasks"
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(f"DELETE FROM {table} WHERE id=?", (iid,))
            if itype == "task":
                conn.execute("DELETE FROM tasks WHERE parent_id=?", (iid,))
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot()
    def select_obsidian_path(self):
        dir_path = QFileDialog.getExistingDirectory(None, "Select Obsidian Vault")
        if dir_path:
            self.settings["obsidian_path"] = dir_path
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f)
            self.data_updated.emit()
            self.trigger_sync()

    @pyqtSlot(result=str)
    def select_cert_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select CA Certificate",
            "",
            "Certificates (*.pem *.crt *.cer);;All Files (*)",
        )
        return file_path

    @pyqtSlot(str, result=str)
    def generate_summary(self, modifier):
        try:
            with sqlite3.connect(CHRONOS_DB) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT content, impact, notes FROM achievements WHERE timestamp >= datetime('now', '{modifier}')"
                )
                achs = cursor.fetchall()
                cursor.execute(
                    f"SELECT content, status, notes FROM tasks WHERE timestamp >= datetime('now', '{modifier}')"
                )
                tasks = cursor.fetchall()

            summ = "### 🚀 CHRONOS SUMMARY\n\n"
            if achs:
                summ += "#### 🏆 Achievements\n"
                for c, i, n in achs:
                    icon = "🔥" if i == "High" else "🔵" if i == "Medium" else "🟢"
                    summ += f"- {icon} **{c}**\n"
                    if n:
                        summ += f"  > {n}\n"
            if tasks:
                summ += "\n#### 📝 Missions\n"
                for c, s, n in tasks:
                    check = "[x]" if s == "Completed" else "[ ]"
                    summ += f"- {check} {c}\n"
                    if n:
                        summ += f"  *Note: {n}*\n"
            return summ
        except (sqlite3.Error, Exception) as e:
            return f"Error: {str(e)}"

    @pyqtSlot(str, result=str)
    def get_ai_recap(self, prompt):
        base_url = self.settings.get("ai_url", "").rstrip("/")
        api_key = self.settings.get("ai_key", "")
        model = self.settings.get("ai_model", "")
        cert_path = self.settings.get("ai_cert_path", "")

        if not base_url:
            return "Error: No AI API URL defined in settings."

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
                return f"Error: Certificate path not found: {cert_path}"

            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, context=context) as response:
                result = json.loads(response.read().decode())
                # Handle common response formats (OpenAI / Ollama style)
                if "choices" in result:
                    return result["choices"][0]["message"]["content"]
                elif "message" in result:
                    return result["message"]["content"]
                return json.dumps(result)
        except urllib.error.URLError as e:
            return f"Connection Error: {str(e)}"
        except Exception as e:
            return f"AI Logic Error: {str(e)}"

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
                # Handle common model list formats
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
        except (urllib.error.URLError, json.JSONDecodeError, Exception):
            return json.dumps([])

    def trigger_sync(self):
        if self.settings.get("sync_enabled") and self.settings.get("obsidian_path"):
            self.sync_to_obsidian()

    def sync_to_obsidian(self):
        v_path = self.settings["obsidian_path"]
        if not os.path.exists(v_path):
            return
        sync_dir = os.path.join(v_path, "Chronos_Sync")
        if not os.path.exists(sync_dir):
            os.makedirs(sync_dir)

        now = datetime.datetime.now()
        f_path = os.path.join(sync_dir, f"Log_{now.strftime('%Y-%m-%d')}.md")

        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT impact, content, notes, links FROM achievements WHERE date(timestamp) = date('now')"
            )
            achs = cursor.fetchall()
            cursor.execute(
                "SELECT status, content, notes, links FROM tasks WHERE date(timestamp) = date('now') OR status='Pending'"
            )
            tasks = cursor.fetchall()

        with open(f_path, "w", encoding="utf-8") as f:
            f.write(f"# ⏳ Chronos Daily Log: {now.strftime('%A, %b %d, %Y')}\n\n")
            f.write("## 🏆 Achievements\n")
            for impact, content, notes, link in achs:
                icon = "🔴" if impact == "High" else "🔵"
                f.write(f"- {icon} **[{impact}]** {content}\n")
                if notes:
                    f.write(f"  - Notes: {notes}\n")
                if link:
                    f.write(f"  - Links: {link}\n")
            f.write("\n## 📝 Missions\n")
            for status, content, notes, link in tasks:
                check = "[x]" if status == "Completed" else "[ ]"
                f.write(f"- {check} {content}\n")
                if notes:
                    f.write(f"  - Notes: {notes}\n")
                if link:
                    f.write(f"  - Links: {link}\n")


class ChronosApp(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle("Chronos Hub Ultra")
        self.resize(1200, 900)

        self.view = QWebEngineView()
        self.view.page().setBackgroundColor(QColor("#03233A"))

        # Safely enable dev tools if available
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

        # F12 DevTools
        self.shortcut = QShortcut(QKeySequence("F12"), self)
        self.shortcut.activated.connect(self.open_devtools)

        html_path = os.path.abspath("chronos_v4.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

        self.rem_timer = QTimer(self)
        self.rem_timer.timeout.connect(self.check_reminders)
        self.rem_timer.start(60000)
        self.last_hour = -1

    def open_devtools(self):
        self.devtools_view = QWebEngineView()
        self.devtools_view.setWindowTitle("Chronos - Tactical Intelligence Inspector")
        self.devtools_view.resize(1000, 700)
        self.view.page().setDevToolsPage(self.devtools_view.page())
        self.devtools_view.show()

    def check_reminders(self):
        if not self.bridge.settings.get("reminders_enabled"):
            return
        hr = datetime.datetime.now().hour
        if hr in [12, 17] and hr != self.last_hour:
            self.last_hour = hr
            self.view.page().runJavaScript("triggerReminderPopup()")
            self.showNormal()
            self.activateWindow()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChronosApp()
    window.show()
    sys.exit(app.exec())
