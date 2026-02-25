import sys
import os
import re
import sqlite3
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QTextEdit,
    QFrame,
    QMessageBox,
    QInputDialog,
    QCheckBox,
    QDialog,
    QPlainTextEdit,
    QComboBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor

# --- CONFIGURATION & DATABASE ---
DB_PATH = os.path.join(os.getenv("APPDATA", "."), "regex_sandbox.db")


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
        # Safe migration if updating from an older version of the app
        try:
            cursor.execute("ALTER TABLE patterns ADD COLUMN mode TEXT DEFAULT 'Regex'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


def seed_defaults():
    defaults = [
        (
            "Email Address",
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            0,
            "test@example.com",
            "Regex",
        ),
        (
            "URL (Simple)",
            r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+",
            0,
            "Check out https://google.com",
            "Regex",
        ),
        (
            "IP Address (IPv4)",
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            0,
            "Local: 127.0.0.1",
            "Regex",
        ),
        (
            "Date (YYYY-MM-DD)",
            r"\d{4}-\d{2}-\d{2}",
            0,
            "Today is 2024-05-20",
            "Regex",
        ),
        (
            "Phone Number (US)",
            r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
            0,
            "Call (555) 123-4567",
            "Regex",
        ),
    ]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM patterns")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO patterns (name, pattern, flags, test_string, mode) VALUES (?, ?, ?, ?, ?)",
                defaults,
            )
            conn.commit()


# --- BACKGROUND WORKERS ---
class FileSearchWorker(QThread):
    progress = pyqtSignal(int)
    results_found = pyqtSignal(list)  # Batch of matches (file_path, line_num, content)
    finished = pyqtSignal(int)

    def __init__(self, directory, pattern, extensions, flags):
        super().__init__()
        self.directory = directory
        self.pattern = pattern
        self.extensions = [
            e.strip().lower() for e in extensions.split(",") if e.strip()
        ]
        self.flags = flags
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        match_count = 0
        MAX_TOTAL_MATCHES = 2000
        try:
            regex = re.compile(self.pattern, self.flags)
        except re.error:
            self.finished.emit(0)
            return

        file_list = []
        for root, _, files in os.walk(self.directory):
            if not self._is_running:
                break
            for f in files:
                if not self.extensions or any(
                    f.lower().endswith(ext) for ext in self.extensions
                ):
                    file_list.append(os.path.join(root, f))

        total_files = len(file_list)
        batch = []

        for i, file_path in enumerate(file_list):
            if not self._is_running or match_count >= MAX_TOTAL_MATCHES:
                break

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            batch.append((file_path, line_num, line.strip()))
                            match_count += 1

                            if len(batch) >= 50:
                                self.results_found.emit(batch)
                                batch = []

                            if match_count >= MAX_TOTAL_MATCHES:
                                break
            except Exception:
                continue

            if total_files > 0:
                self.progress.emit(int((i / total_files) * 100))

        if batch:
            self.results_found.emit(batch)
        self.finished.emit(match_count)


# --- CODE GENERATION DIALOG ---
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
        btn_copy.clicked.connect(self.copy_to_clipboard)
        layout.addWidget(btn_copy)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        QMessageBox.information(self, "Copied", "Code copied to clipboard!")
        self.accept()


