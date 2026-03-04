import contextlib
import os
import re
import sqlite3
import sys

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.common.config import APPDATA, ASSETS_DIR
from src.common.theme import ThemeManager, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

DB_PATH = os.path.join(APPDATA, "regex_sandbox.db")

_DEFAULT_PATTERNS = [
    ("Email Address", r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", 0, "test@example.com", "Regex"),
    ("URL (Simple)", r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", 0, "Check out https://google.com", "Regex"),
    ("IP Address (IPv4)", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 0, "Local: 127.0.0.1", "Regex"),
    ("Date (YYYY-MM-DD)", r"\d{4}-\d{2}-\d{2}", 0, "Today is 2024-05-20", "Regex"),
    ("Phone Number (US)", r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", 0, "Call (555) 123-4567", "Regex"),
]


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                pattern TEXT,
                flags INTEGER,
                test_string TEXT,
                mode TEXT DEFAULT 'Regex'
            )
        """)
        with contextlib.suppress(sqlite3.OperationalError):
            cursor.execute("ALTER TABLE patterns ADD COLUMN mode TEXT DEFAULT 'Regex'")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
        """)
        conn.commit()


def seed_defaults():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if cursor.execute("SELECT COUNT(*) FROM patterns").fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO patterns (name, pattern, flags, test_string, mode) VALUES (?, ?, ?, ?, ?)",
                _DEFAULT_PATTERNS,
            )
            conn.commit()


class FileSearchWorker(QThread):
    progress = pyqtSignal(int)
    results_found = pyqtSignal(list)
    finished = pyqtSignal(int)

    MAX_MATCHES = 2000
    BATCH_SIZE = 50

    def __init__(self, directory, pattern, extensions, flags):
        super().__init__()
        self.directory = directory
        self.pattern = pattern
        self.extensions = [e.strip().lower() for e in extensions.split(",") if e.strip()]
        self.flags = flags
        self._is_running = True

    def stop(self):
        self._is_running = False

    def _matches_extension(self, filename):
        return not self.extensions or any(filename.lower().endswith(e) for e in self.extensions)

    def run(self):
        try:
            regex = re.compile(self.pattern, self.flags)
        except re.error:
            self.finished.emit(0)
            return

        file_list = [
            os.path.join(root, f)
            for root, _, files in os.walk(self.directory)
            for f in files
            if self._matches_extension(f)
        ]
        total = len(file_list)
        match_count = 0
        batch = []

        for i, file_path in enumerate(file_list):
            if not self._is_running or match_count >= self.MAX_MATCHES:
                break
            try:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            batch.append((file_path, line_num, line.strip()))
                            match_count += 1
                            if len(batch) >= self.BATCH_SIZE:
                                self.results_found.emit(batch)
                                batch = []
                            if match_count >= self.MAX_MATCHES:
                                break
            except Exception:
                continue

            if total > 0:
                self.progress.emit(int((i / total) * 100))

        if batch:
            self.results_found.emit(batch)
        self.finished.emit(match_count)


