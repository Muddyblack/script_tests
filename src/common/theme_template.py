# --- Shared Stylesheet template for all Nexus Tools ---

TOOL_SHEET = """
/* ── Reset ── */
* { outline: none; }

/* ── Root ── */
QMainWindow, QWidget#root {
    background: {{bg_base}};
}

/* ── Main card ── */
QFrame#card {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-radius: 20px;
}

/* ── Divider ── */
QFrame#divider {
    background: {{border}};
    max-height: 1px;
    border: none;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Labels
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QLabel#title {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 4px;
    color: {{accent}};
}
QLabel#sub {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    letter-spacing: 2px;
    color: {{text_secondary}};
}
QLabel#section_label {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 9px;
    letter-spacing: 3px;
    color: {{text_secondary}};
}
QLabel#status {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {{text_secondary}};
    padding: 2px 0;
}
QLabel#state_LISTEN  { color: {{success}}; font-weight: 600; }
QLabel#state_ESTAB   { color: {{accent}};  font-weight: 600; }
QLabel#state_CLOSE   { color: {{danger}};  font-weight: 600; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Drop zone
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QLabel#drop_zone {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 12px;
    letter-spacing: 1px;
    color: {{text_secondary}};
    background: transparent;
    border: 1px dashed {{border_light}};
    border-radius: 14px;
    padding: 40px 20px;
}
QLabel#drop_zone[active="true"] {
    color: {{accent}};
    border: 1px solid {{accent}};
    background: {{accent_subtle}};
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   List widget
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QListWidget {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    padding: 4px;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: transparent;
}
QListWidget::item {
    padding: 8px 12px;
    border-radius: 8px;
    border-bottom: 1px solid {{border}};
    color: {{text_primary}};
}
QListWidget::item:last       { border-bottom: none; }
QListWidget::item:selected   { background: {{accent_subtle}}; color: {{accent}}; }
QListWidget::item:hover:!selected { background: rgba(255,255,255,0.03); }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Scrollbar
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: {{border_light}};
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical { height: 0; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Table
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QTableWidget {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    gridline-color: {{border}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
    selection-color: {{accent}};
}
QTableWidget::item                  { padding: 6px 10px; border: none; }
QTableWidget::item:selected         { background: {{accent_subtle}}; color: {{accent}}; }
QTableWidget::item:hover:!selected  { background: rgba(255,255,255,0.03); }

QHeaderView::section {
    background: {{bg_elevated}};
    color: {{text_secondary}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 8px 10px;
    border: none;
    border-right:  1px solid {{border}};
    border-bottom: 1px solid {{border}};
}
QHeaderView::section:hover { color: {{accent}}; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Inputs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 9px 14px;
    color: {{text_primary}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    selection-background-color: {{accent_pressed}};
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid {{accent_pressed}};
    background: {{bg_overlay}};
}
QLineEdit::placeholder { color: {{text_disabled}}; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Combo box
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QComboBox {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 10px;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    min-width: 110px;
}
QComboBox:hover  { border: 1px solid {{border_focus}}; }
QComboBox:focus  { border: 1px solid {{accent_pressed}}; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: {{bg_elevated}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    selection-background-color: {{accent_subtle}};
    selection-color: {{accent}};
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Buttons — base
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QPushButton {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    border-radius: 10px;
    padding: 9px 20px;
    border: 1px solid {{border_light}};
    background: {{bg_overlay}};
    color: {{text_secondary}};
}
QPushButton:hover {
    color: {{text_primary}};
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
}
QPushButton:pressed  { background: rgba(255,255,255,0.02); }
QPushButton:disabled { opacity: 0.35; }

/* ── action / danger (tool-bar style, smaller) ── */
QPushButton#action_btn {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 16px;
    letter-spacing: 1px;
}
QPushButton#action_btn:hover {
    background: {{bg_control_hov}};
    border: 1px solid {{border_focus}};
    color: {{accent}};
}

QPushButton#danger_btn {
    background: {{bg_control}};
    color: {{danger}};
    border: 1px solid {{danger_border}};
    border-radius: 8px;
    padding: 6px 16px;
    letter-spacing: 1px;
}
QPushButton#danger_btn:hover {
    background: {{danger_glow}};
    border: 1px solid {{danger}};
}

/* ── semantic accent variants ── */
QPushButton#btn_compress {
    color: {{accent}};
    border: 1px solid rgba(0,212,255,0.25);
    background: rgba(0,212,255,0.06);
}
QPushButton#btn_compress:hover {
    background: rgba(0,212,255,0.12);
    border-color: rgba(0,212,255,0.45);
}

QPushButton#btn_extract,
QPushButton#btn_success {
    color: {{success}};
    border: 1px solid rgba(0,255,157,0.25);
    background: rgba(0,255,157,0.06);
}
QPushButton#btn_extract:hover,
QPushButton#btn_success:hover {
    background: rgba(0,255,157,0.12);
    border-color: rgba(0,255,157,0.45);
}

QPushButton#btn_danger {
    color: {{danger}};
    border: 1px solid rgba(255,68,102,0.25);
    background: rgba(255,68,102,0.06);
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Checkbox
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QCheckBox {
    color: {{text_secondary}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid {{border_focus}};
    background: {{bg_control}};
}
QCheckBox::indicator:checked {
    background: {{accent}};
    border: 1px solid {{accent}};
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Progress bar
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QProgressBar {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 6px;
    height: 6px;
    text-align: center;
    font-size: 0px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {{accent}}, stop:1 {{success}});
    border-radius: 5px;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Tab widget
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QTabWidget::pane {
    border: 1px solid {{border}};
    background: {{bg_base}};
    top: -1px;
}
QTabBar::tab {
    background: {{bg_elevated}};
    color: {{text_secondary}};
    border: 1px solid {{border}};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 9px 22px;
    margin-right: 2px;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QTabBar::tab:selected {
    background: {{bg_base}};
    color: {{accent}};
    border-bottom: 2px solid {{accent}};
}
QTabBar::tab:hover:!selected { background: {{bg_overlay}}; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Sidebar frame
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QFrame#sidebar {
    background: {{bg_elevated}};
    border-right: 1px solid {{border}};
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Tool-specific labels
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
QLabel#section_title {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {{text_secondary}};
    margin-top: 8px;
}
QLabel#mode_label {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    color: {{text_secondary}};
}
QLabel#status_label {
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    font-weight: 700;
    color: {{text_secondary}};
    padding: 2px 0;
}

/* ── Accent button ── */
QPushButton#accent_btn {
    background: {{accent}};
    color: {{text_on_accent}};
    border: none;
    font-size: 11px;
    letter-spacing: 1px;
}
QPushButton#accent_btn:hover   { background: {{accent_hover}}; }
QPushButton#accent_btn:pressed { background: {{accent_pressed}}; }
"""

