"""Extra QSS stylesheet for the Env Var Explorer tool."""

EXTRA = """
QTabWidget::pane {
    border: 1px solid {{border}};
    border-radius: 12px;
    background: {{bg_overlay}};
    top: -1px;
}
QTabBar::tab {
    background: {{bg_control}};
    color: {{text_secondary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    border: 1px solid {{border}};
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 8px 22px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: {{bg_overlay}};
    color: {{accent}};
    border-color: {{border_focus}};
}
QTabBar::tab:hover:!selected { background: {{bg_control_hov}}; color: {{text_primary}}; }

QListWidget#var_list {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    padding: 4px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: transparent;
    outline: none;
}
QListWidget#var_list::item {
    padding: 7px 10px;
    border-radius: 8px;
    border-bottom: 1px solid {{border}};
    color: {{text_primary}};
}
QListWidget#var_list::item:selected {
    background: {{accent_subtle}};
    color: {{accent}};
}
QListWidget#var_list::item:hover:!selected { background: rgba(255,255,255,0.03); }

QListWidget#path_list {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 4px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
    selection-color: {{accent}};
    outline: none;
}
QListWidget#path_list::item {
    padding: 6px 10px;
    border-radius: 6px;
    border-bottom: 1px solid {{border}};
}
QListWidget#path_list::item:selected { background: {{accent_subtle}}; color: {{accent}}; }

QLabel#var_name {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    font-weight: 700;
    color: {{accent}};
}
QLabel#var_value {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    color: {{text_secondary}};
}
QPlainTextEdit#edit_val {
    background: {{bg_control}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 10px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
}
QPlainTextEdit#edit_val:focus { border: 1px solid {{border_focus}}; }

QPushButton#action_btn {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#action_btn:hover { background: {{bg_control_hov}}; color: {{accent}}; border: 1px solid {{border_focus}}; }

QPushButton#danger_btn {
    background: {{bg_control}};
    color: {{danger}};
    border: 1px solid {{danger_border}};
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#danger_btn:hover { background: {{danger_glow}}; border: 1px solid {{danger}}; }

QPushButton#accent_btn {
    background: {{accent}};
    color: {{text_on_accent}};
    border: none;
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#accent_btn:hover { background: {{accent_hover}}; }
QPushButton#accent_btn:pressed { background: {{accent_pressed}}; }

QLabel#path_badge {
    color: {{warning}};
    font-size: 9px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    letter-spacing: 2px;
    border: 1px solid {{warning}};
    border-radius: 4px;
    padding: 1px 6px;
}
"""