class CodeGenDialog(QDialog):
    def __init__(self, parent, code_text, lang):
        super().__init__(parent)
        self.setWindowTitle(f"Generated {lang} Code")
        self.resize(700, 400)
        self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(code_text)
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont("Consolas", 11))
        layout.addWidget(self.editor)

        btn_copy = QPushButton("📋 Copy to Clipboard")
        btn_copy.setObjectName("accent_btn")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_and_close)
        layout.addWidget(btn_copy)

    def _copy_and_close(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        QMessageBox.information(self, "Copied", "Code copied to clipboard!")
        self.accept()


class RegexSandbox(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mgr = ThemeManager()
        init_db()
        seed_defaults()
        self.setWindowTitle("Regex Sandbox & Library | Offline Pattern Tester")

        icon_path = os.path.join(ASSETS_DIR, "regex_sandbox.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1100, 750)
        self.base_font = QFont("Segoe UI", 10)
        self.code_font = QFont("Consolas", 11)
        self.current_pattern_id = None
        self.search_thread = None

        self.eval_timer = QTimer()
        self.eval_timer.setSingleShot(True)
        self.eval_timer.timeout.connect(self.evaluate_regex)

        self.setup_ui()
        self.mgr.theme_changed.connect(self.apply_theme)
        self.load_patterns()
        self._theme_bridge = WindowThemeBridge(self.mgr, self, TOOL_SHEET)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_sidebar())
        main_layout.addWidget(self._build_content())

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("SAVED PATTERNS")
        title.setObjectName("section_title")
        layout.addWidget(title)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍 Filter patterns...")
        self.filter_input.textChanged.connect(self.filter_patterns)
        layout.addWidget(self.filter_input)

        self.pattern_list = QListWidget()
        self.pattern_list.itemClicked.connect(self.select_pattern)
        layout.addWidget(self.pattern_list)

        btn_save = QPushButton("💾 Save Current Pattern")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.save_pattern)
        layout.addWidget(btn_save)

        btn_del = QPushButton("🗑 Delete Selected")
        btn_del.setObjectName("danger_btn")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self.delete_pattern)
        layout.addWidget(btn_del)

        layout.addStretch()
        return sidebar

    def _build_content(self):
        wrapper = QWidget()
        wrapper.setObjectName("main_content")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        self.setup_sandbox_tab()
        self.setup_search_tab()
        self.setup_cheat_sheet_tab()
        return wrapper

    def setup_sandbox_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Pattern header
        header = QHBoxLayout()
        lbl = QLabel("PATTERN")
        lbl.setObjectName("section_title")
        header.addWidget(lbl)
        header.addStretch()

        lbl_mode = QLabel("Mode:")
        lbl_mode.setObjectName("mode_label")
        header.addWidget(lbl_mode)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Regex", "Wildcard (*, ?)", "Exact Match"])
        self.mode_combo.currentTextChanged.connect(self.trigger_evaluation)
        header.addWidget(self.mode_combo)
        layout.addLayout(header)

        self.regex_input = QLineEdit()
        self.regex_input.setFont(self.code_font)
        self.regex_input.setPlaceholderText("Enter your pattern here...")
        self.regex_input.textChanged.connect(self.trigger_evaluation)
        layout.addWidget(self.regex_input)

        # Flags
        flags_layout = QHBoxLayout()
        self.chk_ignorecase = QCheckBox("Ignore Case (i)")
        self.chk_multiline = QCheckBox("Multiline (m)")
        self.chk_dotall = QCheckBox("Dot All (s)")
        for chk in (self.chk_ignorecase, self.chk_multiline, self.chk_dotall):
            chk.stateChanged.connect(self.trigger_evaluation)
            flags_layout.addWidget(chk)
        flags_layout.addStretch()
        layout.addLayout(flags_layout)

        # Split: test string | match table
        split = QHBoxLayout()

        test_col = QVBoxLayout()
        lbl_target = QLabel("TEST STRING")
        lbl_target.setObjectName("section_title")
        test_col.addWidget(lbl_target)

        self.text_input = QTextEdit()
        self.text_input.setFont(self.code_font)
        self.text_input.setPlaceholderText("Paste the logs or data you want to test against here...")
        self.text_input.textChanged.connect(self.trigger_evaluation)
        test_col.addWidget(self.text_input)

        replace_row = QHBoxLayout()
        lbl_replace = QLabel("REPLACE WITH:")
        lbl_replace.setObjectName("mode_label")
        replace_row.addWidget(lbl_replace)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Optional: Replacement string...")
        self.replace_input.textChanged.connect(self.trigger_evaluation)
        replace_row.addWidget(self.replace_input)
        test_col.addLayout(replace_row)

        split.addLayout(test_col, 2)

        match_col = QVBoxLayout()
        lbl_groups = QLabel("GROUPS & MATCHES")
        lbl_groups.setObjectName("section_title")
        match_col.addWidget(lbl_groups)

        self.group_table = QTableWidget()
        self.group_table.setColumnCount(3)
        self.group_table.setHorizontalHeaderLabels(["#", "Content", "Range"])
        self.group_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.group_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.group_table.setShowGrid(False)
        self.group_table.itemClicked.connect(self.highlight_match_from_table)
        match_col.addWidget(self.group_table)

        split.addLayout(match_col, 1)
        layout.addLayout(split)

        self.replace_preview = QTextEdit()
        self.replace_preview.setReadOnly(True)
        self.replace_preview.setMaximumHeight(80)
        self.replace_preview.setPlaceholderText("Replacement preview will appear here...")
        self.replace_preview.setVisible(False)
        layout.addWidget(self.replace_preview)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status_label")
        self.status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.status_label)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("Generator:"))
        for label, slot in [("🐍 Python", self.generate_python), ("🟨 JavaScript", self.generate_javascript)]:
            btn = QPushButton(label)
            btn.setObjectName("accent_btn")
            btn.clicked.connect(slot)
            footer.addWidget(btn)
        footer.addStretch()
        layout.addLayout(footer)

        self.tabs.addTab(page, "Sandbox")

    def setup_search_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("SEARCH IN LOCAL FILES")
        header.setObjectName("section_title")
        layout.addWidget(header)

        ctrl = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select directory to search...")
        ctrl.addWidget(self.dir_input)

        btn_browse = QPushButton("📁 Browse")
        btn_browse.clicked.connect(self.browse_directory)
        ctrl.addWidget(btn_browse)

        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("Ext: .py, .txt, .js")
        self.ext_input.setFixedWidth(120)
        ctrl.addWidget(self.ext_input)

        self.btn_run_search = QPushButton("🔍 Find All")
        self.btn_run_search.setObjectName("accent_btn")
        self.btn_run_search.clicked.connect(self.start_file_search)
        ctrl.addWidget(self.btn_run_search)
        layout.addLayout(ctrl)

        self.file_results = QListWidget()
        self.file_results.itemDoubleClicked.connect(self.open_file_result)
        layout.addWidget(self.file_results)

        self.search_progress = QProgressBar()
        self.search_progress.setVisible(False)
        self.search_progress.setFixedHeight(4)
        self.search_progress.setTextVisible(False)
        layout.addWidget(self.search_progress)

        self.search_status = QLabel("Ready to search")
        self.search_status.setObjectName("status_label")
        layout.addWidget(self.search_status)

        self.tabs.addTab(page, "Find in Files")

    def setup_cheat_sheet_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)

        cheat_text = QTextEdit()
        cheat_text.setReadOnly(True)
        cheat_text.setHtml(r"""
            <h2 style='color:#3b82f6;'>Regex Quick Reference</h2>
            <table width='100%' cellpadding='5'>
                <tr style='background-color:rgba(59, 130, 246, 0.1);'><td><b>Pattern</b></td><td><b>Description</b></td></tr>
                <tr><td><code>.</code></td><td>Any character except newline</td></tr>
                <tr><td><code>*</code></td><td>0 or more repetitions</td></tr>
                <tr><td><code>+</code></td><td>1 or more repetitions</td></tr>
                <tr><td><code>?</code></td><td>0 or 1 repetition</td></tr>
                <tr><td><code>^</code></td><td>Start of string (or line in multiline)</td></tr>
                <tr><td><code>$</code></td><td>End of string (or line)</td></tr>
                <tr><td><code>\d</code></td><td>Any digit [0-9]</td></tr>
                <tr><td><code>\w</code></td><td>Any alphanumeric + underscore [a-zA-Z0-9_]</td></tr>
                <tr><td><code>\s</code></td><td>Any whitespace (space, tab, etc.)</td></tr>
                <tr><td><code>[...]</code></td><td>Set of characters</td></tr>
                <tr><td><code>(...)</code></td><td>Capture Group</td></tr>
                <tr><td><code>(?:...)</code></td><td>Non-capture Group</td></tr>
                <tr><td><code>|</code></td><td>Either or (logical OR)</td></tr>
                <tr><td><code>{n,m}</code></td><td>Between n and m repetitions</td></tr>
            </table>
            <br>
            <h2 style='color:#3b82f6;'>Lookarounds</h2>
            <table width='100%' cellpadding='5'>
                <tr><td><code>(?=...)</code></td><td>Positive Lookahead</td></tr>
                <tr><td><code>(?!...)</code></td><td>Negative Lookahead</td></tr>
                <tr><td><code>(?&lt;=...)</code></td><td>Positive Lookbehind</td></tr>
                <tr><td><code>(?&lt;!...)</code></td><td>Negative Lookbehind</td></tr>
            </table>
        """)
        layout.addWidget(cheat_text)
        self.tabs.addTab(page, "Cheat Sheet")

    def apply_theme(self):
        self.trigger_evaluation()

    def trigger_evaluation(self):
        self.eval_timer.start(250)

    def get_compiled_pattern_string(self):
        raw = self.regex_input.text()
        mode = self.mode_combo.currentText()
        if mode == "Wildcard (*, ?)":
            return re.escape(raw).replace(r"\*", ".*").replace(r"\?", ".")
        if mode == "Exact Match":
            return re.escape(raw)
        return raw

    def get_active_flags(self):
        flags = 0
        if self.chk_ignorecase.isChecked():
            flags |= re.IGNORECASE
        if self.chk_multiline.isChecked():
            flags |= re.MULTILINE
        if self.chk_dotall.isChecked():
            flags |= re.DOTALL
        return flags

    def evaluate_regex(self):
        raw_pattern = self.regex_input.text()
        test_str = self.text_input.toPlainText()

        saved_cursor = self.text_input.textCursor()
        saved_scroll = self.text_input.verticalScrollBar().value()
        self.text_input.blockSignals(True)

        # Reset formatting
        clear_cursor = self.text_input.textCursor()
        clear_cursor.select(QTextCursor.SelectionType.Document)
        default_fmt = QTextCharFormat()
        default_fmt.setForeground(QColor(self.mgr["text_primary"]))
        default_fmt.setBackground(Qt.GlobalColor.transparent)
        clear_cursor.setCharFormat(default_fmt)

        if not raw_pattern:
            self.status_label.setText("Ready")
            self.status_label.setStyleSheet(f"color: {self.mgr['text_secondary']};")
            self._restore_cursor(saved_cursor, saved_scroll)
            return

        try:
            pattern = re.compile(self.get_compiled_pattern_string(), self.get_active_flags())
            matches = list(pattern.finditer(test_str))

            self.group_table.setRowCount(0)
            highlight_fmt = QTextCharFormat()
            highlight_fmt.setBackground(QColor(self.mgr["accent"]))
            highlight_fmt.setForeground(QColor(self.mgr["text_on_accent"]))

            MAX_DISPLAY = 200
            for i, match in enumerate(matches[:MAX_DISPLAY]):
                if match.start() != match.end():
                    hc = self.text_input.textCursor()
                    hc.setPosition(match.start())
                    hc.setPosition(match.end(), QTextCursor.MoveMode.KeepAnchor)
                    hc.setCharFormat(highlight_fmt)

                row = self.group_table.rowCount()
                self.group_table.insertRow(row)
                self.group_table.setItem(row, 0, QTableWidgetItem(f"Match {i + 1}"))
                self.group_table.setItem(row, 1, QTableWidgetItem(match.group()))
                self.group_table.setItem(row, 2, QTableWidgetItem(f"{match.start()}-{match.end()}"))

                for g_idx, group in enumerate(match.groups(), 1):
                    row = self.group_table.rowCount()
                    self.group_table.insertRow(row)
                    self.group_table.setItem(row, 0, QTableWidgetItem(f"  └ Group {g_idx}"))
                    self.group_table.setItem(row, 1, QTableWidgetItem(str(group) if group is not None else "None"))
                    self.group_table.setItem(row, 2, QTableWidgetItem(f"{match.start(g_idx)}-{match.end(g_idx)}"))

            if len(matches) > MAX_DISPLAY:
                row = self.group_table.rowCount()
                self.group_table.insertRow(row)
                item = QTableWidgetItem(f"... and {len(matches) - MAX_DISPLAY} more")
                item.setForeground(QColor("#94a3b8"))
                self.group_table.setItem(row, 0, item)

            replace_str = self.replace_input.text()
            if replace_str:
                try:
                    self.replace_preview.setPlainText(pattern.sub(replace_str, test_str))
                    self.replace_preview.setVisible(True)
                except re.error as e:
                    self.replace_preview.setPlainText(f"Replacement Error: {e}")
                    self.replace_preview.setVisible(True)
            else:
                self.replace_preview.setVisible(False)

            count = len(matches)
            if count:
                self.status_label.setText(f"✅ Found {count} match{'es' if count > 1 else ''}!")
                self.status_label.setStyleSheet(f"color: {self.mgr['success']};")
            else:
                self.status_label.setText("❌ No matches found.")
                self.status_label.setStyleSheet(f"color: {self.mgr['text_secondary']};")

        except re.error as e:
            self.status_label.setText(f"⚠ Regex Error: {e.msg}")
            self.status_label.setStyleSheet(f"color: {self.mgr['danger']};")
            self.group_table.setRowCount(0)
            self.replace_preview.setVisible(False)

        self._restore_cursor(saved_cursor, saved_scroll)

    def _restore_cursor(self, cursor, scroll):
        self.text_input.setTextCursor(cursor)
        self.text_input.verticalScrollBar().setValue(scroll)
        self.text_input.blockSignals(False)

    def highlight_match_from_table(self, item):
        range_item = self.group_table.item(item.row(), 2)
        if not range_item or "-" not in range_item.text():
            return
        try:
            start, end = map(int, range_item.text().split("-"))
            cursor = self.text_input.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            self.text_input.setTextCursor(cursor)
            self.text_input.setFocus()
        except ValueError:
            pass

    def generate_python(self):
        pattern_str = self.get_compiled_pattern_string().replace("\\", "\\\\").replace('"', '\\"')
        raw_pattern = self.regex_input.text().replace('"', '\\"')
        mode = self.mode_combo.currentText()

        flags_list = []
        if self.chk_ignorecase.isChecked():
            flags_list.append("re.IGNORECASE")
        if self.chk_multiline.isChecked():
            flags_list.append("re.MULTILINE")
        if self.chk_dotall.isChecked():
            flags_list.append("re.DOTALL")
        flag_str = (", " + " | ".join(flags_list)) if flags_list else ""

        if mode == "Wildcard (*, ?)":
            comment = f"# Converted to Regex from Wildcard: {raw_pattern}"
        elif mode == "Exact Match":
            comment = f"# Escaped Literal Match for: {raw_pattern}"
        else:
            comment = "# Your Regex Pattern"

        body = self.text_input.toPlainText()
        snippet = body[:150] + ("..." if len(body) > 150 else "")
        tq = '"""'

        code = f"""import re

{comment}
regex = r"{pattern_str}"

# Your Target String
test_str = {tq}{snippet}{tq}

# Find Matches
matches = re.finditer(regex, test_str{flag_str})

for matchNum, match in enumerate(matches, start=1):
    print(f"Match {{matchNum}} found at {{match.start()}}-{{match.end()}}: {{match.group()}}")
    for groupNum in range(0, len(match.groups())):
        groupNum = groupNum + 1
        print(f"  Group {{groupNum}}: {{match.group(groupNum)}}")
"""
        CodeGenDialog(self, code, "Python").exec()

    def generate_javascript(self):
        pattern_str = self.get_compiled_pattern_string().replace("/", "\\/")
        raw_pattern = self.regex_input.text()
        mode = self.mode_combo.currentText()

        js_flags = "g"
        if self.chk_ignorecase.isChecked():
            js_flags += "i"
        if self.chk_multiline.isChecked():
            js_flags += "m"
        if self.chk_dotall.isChecked():
            js_flags += "s"

        if mode == "Wildcard (*, ?)":
            comment = f"// Converted to Regex from Wildcard: {raw_pattern}"
        elif mode == "Exact Match":
            comment = f"// Escaped Literal Match for: {raw_pattern}"
        else:
            comment = "// Your Regex Pattern"

        body = self.text_input.toPlainText()
        snippet = body[:150].replace("`", "\\`") + ("..." if len(body) > 150 else "")

        code = f"""{comment}
const regex = /{pattern_str}/{js_flags};

// Your Target String
const str = `{snippet}`;

let m;
while ((m = regex.exec(str)) !== null) {{
    if (m.index === regex.lastIndex) {{
        regex.lastIndex++;
    }}
    m.forEach((match, groupIndex) => {{
        console.log(`Found match, group ${{groupIndex}}: ${{match}}`);
    }});
}}
"""
        CodeGenDialog(self, code, "JavaScript").exec()

    def browse_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            self.dir_input.setText(path)

    def start_file_search(self):
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.stop()
            self.btn_run_search.setText("🔍 Find All")
            return

        dir_path = self.dir_input.text()
        pattern = self.get_compiled_pattern_string()

        if not dir_path or not os.path.exists(dir_path):
            QMessageBox.warning(self, "Invalid Path", "Please select a valid directory.")
            return
        if not pattern:
            QMessageBox.warning(self, "No Pattern", "Please enter a regex pattern.")
            return

        self.file_results.clear()
        self.search_progress.setVisible(True)
        self.search_progress.setValue(0)
        self.btn_run_search.setText("🛑 Stop")
        self.search_status.setText("Searching...")

        self.search_thread = FileSearchWorker(dir_path, pattern, self.ext_input.text(), self.get_active_flags())
        self.search_thread.progress.connect(self.search_progress.setValue)
        self.search_thread.results_found.connect(self.add_search_results)
        self.search_thread.finished.connect(self.search_finished)
        self.search_thread.start()

    def add_search_results(self, results):
        for file_path, line_num, content in results:
            item = QListWidgetItem(f"{os.path.basename(file_path)}:{line_num} | {content}")
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            item.setToolTip(file_path)
            self.file_results.addItem(item)

    def search_finished(self, match_count):
        self.search_progress.setVisible(False)
        self.btn_run_search.setText("🔍 Find All")
        self.search_status.setText(f"Search complete. Found {match_count} matches.")

    def open_file_result(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if os.path.exists(file_path):
            os.startfile(file_path)

    def load_patterns(self):
        self.pattern_list.clear()
        with sqlite3.connect(DB_PATH) as conn:
            for row in conn.execute("SELECT id, name, pattern, flags, test_string, mode FROM patterns ORDER BY name ASC"):
                item = QListWidgetItem(row[1])
                item.setData(Qt.ItemDataRole.UserRole, {
                    "id": row[0], "pattern": row[2],
                    "flags": row[3], "test_string": row[4],
                    "mode": row[5] or "Regex",
                })
                self.pattern_list.addItem(item)

    def select_pattern(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.current_pattern_id = data["id"]

        widgets = [self.regex_input, self.mode_combo, self.chk_ignorecase, self.chk_multiline, self.chk_dotall]
        for w in widgets:
            w.blockSignals(True)

        self.mode_combo.setCurrentText(data.get("mode", "Regex"))
        self.regex_input.setText(data["pattern"])
        self.text_input.setPlainText(data["test_string"])
        self.replace_input.clear()

        flags = data["flags"]
        self.chk_ignorecase.setChecked(bool(flags & re.IGNORECASE))
        self.chk_multiline.setChecked(bool(flags & re.MULTILINE))
        self.chk_dotall.setChecked(bool(flags & re.DOTALL))

        for w in widgets:
            w.blockSignals(False)

        self.trigger_evaluation()

    def save_pattern(self):
        name, ok = QInputDialog.getText(self, "Save Pattern", "Enter a name for this regex pattern:")
        if not ok or not name.strip():
            return
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO patterns (name, pattern, flags, test_string, mode) VALUES (?, ?, ?, ?, ?)",
                (name.strip(), self.regex_input.text(), self.get_active_flags(),
                 self.text_input.toPlainText(), self.mode_combo.currentText()),
            )
            conn.commit()
        self.load_patterns()
        QMessageBox.information(self, "Saved", "Pattern saved to local library successfully.")

    def delete_pattern(self):
        item = self.pattern_list.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Confirm Delete", f"Delete '{item.text()}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM patterns WHERE id=?", (data["id"],))
                conn.commit()
            self.load_patterns()

    def filter_patterns(self):
        query = self.filter_input.text().lower()
        for i in range(self.pattern_list.count()):
            item = self.pattern_list.item(i)
            item.setHidden(query not in item.text().lower())


def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.regexhelper")
    app = QApplication(sys.argv)
    window = RegexSandbox()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