# ---------------------------------------------------------------------------
# Color Picker stylesheet — preserves exact color-picker look
# ---------------------------------------------------------------------------
COLOR_PICKER_SHEET = """
* { font-family: 'SF Pro Display', 'Helvetica Neue', 'Segoe UI', sans-serif; }
QWidget#root_bg { background-color: {{bg_base}}; }
QWidget { background-color: transparent; color: {{text_primary}}; }
QLabel#section_label {
    font-size: 10px; font-weight: 600; letter-spacing: 2px;
    color: {{text_secondary}};
}
QLabel#value_label {
    font-size: 19px; font-weight: 700;
    color: {{text_primary}}; letter-spacing: -0.5px;
}
QLabel#sub_label   { font-size: 11px; color: {{text_secondary}}; font-weight: 400; }
QLabel#channel_label {
    font-size: 9px; font-weight: 700; letter-spacing: 1.5px;
    color: {{text_secondary}};
}
QLabel#app_title {
    font-size: 10px; font-weight: 700; letter-spacing: 3px;
    color: {{text_secondary}};
}
QLineEdit {
    background-color: {{bg_control}};
    border: 1px solid {{border}};
    padding: 8px 32px 8px 10px;
    border-radius: 8px;
    color: {{text_primary}};
    font-size: 13px; font-weight: 500;
    selection-background-color: {{accent}};
}
QLineEdit:focus {
    border: 1px solid {{border_focus}};
    background-color: {{bg_overlay}};
}
QLineEdit#channel_input {
    padding: 5px 4px; font-size: 12px;
    border-radius: 7px; font-weight: 600;
}
QPushButton#primary {
    background-color: {{accent}}; color: {{text_on_accent}};
    border: none; padding: 10px 16px;
    border-radius: 10px; font-weight: 600; font-size: 12px;
}
QPushButton#primary:hover   { background-color: {{accent_hover}}; }
QPushButton#primary:pressed { background-color: {{accent_pressed}}; }
QPushButton#ghost {
    background-color: {{bg_control}}; color: {{text_primary}};
    border: 1px solid {{border}}; padding: 10px 16px;
    border-radius: 10px; font-weight: 600; font-size: 12px;
}
QPushButton#ghost:hover {
    background-color: {{bg_control_hov}}; color: {{text_primary}};
    border: 1px solid {{border_focus}};
}
QPushButton#toggle {
    background-color: {{bg_control}}; color: {{text_primary}};
    border: 1px solid {{border}}; padding: 6px 10px;
    border-radius: 8px; font-size: 14px;
    min-width: 32px; max-width: 32px;
}
QPushButton#toggle:hover {
    background-color: {{bg_control_hov}};
    border: 1px solid {{border_focus}};
}
QPushButton#expand_btn {
    background-color: transparent; color: {{text_secondary}};
    border: none; padding: 0px;
    font-size: 10px; font-weight: 700; letter-spacing: 1px;
}
QPushButton#expand_btn:hover { color: {{text_primary}}; }
QPushButton#inline_copy {
    background-color: transparent; color: {{text_secondary}};
    border: none; padding: 0px 6px;
    font-size: 13px; min-width: 24px; max-width: 24px;
}
QPushButton#inline_copy:hover { color: {{accent}}; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: transparent; width: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background: {{border}}; border-radius: 2px; min-height: 20px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical { height: 0; }
"""