# --- MAIN UI ---
class RegexSandbox(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        seed_defaults()
        self.setWindowTitle("Regex Sandbox & Library | Offline Pattern Tester")
        self.resize(1100, 750)

        self.base_font = QFont("Segoe UI", 10)
        self.code_font = QFont("Consolas", 11)
        self.current_pattern_id = None
        self.dark_mode = True  # Default

        self.load_settings()
        self.setup_ui()
        self.apply_theme()
        self.load_patterns()

        # Debounce timer to prevent lag when typing huge strings
        self.eval_timer = QTimer()
        self.eval_timer.setSingleShot(True)
        self.eval_timer.timeout.connect(self.evaluate_regex)

        # File search worker
        self.search_thread = None

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- LEFT SIDEBAR (LIBRARY) ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(15)

        title = QLabel("SAVED PATTERNS")
        title.setObjectName("section_title")
        sidebar_layout.addWidget(title)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍 Filter patterns...")
        self.filter_input.textChanged.connect(self.filter_patterns)
        sidebar_layout.addWidget(self.filter_input)

        self.pattern_list = QListWidget()
        self.pattern_list.itemClicked.connect(self.select_pattern)
        sidebar_layout.addWidget(self.pattern_list)

        btn_save = QPushButton("💾 Save Current Pattern")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.save_pattern)
        sidebar_layout.addWidget(btn_save)

        btn_del = QPushButton("🗑 Delete Selected")
        btn_del.setObjectName("danger_btn")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self.delete_pattern)
        sidebar_layout.addWidget(btn_del)

        sidebar_layout.addStretch()

        self.btn_theme = QPushButton("☀️ Light Mode")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme)

        # --- MAIN CONTENT AREA ---
        content_wrapper = QWidget()
        content_wrapper.setObjectName("main_content")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(0)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        content_layout.addWidget(self.tabs)

        # Tab 1: Sandbox (Main Tester)
        self.setup_sandbox_tab()

        # Tab 2: Find in Files
        self.setup_search_tab()

        # Tab 3: Cheat Sheet
        self.setup_cheat_sheet_tab()

        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_wrapper)

    def setup_sandbox_tab(self):
        sandbox_page = QWidget()
        layout = QVBoxLayout(sandbox_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Pattern Header with Mode Switch
        header_layout = QHBoxLayout()
        lbl_regex = QLabel("PATTERN")
        lbl_regex.setObjectName("section_title")
        header_layout.addWidget(lbl_regex)

        header_layout.addStretch()

        lbl_mode = QLabel("Mode:")
        lbl_mode.setObjectName("mode_label")
        header_layout.addWidget(lbl_mode)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Regex", "Wildcard (*, ?)", "Exact Match"])
        self.mode_combo.currentTextChanged.connect(self.trigger_evaluation)
        header_layout.addWidget(self.mode_combo)

        layout.addLayout(header_layout)

        self.regex_input = QLineEdit()
        self.regex_input.setFont(self.code_font)
        self.regex_input.setPlaceholderText("Enter your pattern here...")
        self.regex_input.textChanged.connect(self.trigger_evaluation)
        layout.addWidget(self.regex_input)

        # Flags layout
        flags_layout = QHBoxLayout()
        self.chk_ignorecase = QCheckBox("Ignore Case (i)")
        self.chk_multiline = QCheckBox("Multiline (m)")
        self.chk_dotall = QCheckBox("Dot All (s)")

        for chk in [self.chk_ignorecase, self.chk_multiline, self.chk_dotall]:
            chk.stateChanged.connect(self.trigger_evaluation)
            flags_layout.addWidget(chk)
        flags_layout.addStretch()
        layout.addLayout(flags_layout)

        # Split for Test String & Matches
        split_layout = QHBoxLayout()

        # Test String Column
        test_col = QVBoxLayout()
        lbl_target = QLabel("TEST STRING")
        lbl_target.setObjectName("section_title")
        test_col.addWidget(lbl_target)

        self.text_input = QTextEdit()
        self.text_input.setFont(self.code_font)
        self.text_input.setPlaceholderText(
            "Paste the logs or data you want to test against here..."
        )
        self.text_input.textChanged.connect(self.trigger_evaluation)
        test_col.addWidget(self.text_input)

        # Replacement Field (Optional)
        replace_layout = QHBoxLayout()
        lbl_replace = QLabel("REPLACE WITH:")
        lbl_replace.setObjectName("mode_label")
        replace_layout.addWidget(lbl_replace)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Optional: Replacement string...")
        self.replace_input.textChanged.connect(self.trigger_evaluation)
        replace_layout.addWidget(self.replace_input)
        test_col.addLayout(replace_layout)

        split_layout.addLayout(test_col, 2)

        # Groups / Matches Table Column
        match_col = QVBoxLayout()
        lbl_groups = QLabel("GROUPS & MATCHES")
        lbl_groups.setObjectName("section_title")
        match_col.addWidget(lbl_groups)

        self.group_table = QTableWidget()
        self.group_table.setColumnCount(3)
        self.group_table.setHorizontalHeaderLabels(["#", "Content", "Range"])
        self.group_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.group_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.group_table.setShowGrid(False)
        self.group_table.itemClicked.connect(self.highlight_match_from_table)
        match_col.addWidget(self.group_table)

        split_layout.addLayout(match_col, 1)
        layout.addLayout(split_layout)

        # Replacement Result Preview
        self.replace_preview = QTextEdit()
        self.replace_preview.setReadOnly(True)
        self.replace_preview.setMaximumHeight(80)
        self.replace_preview.setPlaceholderText(
            "Replacement preview will appear here..."
        )
        self.replace_preview.setVisible(False)
        layout.addWidget(self.replace_preview)

        # Match Info
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status_label")
        self.status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.status_label)

        # Code Gen Footer
        footer_layout = QHBoxLayout()
        footer_layout.addWidget(QLabel("Generator:"))

        btn_gen_py = QPushButton("🐍 Python")
        btn_gen_py.setObjectName("accent_btn")
        btn_gen_py.clicked.connect(self.generate_python)
        footer_layout.addWidget(btn_gen_py)

        btn_gen_js = QPushButton("🟨 JavaScript")
        btn_gen_js.setObjectName("accent_btn")
        btn_gen_js.clicked.connect(self.generate_javascript)
        footer_layout.addWidget(btn_gen_js)

        footer_layout.addStretch()
        layout.addLayout(footer_layout)

        self.tabs.addTab(sandbox_page, "Sandbox")

    def setup_search_tab(self):
        search_page = QWidget()
        layout = QVBoxLayout(search_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel("SEARCH IN LOCAL FILES")
        header.setObjectName("section_title")
        layout.addWidget(header)

        # Search Controls
        ctrl_layout = QHBoxLayout()

        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select directory to search...")
        ctrl_layout.addWidget(self.dir_input)

        btn_browse = QPushButton("📁 Browse")
        btn_browse.clicked.connect(self.browse_directory)
        ctrl_layout.addWidget(btn_browse)

        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("Ext: .py, .txt, .js")
        self.ext_input.setFixedWidth(120)
        ctrl_layout.addWidget(self.ext_input)

        self.btn_run_search = QPushButton("🔍 Find All")
        self.btn_run_search.setObjectName("accent_btn")
        self.btn_run_search.clicked.connect(self.start_file_search)
        ctrl_layout.addWidget(self.btn_run_search)

        layout.addLayout(ctrl_layout)

        # Results List
        self.file_results = QListWidget()
        self.file_results.itemDoubleClicked.connect(self.open_file_result)
        layout.addWidget(self.file_results)

        # Progress Bar
        self.search_progress = QProgressBar()
        self.search_progress.setVisible(False)
        self.search_progress.setFixedHeight(4)
        self.search_progress.setTextVisible(False)
        layout.addWidget(self.search_progress)

        self.search_status = QLabel("Ready to search")
        self.search_status.setObjectName("status_label")
        layout.addWidget(self.search_status)

        self.tabs.addTab(search_page, "Find in Files")

    def setup_cheat_sheet_tab(self):
        cheat_page = QWidget()
        layout = QVBoxLayout(cheat_page)
        layout.setContentsMargins(20, 20, 20, 20)

        cheat_text = QTextEdit()
        cheat_text.setReadOnly(True)
        cheat_text.setHtml("""
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
        self.tabs.addTab(cheat_page, "Cheat Sheet")

    def load_settings(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key='theme'")
            res = cursor.fetchone()
            if res:
                self.dark_mode = res[0] == "dark"

    def save_settings(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings VALUES (?, ?)",
                ("theme", "dark" if self.dark_mode else "light"),
            )
            conn.commit()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        self.save_settings()
        self.trigger_evaluation()  # Re-evaluate to update text highlights

    def apply_theme(self):
        if self.dark_mode:
            self.btn_theme.setText("☀️ Light Mode")
            self.highlight_bg = "#2563eb"
            self.highlight_fg = "#ffffff"
            self.setStyleSheet("""
                QMainWindow { background-color: #0b0e14; }
                QWidget { background-color: #0b0e14; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; }
                
                QFrame#sidebar { 
                    background-color: #121620; 
                    border-right: 1px solid #1e293b; 
                }
                
                QLabel#section_title { color: #94a3b8; font-weight: bold; font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px; margin-top: 10px; }
                QLabel#mode_label { color: #94a3b8; }
                
                QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { 
                    background-color: #1a1f2e; 
                    border: 1px solid #334155; 
                    padding: 12px; 
                    border-radius: 8px; 
                    color: #ffffff;
                    font-size: 13px;
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #3b82f6; background-color: #0f172a; }
                QComboBox::drop-down { border: none; }
                
                QCheckBox { color: #94a3b8; spacing: 8px; }
                QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1.5px solid #334155; background-color: #0f172a; }
                QCheckBox::indicator:checked { background-color: #3b82f6; border: 1.5px solid #3b82f6; }
                
                QPushButton { 
                    background-color: #1e293b; 
                    border: 1px solid #334155; 
                    padding: 8px 12px; 
                    border-radius: 6px; 
                    font-weight: 600; 
                    color: #f8fafc;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #334155; border: 1px solid #475569; }
                QPushButton:pressed { background-color: #0f172a; }
                
                QPushButton#accent_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); 
                    color: white; 
                    border: none;
                    font-size: 12px;
                }
                QPushButton#accent_btn:hover { background: #3b82f6; }
                
                QPushButton#danger_btn { 
                    background-color: rgba(239, 68, 68, 0.1); 
                    color: #f87171; 
                    border: 1px solid rgba(239, 68, 68, 0.2); 
                }
                QPushButton#danger_btn:hover { background-color: rgba(239, 68, 68, 0.2); }

                QListWidget { 
                    background-color: transparent; 
                    border: none; 
                    outline: none; 
                }
                QListWidget::item { 
                    background-color: #1a1f2e;
                    padding: 6px 10px; 
                    border-radius: 5px; 
                    margin-bottom: 3px; 
                    border: 1px solid transparent;
                }
                QListWidget::item:hover { background-color: #242b3d; border: 1px solid #334155; }
                QListWidget::item:selected { background-color: #1e293b; color: #3b82f6; border: 1px solid #3b82f6; }
                
                QTabWidget::pane { border: 1px solid #1e293b; top: -1px; background-color: #0b0e14; }
                QTabBar::tab { background: #121620; border: 1px solid #1e293b; padding: 10px 25px; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; color: #94a3b8; font-weight: bold; margin-right: 2px; }
                QTabBar::tab:selected { background: #0b0e14; color: #3b82f6; border-bottom: 2px solid #3b82f6; }
                QTabBar::tab:hover { background: #1a1f2e; }

                QTableWidget { background-color: #1a1f2e; border: 1px solid #334155; border-radius: 8px; color: #ffffff; gridline-color: transparent; outline: none; }
                QHeaderView::section { background-color: #121620; padding: 8px; border: none; font-weight: bold; color: #94a3b8; border-bottom: 1px solid #334155; }
                QTableWidget::item { padding: 5px; }
                QTableWidget::item:selected { background-color: #2563eb; color: white; }

                QProgressBar { background-color: #1a1f2e; border: none; border-radius: 2px; }
                QProgressBar::chunk { background-color: #3b82f6; border-radius: 2px; }

                QScrollBar:vertical { 
                    border: none; background: transparent; 
                    width: 4px; margin: 0px;
                }
                QScrollBar::handle:vertical { 
                    background: #334155; border-radius: 2px; min-height: 40px; 
                }
                QScrollBar::handle:vertical:hover { background: #475569; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            """)
        else:
            self.btn_theme.setText("🌙 Dark Mode")
            self.highlight_bg = "#bfdbfe"
            self.highlight_fg = "#1e3a8a"
            self.setStyleSheet("""
                QMainWindow { background-color: #f8fafc; }
                QWidget { background-color: #f8fafc; color: #1e293b; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; }
                
                QFrame#sidebar { 
                    background-color: #ffffff; 
                    border-right: 1px solid #e2e8f0; 
                }
                
                QLabel#section_title { color: #64748b; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-top: 10px; }
                QLabel#mode_label { color: #64748b; }
                
                QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { 
                    background-color: #ffffff; 
                    border: 1px solid #e2e8f0; 
                    padding: 12px; 
                    border-radius: 8px; 
                    color: #1e293b;
                    font-size: 14px;
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #3b82f6; background-color: #f1f5f9; }
                QComboBox::drop-down { border: none; }
                
                QCheckBox { color: #64748b; spacing: 8px; }
                QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1.5px solid #cbd5e1; background-color: #ffffff; }
                QCheckBox::indicator:checked { background-color: #3b82f6; border: 1.5px solid #3b82f6; }
                
                QPushButton { 
                    background-color: #f1f5f9; 
                    border: 1px solid #e2e8f0; 
                    padding: 8px 12px; 
                    border-radius: 6px; 
                    font-weight: 600; 
                    color: #475569;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #e2e8f0; border: 1px solid #cbd5e1; }
                QPushButton:pressed { background-color: #cbd5e1; }
                
                QPushButton#accent_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); 
                    color: white; 
                    border: none;
                }
                QPushButton#accent_btn:hover { background: #1d4ed8; }
                
                QPushButton#danger_btn { 
                    background-color: #fef2f2; 
                    color: #ef4444; 
                    border: 1px solid #fee2e2; 
                }
                QPushButton#danger_btn:hover { background-color: #fee2e2; }

                QListWidget { 
                    background-color: transparent; 
                    border: none; 
                    outline: none; 
                }
                QListWidget::item { 
                    background-color: #ffffff;
                    padding: 6px 10px; 
                    border-radius: 6px; 
                    margin-bottom: 4px; 
                    border: 1px solid #f1f5f9;
                }
                QListWidget::item:hover { background-color: #f1f5f9; border: 1px solid #e2e8f0; }
                QListWidget::item:selected { background-color: #eff6ff; color: #2563eb; border: 1px solid #3b82f6; }
                
                QTabWidget::pane { border: 1px solid #e2e8f0; top: -1px; background-color: #f8fafc; }
                QTabBar::tab { background: #f1f5f9; border: 1px solid #e2e8f0; padding: 10px 25px; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; color: #64748b; font-weight: bold; margin-right: 2px; }
                QTabBar::tab:selected { background: #f8fafc; color: #2563eb; border-bottom: 2px solid #2563eb; }
                
                QTableWidget { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b; gridline-color: transparent; }
                QHeaderView::section { background-color: #f1f5f9; padding: 8px; border: none; font-weight: bold; color: #64748b; border-bottom: 1px solid #e2e8f0; }

                QProgressBar { background-color: #e2e8f0; border: none; border-radius: 2px; }
                QProgressBar::chunk { background-color: #3b82f6; border-radius: 2px; }

                QScrollBar:vertical { 
                    border: none; background: rgba(0,0,0,0.03); 
                    width: 4px; border-radius: 2px;
                }
                QScrollBar::handle:vertical { 
                    background: #e2e8f0; border-radius: 2px; min-height: 30px; 
                }
                QScrollBar::handle:vertical:hover { background: #cbd5e1; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            """)

    # --- REGEX EVALUATION ---
    def trigger_evaluation(self):
        # Debounce the text change so it doesn't freeze on massive logs
        self.eval_timer.start(250)

    def get_compiled_pattern_string(self):
        """Converts the user input into a valid regex string based on the selected mode"""
        raw_pattern = self.regex_input.text()
        mode = self.mode_combo.currentText()

        if mode == "Wildcard (*, ?)":
            # Escape regex specials, then unescape the wildcards to regex equivalents
            return re.escape(raw_pattern).replace(r"\*", ".*").replace(r"\?", ".")
        elif mode == "Exact Match":
            # Escape everything so it matches exactly
            return re.escape(raw_pattern)

        # Default Regex mode
        return raw_pattern

    def evaluate_regex(self):
        raw_pattern = self.regex_input.text()
        test_str = self.text_input.toPlainText()

        # Save user's cursor position and scrollbar to prevent jumping
        cursor = self.text_input.textCursor()
        v_scroll = self.text_input.verticalScrollBar().value()

        # Block signals to prevent infinite recursive loop from formatting changes
        self.text_input.blockSignals(True)

        # Reset formatting based on current theme
        clear_cursor = self.text_input.textCursor()
        clear_cursor.select(QTextCursor.SelectionType.Document)
        default_format = QTextCharFormat()

        text_color = "#e2e8f0" if self.dark_mode else "#1e293b"
        muted_color = "#94a3b8" if self.dark_mode else "#64748b"
        success_color = "#22c55e"
        danger_color = "#ef4444"

        default_format.setForeground(QColor(text_color))
        default_format.setBackground(Qt.GlobalColor.transparent)
        clear_cursor.setCharFormat(default_format)

        if not raw_pattern:
            self.status_label.setText("Ready")
            self.status_label.setStyleSheet(f"color: {muted_color};")
            self.restore_cursor(cursor, v_scroll)
            return

        flags = self.get_active_flags()
        compiled_str = self.get_compiled_pattern_string()

        try:
            compiled_pattern = re.compile(compiled_str, flags)
            matches = list(compiled_pattern.finditer(test_str))

            # --- Update Table & Highlighting ---
            self.group_table.setRowCount(0)
            highlight_format = QTextCharFormat()
            highlight_format.setBackground(QColor(self.highlight_bg))
            highlight_format.setForeground(QColor(self.highlight_fg))

            MAX_DISPLAY_MATCHES = 200
            for i, match in enumerate(matches):
                if i >= MAX_DISPLAY_MATCHES:
                    break

                # Highlighting
                if match.start() != match.end():
                    hc = self.text_input.textCursor()
                    hc.setPosition(match.start())
                    hc.setPosition(match.end(), QTextCursor.MoveMode.KeepAnchor)
                    hc.setCharFormat(highlight_format)

                # Add main match to table
                row = self.group_table.rowCount()
                self.group_table.insertRow(row)
                self.group_table.setItem(row, 0, QTableWidgetItem(f"Match {i + 1}"))
                self.group_table.setItem(row, 1, QTableWidgetItem(match.group()))
                self.group_table.setItem(
                    row, 2, QTableWidgetItem(f"{match.start()}-{match.end()}")
                )

                # Add groups to table
                for g_idx, group in enumerate(match.groups(), 1):
                    row = self.group_table.rowCount()
                    self.group_table.insertRow(row)
                    self.group_table.setItem(
                        row, 0, QTableWidgetItem(f"  └ Group {g_idx}")
                    )
                    self.group_table.setItem(
                        row,
                        1,
                        QTableWidgetItem(str(group) if group is not None else "None"),
                    )
                    self.group_table.setItem(
                        row,
                        2,
                        QTableWidgetItem(f"{match.start(g_idx)}-{match.end(g_idx)}"),
                    )

            match_count = len(matches)
            if match_count > MAX_DISPLAY_MATCHES:
                row = self.group_table.rowCount()
                self.group_table.insertRow(row)
                item = QTableWidgetItem(
                    f"... and {match_count - MAX_DISPLAY_MATCHES} more"
                )
                item.setForeground(QColor("#94a3b8"))
                self.group_table.setItem(row, 0, item)

            # --- Replacement Preview ---
            replace_str = self.replace_input.text()
            if replace_str:
                try:
                    res = compiled_pattern.sub(replace_str, test_str)
                    self.replace_preview.setPlainText(res)
                    self.replace_preview.setVisible(True)
                except re.error as re_err:
                    self.replace_preview.setPlainText(f"Replacement Error: {re_err}")
                    self.replace_preview.setVisible(True)
            else:
                self.replace_preview.setVisible(False)

            match_count = len(matches)
            if match_count > 0:
                self.status_label.setText(
                    f"✅ Found {match_count} match{'es' if match_count > 1 else ''}!"
                )
                self.status_label.setStyleSheet(f"color: {success_color};")
            else:
                self.status_label.setText("❌ No matches found.")
                self.status_label.setStyleSheet(f"color: {muted_color};")

        except re.error as e:
            self.status_label.setText(f"⚠ Regex Error: {e.msg}")
            self.status_label.setStyleSheet(f"color: {danger_color};")
            self.group_table.setRowCount(0)
            self.replace_preview.setVisible(False)

        self.restore_cursor(cursor, v_scroll)

    def restore_cursor(self, cursor, v_scroll):
        self.text_input.setTextCursor(cursor)
        self.text_input.verticalScrollBar().setValue(v_scroll)
        self.text_input.blockSignals(False)

    def highlight_match_from_table(self, item):
        row = item.row()
        range_item = self.group_table.item(row, 2)
        if not range_item:
            return
        range_text = range_item.text()
        if "-" in range_text:
            try:
                start, end = map(int, range_text.split("-"))
                cursor = self.text_input.textCursor()
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                self.text_input.setTextCursor(cursor)
                self.text_input.setFocus()
            except ValueError:
                pass

    def get_active_flags(self):
        flags = 0
        if self.chk_ignorecase.isChecked():
            flags |= re.IGNORECASE
        if self.chk_multiline.isChecked():
            flags |= re.MULTILINE
        if self.chk_dotall.isChecked():
            flags |= re.DOTALL
        return flags

    # --- CODE GENERATION ---
    def generate_python(self):
        pattern_str = (
            self.get_compiled_pattern_string().replace("\\", "\\\\").replace('"', '\\"')
        )
        raw_pattern = self.regex_input.text().replace('"', '\\"')
        mode = self.mode_combo.currentText()

        flags_list = []
        if self.chk_ignorecase.isChecked():
            flags_list.append("re.IGNORECASE")
        if self.chk_multiline.isChecked():
            flags_list.append("re.MULTILINE")
        if self.chk_dotall.isChecked():
            flags_list.append("re.DOTALL")
        flag_str = ", " + " | ".join(flags_list) if flags_list else ""

        comment = "# Your Regex Pattern"
        if mode == "Wildcard (*, ?)":
            comment = f"# Converted to Regex from Wildcard: {raw_pattern}"
        elif mode == "Exact Match":
            comment = f"# Escaped Literal Match for: {raw_pattern}"

        code = f"""import re

{comment}
regex = r"{pattern_str}"

# Your Target String
test_str = \"\"\"{self.text_input.toPlainText()[:150]}{"..." if len(self.text_input.toPlainText()) > 150 else ""}\"\"\"

# Find Matches
matches = re.finditer(regex, test_str{flag_str})

for matchNum, match in enumerate(matches, start=1):
    print(f"Match {{matchNum}} found at {{match.start()}}-{{match.end()}}: {{match.group()}}")
    
    # Iterate through capture groups
    for groupNum in range(0, len(match.groups())):
        groupNum = groupNum + 1
        print(f"  Group {{groupNum}}: {{match.group(groupNum)}}")
"""
        dialog = CodeGenDialog(self, code, "Python")
        dialog.exec()

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

        comment = "// Your Regex Pattern"
        if mode == "Wildcard (*, ?)":
            comment = f"// Converted to Regex from Wildcard: {raw_pattern}"
        elif mode == "Exact Match":
            comment = f"// Escaped Literal Match for: {raw_pattern}"

        code = f"""{comment}
const regex = /{pattern_str}/{js_flags};

// Your Target String
const str = `{self.text_input.toPlainText()[:150].replace("`", "\\`")}{"..." if len(self.text_input.toPlainText()) > 150 else ""}`;

let m;

while ((m = regex.exec(str)) !== null) {{
    // Prevent infinite loops with zero-width matches
    if (m.index === regex.lastIndex) {{
        regex.lastIndex++;
    }}
    
    // The result can be accessed through the `m`-variable.
    m.forEach((match, groupIndex) => {{
        console.log(`Found match, group ${{groupIndex}}: ${{match}}`);
    }});
}}
"""
        dialog = CodeGenDialog(self, code, "JavaScript")
        dialog.exec()

    # --- FILE SEARCH LOGIC ---
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
        exts = self.ext_input.text()
        flags = self.get_active_flags()

        if not dir_path or not os.path.exists(dir_path):
            QMessageBox.warning(
                self, "Invalid Path", "Please select a valid directory."
            )
            return

        if not pattern:
            QMessageBox.warning(self, "No Pattern", "Please enter a regex pattern.")
            return

        self.file_results.clear()
        self.search_progress.setVisible(True)
        self.search_progress.setValue(0)
        self.btn_run_search.setText("🛑 Stop")
        self.search_status.setText("Searching...")

        self.search_thread = FileSearchWorker(dir_path, pattern, exts, flags)
        self.search_thread.progress.connect(self.search_progress.setValue)
        self.search_thread.results_found.connect(self.add_search_results)
        self.search_thread.finished.connect(self.search_finished)
        self.search_thread.start()

    def add_search_results(self, results):
        for file_path, line_num, content in results:
            item = QListWidgetItem(
                f"{os.path.basename(file_path)}:{line_num} | {content}"
            )
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

    # --- DATABASE/LIBRARY LOGIC ---
    def load_patterns(self):
        self.pattern_list.clear()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Fetch mode safely if it exists
            for row in cursor.execute(
                "SELECT id, name, pattern, flags, test_string, mode FROM patterns ORDER BY name ASC"
            ):
                item = QListWidgetItem(row[1])
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    {
                        "id": row[0],
                        "pattern": row[2],
                        "flags": row[3],
                        "test_string": row[4],
                        "mode": row[5] or "Regex",
                    },
                )
                self.pattern_list.addItem(item)

    def select_pattern(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.current_pattern_id = data["id"]

        # Block signals temporarily to prevent early evaluations before UI sets up
        self.regex_input.blockSignals(True)
        self.mode_combo.blockSignals(True)
        self.chk_ignorecase.blockSignals(True)
        self.chk_multiline.blockSignals(True)
        self.chk_dotall.blockSignals(True)

        self.mode_combo.setCurrentText(data.get("mode", "Regex"))
        self.regex_input.setText(data["pattern"])
        self.text_input.setPlainText(data["test_string"])
        self.replace_input.clear()

        flags = data["flags"]
        self.chk_ignorecase.setChecked(bool(flags & re.IGNORECASE))
        self.chk_multiline.setChecked(bool(flags & re.MULTILINE))
        self.chk_dotall.setChecked(bool(flags & re.DOTALL))

        self.regex_input.blockSignals(False)
        self.mode_combo.blockSignals(False)
        self.chk_ignorecase.blockSignals(False)
        self.chk_multiline.blockSignals(False)
        self.chk_dotall.blockSignals(False)

        self.trigger_evaluation()

    def save_pattern(self):
        name, ok = QInputDialog.getText(
            self, "Save Pattern", "Enter a name for this regex pattern:"
        )
        if not ok or not name.strip():
            return

        pattern = self.regex_input.text()
        test_str = self.text_input.toPlainText()
        flags = self.get_active_flags()
        mode = self.mode_combo.currentText()

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO patterns (name, pattern, flags, test_string, mode) 
                VALUES (?, ?, ?, ?, ?)
            """,
                (name.strip(), pattern, flags, test_str, mode),
            )
            conn.commit()

        self.load_patterns()
        QMessageBox.information(
            self, "Saved", "Pattern saved to local library successfully."
        )

    def delete_pattern(self):
        item = self.pattern_list.currentItem()
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete '{item.text()}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM patterns WHERE id=?", (data["id"],))
                conn.commit()
            self.load_patterns()

    def filter_patterns(self):
        query = self.filter_input.text().lower()
        for i in range(self.pattern_list.count()):
            item = self.pattern_list.item(i)
            item.setHidden(query not in item.text().lower())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RegexSandbox()
    window.show()
    sys.exit(app.exec())
