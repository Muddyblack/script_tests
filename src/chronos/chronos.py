import datetime
import json
import os
import sqlite3
import ssl
import sys
import urllib.error
import urllib.request

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow

from src.common.config import CHRONOS_DB, CHRONOS_DIR, CHRONOS_SETTINGS
from src.common.theme import ThemeManager, WebThemeBridge

os.makedirs(CHRONOS_DIR, exist_ok=True)


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
            ("time_spent", "INTEGER DEFAULT 0"),
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
# Async AI Worker
# ---------------------------------------------------------------------------
class _AIWorker(QThread):
    finished = pyqtSignal(str, str)  # (request_id, response_text)

    def __init__(self, bridge, messages, request_id):
        super().__init__()
        self.bridge = bridge
        self.messages = messages
        self.request_id = request_id

    def run(self):
        try:
            result = self.bridge._send_chat(self.messages)
        except Exception as e:
            result = f"Error: {e}"
        self.finished.emit(self.request_id, result)


# ---------------------------------------------------------------------------
# Backend Bridge
# ---------------------------------------------------------------------------
class ChronosBridge(QObject):
    data_updated = pyqtSignal()
    ai_response = pyqtSignal(str, str)  # (request_id, response_text) → JS

    def __init__(self):
        super().__init__()
        self.settings = self._load_settings()
        self._ai_worker = None

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
            "ai_provider": "openai_compat",
            "ai_system_prompt": "",
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
                "is_achievement, position, time_spent "
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
                    "time_spent": r[14] or 0,
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

    @pyqtSlot(int, int)
    def update_task_time(self, tid, seconds):
        with sqlite3.connect(CHRONOS_DB) as conn:
            conn.execute("UPDATE tasks SET time_spent=? WHERE id=?", (seconds, tid))
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

    def _make_ssl_context(self):
        cert_path = self.settings.get("ai_cert_path", "")
        context = ssl.create_default_context()
        if cert_path and os.path.exists(cert_path):
            context.load_verify_locations(cert_path)
        elif cert_path:
            raise FileNotFoundError(f"Certificate not found: {cert_path}")
        return context

    def _fetch_json(self, url, headers, payload=None):
        """GET if payload is None, POST otherwise. Returns parsed dict/list."""
        context = self._make_ssl_context()
        if payload is not None:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
        else:
            req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=context) as resp:
            return json.loads(resp.read().decode())

    @pyqtSlot(result=str)
    def get_ai_models(self):
        provider = self.settings.get("ai_provider", "openai_compat")
        base_url = self.settings.get("ai_url", "").rstrip("/")
        api_key = self.settings.get("ai_key", "")
        if not base_url and provider != "google_gemini":
            return json.dumps([])
        try:
            if provider == "google_gemini":
                # Gemini lists models via its own endpoint; base_url may be empty
                host = base_url or "https://generativelanguage.googleapis.com"
                url = f"{host}/v1beta/models?key={api_key}"
                data = self._fetch_json(url, {})
                models = data.get("models", [])
                return json.dumps(
                    [
                        m["name"].replace("models/", "")
                        for m in models
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ]
                )
            elif provider == "anthropic":
                # Anthropic doesn't expose a public list-models endpoint;
                # return well-known model IDs so the user can pick one.
                return json.dumps(
                    [
                        "claude-opus-4-6",
                        "claude-sonnet-4-6",
                        "claude-haiku-4-5-20251001",
                    ]
                )
            else:
                # openai_compat: works for OpenAI, OpenWebUI, Ollama, llama.cpp, etc.
                # Try /v1/models first (OpenAI standard), fall back to /api/models (OpenWebUI).
                for path in ("/v1/models", "/api/models"):
                    try:
                        data = self._fetch_json(
                            f"{base_url}{path}",
                            {"Authorization": f"Bearer {api_key}"},
                        )
                        if isinstance(data, list):
                            return json.dumps(data)
                        if "data" in data:
                            return json.dumps(
                                [
                                    m["id"] if isinstance(m, dict) else m
                                    for m in data["data"]
                                ]
                            )
                        if "models" in data:
                            return json.dumps(
                                [
                                    m.get("name", m.get("id", m))
                                    if isinstance(m, dict)
                                    else m
                                    for m in data["models"]
                                ]
                            )
                    except Exception:
                        continue
                return json.dumps([])
        except Exception:
            return json.dumps([])

    def _send_chat(self, messages):
        """Send a list of {role, content} messages to the AI. Returns text.

        Called from worker threads — must not touch Qt widgets.
        """
        provider = self.settings.get("ai_provider", "openai_compat")
        base_url = self.settings.get("ai_url", "").rstrip("/")
        api_key = self.settings.get("ai_key", "")
        model = self.settings.get("ai_model", "")

        if not api_key and provider in ("google_gemini", "anthropic"):
            return "Error: No API key configured in settings."

        if provider == "google_gemini":
            host = base_url or "https://generativelanguage.googleapis.com"
            model_id = model or "gemini-2.0-flash"
            url = f"{host}/v1beta/models/{model_id}:generateContent?key={api_key}"
            contents = []
            for m in messages:
                role = "model" if m["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
            payload = {"contents": contents}
            data = self._fetch_json(
                url, {"Content-Type": "application/json"}, payload
            )
            return data["candidates"][0]["content"]["parts"][0]["text"]

        elif provider == "anthropic":
            host = base_url or "https://api.anthropic.com"
            url = f"{host}/v1/messages"
            # Anthropic expects system as a top-level param, not in messages
            sys_msgs = [m["content"] for m in messages if m["role"] == "system"]
            chat_msgs = [m for m in messages if m["role"] != "system"]
            payload = {
                "model": model or "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": chat_msgs,
            }
            if sys_msgs:
                payload["system"] = "\n\n".join(sys_msgs)
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            data = self._fetch_json(url, headers, payload)
            return data["content"][0]["text"]

        else:
            # openai_compat
            if not base_url:
                return "Error: No AI API URL configured in settings."
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "temperature": 0.7,
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            last_err = None
            for path in ("/v1/chat/completions", "/api/chat/completions"):
                try:
                    data = self._fetch_json(f"{base_url}{path}", headers, payload)
                    if "choices" in data:
                        return data["choices"][0]["message"]["content"]
                    if "message" in data:
                        return data["message"]["content"]
                    return json.dumps(data)
                except Exception as e:
                    last_err = e
                    continue
            return f"Error: {last_err}"

    @pyqtSlot(str, result=str)
    def get_ai_recap(self, prompt):
        """Synchronous single-prompt AI call (kept for non-chat uses)."""
        try:
            return self._send_chat([{"role": "user", "content": prompt}])
        except FileNotFoundError as e:
            return f"Error: {e}"
        except urllib.error.URLError as e:
            return f"Connection Error: {e}"
        except (KeyError, IndexError) as e:
            return f"Error parsing response: {e}"
        except Exception as e:
            return f"Error: {e}"

    @pyqtSlot(str, str)
    def send_ai_chat(self, messages_json, request_id):
        """Async AI chat — runs in a QThread, emits ai_response when done."""
        messages = json.loads(messages_json)
        # Prepend system prompt if configured
        sys_prompt = self.settings.get("ai_system_prompt", "").strip()
        if sys_prompt and not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": sys_prompt})
        worker = _AIWorker(self, messages, request_id)
        worker.finished.connect(self._on_ai_done)
        # prevent GC
        self._ai_worker = worker
        worker.start()

    def _on_ai_done(self, request_id, text):
        self.ai_response.emit(request_id, text)

    @pyqtSlot(result=str)
    def get_task_context(self):
        """Return a compact summary of active tasks for AI context."""
        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content, priority, status, due_date, notes, tags "
                "FROM tasks WHERE status='Pending' ORDER BY priority DESC LIMIT 20"
            )
            pending = cursor.fetchall()
        lines = ["## Active Tasks"]
        for c, pri, _s, due, notes, tags in pending:
            extra = []
            if due:
                extra.append(f"due:{due}")
            if tags:
                extra.append(f"#{tags}")
            suffix = f" ({', '.join(extra)})" if extra else ""
            lines.append(f"- [{pri}] {c}{suffix}")
            if notes:
                lines.append(f"  Notes: {notes}")
        return "\n".join(lines)

    @pyqtSlot(int, result=str)
    def get_task_detail(self, task_id):
        """Return detailed info about a single task for AI chat."""
        with sqlite3.connect(CHRONOS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content, priority, status, due_date, notes, tags, "
                "timestamp, completed_at, time_spent "
                "FROM tasks WHERE id=?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return ""
            c, pri, status, due, notes, tags, ts, done, spent = row
            # Also get subtasks
            cursor.execute(
                "SELECT content, status, priority FROM tasks WHERE parent_id=?",
                (task_id,),
            )
            subs = cursor.fetchall()
        lines = [f"## Task: {c}"]
        lines.append(f"- Priority: {pri}")
        lines.append(f"- Status: {status}")
        if due:
            lines.append(f"- Due: {due}")
        if tags:
            lines.append(f"- Tags: {tags}")
        if notes:
            lines.append(f"- Notes: {notes}")
        if spent:
            lines.append(f"- Time spent: {spent}s")
        if subs:
            lines.append("\n### Subtasks")
            for sc, ss, sp in subs:
                check = "[x]" if ss == "Completed" else "[ ]"
                lines.append(f"- {check} [{sp}] {sc}")
        return "\n".join(lines)

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
            from src.common.config import ASSETS_DIR

            icon_path = os.path.join(ASSETS_DIR, "chronos.png")

            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except ImportError:
            pass
        self.resize(1200, 900)

        self.view = QWebEngineView()
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

        # WebThemeBridge handles all theme injection (DocumentCreation + live updates)
        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(script_dir, "chronos_v4.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

        self.rem_timer = QTimer(self)
        self.rem_timer.timeout.connect(self._check_reminders)
        self.rem_timer.start(60000)
        self.last_hour = -1

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
