# --- Shared Stylesheet template for all Nexus Tools (Archiver, File Ops, etc) ---

TOOL_SHEET = """
/* ── Root ── */
* { outline: none; }
QMainWindow, QWidget#root {
    background: {{bg_base}};
}

/* ── Main card ── */
QFrame#card {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-radius: 20px;
}

/* ── Header labels ── */
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

/* ── Drop zone ── */
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

/* ── File list ── */
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
QListWidget::item:last {
    border-bottom: none;
}
QListWidget::item:selected {
    background: {{accent_subtle}};
    color: {{accent}};
}
QListWidget::item:hover:!selected {
    background: rgba(255,255,255,0.03);
}
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
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Input & Combo ── */
QLineEdit, QComboBox {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 9px 14px;
    color: {{text_primary}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    selection-background-color: {{accent_pressed}};
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid {{accent_pressed}};
    background: {{bg_overlay}};
}
QLineEdit::placeholder {
    color: {{text_disabled}};
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    selection-background-color: {{accent_pressed}};
    color: {{text_primary}};
}

/* ── Buttons — base ── */
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
QPushButton:pressed {
    background: rgba(255,255,255,0.02);
}
QPushButton:disabled {
    opacity: 0.35;
}

/* ── Buttons — accent variants ── */
QPushButton#btn_compress {
    color: {{accent}};
    border: 1px solid rgba(0,212,255,0.25);
    background: rgba(0,212,255,0.06);
}
QPushButton#btn_compress:hover {
    background: rgba(0,212,255,0.12);
    border-color: rgba(0,212,255,0.45);
}

QPushButton#btn_extract, QPushButton#btn_success {
    color: {{success}};
    border: 1px solid rgba(0,255,157,0.25);
    background: rgba(0,255,157,0.06);
}
QPushButton#btn_extract:hover, QPushButton#btn_success:hover {
    background: rgba(0,255,157,0.12);
    border-color: rgba(0,255,157,0.45);
}

QPushButton#btn_danger {
    color: {{danger}};
    border: 1px solid rgba(255,68,102,0.25);
    background: rgba(255,68,102,0.06);
}

/* ── Progress bar ── */
QProgressBar {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 6px;
    height: 6px;
    text-align: center;
    font-size: 0px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {{accent}}, stop:1 {{success}});
    border-radius: 5px;
}

/* ── Divider ── */
QFrame#divider {
    background: {{border}};
    max-height: 1px;
    border: none;
}
"""
