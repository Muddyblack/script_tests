# --- Color Picker stylesheet template ---
# Receives a ThemeManager instance (mgr) and returns a QSS string.


def make_stylesheet(mgr) -> str:
    return f"""
    * {{ font-family: 'SF Pro Display', 'Helvetica Neue', 'Segoe UI', sans-serif; }}
    QWidget#root_bg {{ background-color: {mgr["bg_base"]}; }}
    QWidget {{ background-color: transparent; color: {mgr["text_primary"]}; }}
    QLabel#section_label {{ font-size: 10px; font-weight: 600; letter-spacing: 2px; color: {mgr["text_secondary"]}; }}
    QLabel#value_label {{ font-size: 19px; font-weight: 700; color: {mgr["text_primary"]}; letter-spacing: -0.5px; }}
    QLabel#sub_label {{ font-size: 11px; color: {mgr["text_secondary"]}; font-weight: 400; }}
    QLabel#channel_label {{ font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: {mgr["text_secondary"]}; }}
    QLabel#app_title {{ font-size: 10px; font-weight: 700; letter-spacing: 3px; color: {mgr["text_secondary"]}; }}
    QLineEdit {{
        background-color: {mgr["bg_control"]}; border: 1px solid {mgr["border"]};
        padding: 8px 32px 8px 10px; border-radius: 8px; color: {mgr["text_primary"]};
        font-size: 13px; font-weight: 500; selection-background-color: {mgr["accent"]};
    }}
    QLineEdit:focus {{ border: 1px solid {mgr["border_focus"]}; background-color: {mgr["bg_overlay"]}; }}
    QLineEdit#channel_input {{ padding: 5px 4px; font-size: 12px; border-radius: 7px; font-weight: 600; }}
    QPushButton#primary {{
        background-color: {mgr["accent"]}; color: {mgr["text_on_accent"]}; border: none;
        padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 12px;
    }}
    QPushButton#primary:hover {{ background-color: {mgr["accent_hover"]}; }}
    QPushButton#primary:pressed {{ background-color: {mgr["accent_pressed"]}; }}
    QPushButton#ghost {{
        background-color: {mgr["bg_control"]}; color: {mgr["text_primary"]};
        border: 1px solid {mgr["border"]}; padding: 10px 16px;
        border-radius: 10px; font-weight: 600; font-size: 12px;
    }}
    QPushButton#ghost:hover {{
        background-color: {mgr["bg_control_hov"]}; color: {mgr["text_primary"]};
        border: 1px solid {mgr["border_focus"]};
    }}
    QPushButton#toggle {{
        background-color: {mgr["bg_control"]}; color: {mgr["text_primary"]};
        border: 1px solid {mgr["border"]}; padding: 6px 10px;
        border-radius: 8px; font-size: 14px; min-width: 32px; max-width: 32px;
    }}
    QPushButton#toggle:hover {{ background-color: {mgr["bg_control_hov"]}; border: 1px solid {mgr["border_focus"]}; }}
    QPushButton#expand_btn {{
        background-color: transparent; color: {mgr["text_secondary"]};
        border: none; padding: 0px; font-size: 10px; font-weight: 700; letter-spacing: 1px;
    }}
    QPushButton#expand_btn:hover {{ color: {mgr["text_primary"]}; }}
    QPushButton#inline_copy {{
        background-color: transparent; color: {mgr["text_secondary"]};
        border: none; padding: 0px 6px;
        font-size: 13px; min-width: 24px; max-width: 24px;
    }}
    QPushButton#inline_copy:hover {{ color: {mgr["accent"]}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {mgr["border"]}; border-radius: 2px; min-height: 20px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
