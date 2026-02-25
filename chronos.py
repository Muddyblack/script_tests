import sys
import os
import sqlite3
import json
import datetime
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl, QTimer

# --- CONFIGURATION ---
APPDATA = os.getenv("APPDATA", os.path.expanduser("~"))
CHRONOS_DIR = os.path.join(APPDATA, ".chronos_app")
if not os.path.exists(CHRONOS_DIR):
    os.makedirs(CHRONOS_DIR)

CHRONOS_DB = os.path.join(CHRONOS_DIR, "chronos_data.db")
SETTINGS_FILE = os.path.join(CHRONOS_DIR, "chronos_settings.json")


def init_db():
    with sqlite3.connect(CHRONOS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT NOT NULL,
                impact TEXT DEFAULT 'Medium',
                week_number INTEGER,
                year INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'Pending'
            )
        """)
        conn.commit()


# --- BACKEND BRIDGE ---
class ChronosBridge(QObject):
    data_updated = pyqtSignal()
    reminder_triggered = pyqtSignal(str)  # Message

    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()

    @pyqtSlot(result=str)
    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError, PermissionError):
                pass
        return {"obsidian_path": "", "sync_enabled": False, "reminders_enabled": True}

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
                "SELECT id, content, timestamp, impact FROM achievements ORDER BY timestamp DESC"
            )
            achs = [
                {"id": r[0], "content": r[1], "timestamp": r[2], "impact": r[3]}
                for r in cursor.fetchall()
            ]

            cursor.execute(
                "SELECT id, content, timestamp, status FROM tasks ORDER BY status DESC, timestamp DESC"
            )
            tasks = [
                {"id": r[0], "content": r[1], "timestamp": r[2], "status": r[3]}
                for r in cursor.fetchall()
            ]

        return json.dumps(
            {"achievements": achs, "tasks": tasks, "settings": self.settings}
        )

    @pyqtSlot(str, str)
    def add_achievement(self, content, impact):
        now = datetime.datetime.now()
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(
                "INSERT INTO achievements (content, impact, week_number, year) VALUES (?, ?, ?, ?)",
                (content, impact, now.isocalendar()[1], now.year),
            )
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(str)
    def add_task(self, content):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("INSERT INTO tasks (content) VALUES (?)", (content,))
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(int, str)
    def update_task_status(self, tid, status):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid))
        self.data_updated.emit()
        self.trigger_sync()

    @pyqtSlot(int, str)
    def delete_item(self, iid, itype):
        table = "achievements" if itype == "achievement" else "tasks"
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute(f"DELETE FROM {table} WHERE id=?", (iid,))
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

    @pyqtSlot(str, result=str)
    def generate_summary(self, modifier):
        try:
            with sqlite3.connect(CHRONOS_DB) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT content, impact FROM achievements WHERE timestamp >= datetime('now', '{modifier}')"
                )
                achs = cursor.fetchall()
                cursor.execute(
                    f"SELECT content, status FROM tasks WHERE timestamp >= datetime('now', '{modifier}')"
                )
                tasks = cursor.fetchall()

            summ = "### 🚀 CHRONOS SUMMARY\n\n"
            if achs:
                summ += "#### 🏆 Achievements\n"
                for c, i in achs:
                    icon = "🔥" if i == "High" else "🔵" if i == "Medium" else "🟢"
                    summ += f"- {icon} {c}\n"
            if tasks:
                summ += "\n#### 📝 Missions\n"
                for c, s in tasks:
                    check = "[x]" if s == "Completed" else "[ ]"
                    summ += f"- {check} {c}\n"

            return summ
        except Exception as e:
            return f"Error: {str(e)}"

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
                "SELECT impact, content FROM achievements WHERE date(timestamp) = date('now')"
            )
            achs = cursor.fetchall()
            cursor.execute(
                "SELECT status, content FROM tasks WHERE date(timestamp) = date('now') OR status='Pending'"
            )
            tasks = cursor.fetchall()

        with open(f_path, "w", encoding="utf-8") as f:
            f.write(f"# ⏳ Chronos Daily Log: {now.strftime('%A, %b %d, %Y')}\n\n")
            f.write("## 🏆 Achievements\n")
            for i, c in achs:
                icon = "🔴" if i == "High" else "🔵"
                f.write(f"- {icon} **[{i}]** {c}\n")
            f.write("\n## 📝 Missions\n")
            for s, c in tasks:
                check = "[x]" if s == "Completed" else "[ ]"
                f.write(f"- {check} {c}\n")


class ChronosApp(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle("Chronos Hub Ultra")
        self.resize(1100, 850)

        # Web Engine View
        self.view = QWebEngineView()
        self.setCentralWidget(self.view)

        # Bridge Setup
        self.bridge = ChronosBridge()
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Load Content
        html_path = os.path.abspath("chronos_v3.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

        # Reminders
        self.rem_timer = QTimer(self)
        self.rem_timer.timeout.connect(self.check_reminders)
        self.rem_timer.start(60000)
        self.last_hour = -1

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
