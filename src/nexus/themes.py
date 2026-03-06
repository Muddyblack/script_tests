"""Nexus Search QSS — generated dynamically from the active ThemeManager palette.

The rainbow glow is painted in widgets.py via RainbowFrame (not CSS).
"""


def _hex_to_rgba(hex_color: str, alpha: int) -> str:
    """Convert #RRGGBB to rgba(r,g,b,alpha) string."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_color


def _c(colors: dict, key: str, fallback: str = "#888888") -> str:
    return colors.get(key, fallback)


def _c_rgba(colors: dict, key: str, alpha: int, fallback: str = "#888888") -> str:
    col = colors.get(key, fallback)
    if col.startswith("rgba") or col.startswith("rgb"):
        return col
    return _hex_to_rgba(col, alpha)


def get_nexus_theme(mgr) -> str:
    """Return the Nexus QSS for the current ThemeManager state."""
    c = mgr.theme_data.get("colors", {})
    dark = mgr.is_dark

    # Gradient stops for the main panel (hex + alpha channel)
    bg_top = _c_rgba(c, "bg_base", 235 if dark else 250)
    bg_mid = _c_rgba(c, "bg_elevated", 240 if dark else 252)
    bg_bot = _c_rgba(c, "bg_overlay", 245 if dark else 255)

    # Translucent overlays — white-on-dark vs black-on-light
    if dark:
        ov_xs = "rgba(255,255,255,0.01)"
        ov_sm = "rgba(255,255,255,0.03)"
        ov_md = "rgba(255,255,255,0.05)"
        ov_lg = "rgba(255,255,255,0.08)"
        ov_brd = "rgba(255,255,255,0.06)"
        scrl = "rgba(255,255,255,0.08)"
        scrl_h = "rgba(255,255,255,0.15)"
    else:
        ov_xs = "rgba(0,0,0,0.005)"
        ov_sm = "rgba(0,0,0,0.02)"
        ov_md = "rgba(0,0,0,0.04)"
        ov_lg = "rgba(0,0,0,0.07)"
        ov_brd = "rgba(0,0,0,0.06)"
        scrl = "rgba(0,0,0,0.08)"
        scrl_h = "rgba(0,0,0,0.15)"

    accent = _c(c, "accent", "#60a5fa")
    accent_subtle = _c(c, "accent_subtle", "rgba(96,165,250,0.12)")
    # accent_pressed is used in TOOL_SHEET but not here
    border = _c(c, "border", "rgba(255,255,255,0.08)")
    text = _c(c, "text_primary", "#e5e7eb")
    text2 = _c(c, "text_secondary", "#78849e")
    text_dis = _c(c, "text_disabled", "#6b7280")

    font = "'Outfit','Inter','Segoe UI'"

    return f"""
        /* ── Main panel background ── */
        QWidget#nexus_bg {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0   {bg_top},
                stop:0.5 {bg_mid},
                stop:1   {bg_bot});
            border: 1px solid {ov_lg};
            border-radius: 24px;
        }}

        /* ── Branding / clock ── */
        QLabel#nexus_brand {{
            color: {text2}; font-size: 11px; font-weight: 700;
            letter-spacing: 3px; font-family: {font};
        }}
        QLabel#nexus_version {{
            color: {text_dis}; font-size: 9px; font-family: {font};
        }}
        QLabel#nexus_clock {{
            color: {text2}; font-size: 13px; font-weight: 700;
            font-family: {font}; margin-top: 8px; letter-spacing: 2px;
            background: {ov_xs}; border: 1px solid {ov_sm};
            padding: 8px 12px; border-radius: 10px;
        }}
        QLabel#nexus_logo {{ background: transparent; border: none; }}

        /* ── Top-bar buttons ── */
        QPushButton#panel_toggle {{
            background: {ov_sm}; border: 1px solid {ov_lg};
            border-radius: 6px; color: {text2}; font-size: 10px; padding: 2px 6px;
        }}
        QPushButton#panel_toggle:hover {{
            background: {ov_lg}; color: {text};
        }}

        QPushButton#theme_btn {{
            background: {ov_xs}; border: 1px solid {ov_md};
            border-radius: 6px; color: {text2}; font-size: 10px; padding: 2px 8px;
        }}
        QPushButton#theme_btn:hover {{
            background: {accent_subtle}; color: {accent}; border-color: {accent};
        }}

        QPushButton#nexus_close_btn {{
            background: {ov_sm}; border: 1px solid {ov_lg};
            border-radius: 8px; color: {text2}; font-size: 14px; padding: 2px;
            font-family: {font};
        }}
        QPushButton#nexus_close_btn:hover {{
            background: rgba(239, 68, 68, 0.4); color: #ffffff; border-color: #ef4444;
        }}

        /* ── Rainbow input wrapper ── */
        QFrame#rainbow_frame {{ background: transparent; border: none; border-radius: 16px; }}
        QLineEdit#nexus_search {{
            background: {ov_sm}; border: 2px solid {ov_lg};
            border-radius: 14px; padding: 12px 22px;
            color: {text}; font-size: 17px; font-family: {font};
            selection-background-color: {accent};
            selection-color: #ffffff;
        }}
        QLineEdit#nexus_search:focus {{
            border: 2px solid transparent; background: {ov_md};
        }}
        QLabel#search_prefix {{
            color: {accent}; font-size: 15px; font-weight: 700; font-family: {font};
        }}

        /* ── Left panel ── */
        QWidget#left_panel {{
            background: {ov_xs}; border-right: 1px solid {ov_brd};
        }}
        QWidget#right_panel {{ background: transparent; }}

        /* ── Splitter ── */
        QSplitter#nexus_splitter::handle {{
            background: {ov_brd}; width: 3px;
        }}
        QSplitter#nexus_splitter::handle:hover {{
            background: {accent_subtle};
        }}

        /* ── Panel header / mode buttons ── */
        QLabel#panel_header {{
            color: {text_dis}; font-size: 9px; font-weight: 700;
            letter-spacing: 2px; font-family: {font};
        }}
        QPushButton#mode_btn {{
            background: {ov_xs}; border: 1px solid {ov_sm};
            border-radius: 10px; padding: 7px 12px;
            color: {text2}; font-size: 11px; font-weight: 600;
            font-family: {font}; text-align: left;
        }}
        QPushButton#mode_btn:checked {{
            background: {accent_subtle}; border: 1px solid {border};
            color: {accent};
        }}
        QPushButton#mode_btn:hover {{
            background: {ov_md}; border: 1px solid {ov_lg};
        }}

        /* ── Filter bar ── */
        QFrame#filter_bar {{
            background: {ov_xs}; border: 1px solid {ov_sm};
            border-radius: 12px; padding: 4px;
        }}
        QLabel#filter_label {{
            color: {text_dis}; font-size: 10px; font-weight: 600;
        }}

        /* ── Results list ── */
        QListWidget#nexus_list {{
            background: transparent; border: none; outline: none;
        }}
        QListWidget#nexus_list::item {{
            background: {ov_xs}; border-radius: 14px; margin-bottom: 4px;
            padding: 2px 14px; color: {text}; border: 1px solid transparent;
        }}
        QListWidget#nexus_list::item:selected {{
            background: {accent_subtle}; border: 1px solid {border};
        }}
        QListWidget#nexus_list::item:hover {{
            background: {ov_sm};
        }}

        /* ── Result labels ── */
        QLabel#item_title {{
            color: {text}; font-size: 14px; font-weight: 600; font-family: {font};
        }}
        QLabel#item_path {{
            color: {text2}; font-size: 10px; font-family: {font};
        }}
        QLabel#shortcut_badge {{
            background: {ov_sm}; border: 1px solid {ov_lg};
            border-radius: 6px; color: {text_dis};
            font-size: 11px; font-weight: 700; padding: 2px 8px; margin-right: 6px;
        }}

        /* ── Inline action buttons ── */
        QPushButton#action_btn {{
            background: {ov_sm}; border: 1px solid {ov_brd};
            border-radius: 8px; padding: 4px 10px;
            color: {text2}; font-size: 11px; font-weight: 500; font-family: {font};
        }}
        QPushButton#action_btn:hover {{
            background: {accent_subtle}; border: 1px solid {border}; color: {accent};
        }}

        /* ── Footer ── */
        QLabel#status_text {{
            color: {text_dis}; font-size: 10px; font-weight: 500; font-family: {font};
        }}
        QLabel#hint_text {{
            color: {text_dis}; font-size: 10px; font-weight: 500; font-family: {font};
        }}

        /* ── Tree view ── */
        QTreeWidget#nexus_tree {{
            background: transparent !important; color: {text};
            border: none; font-size: 13px; outline: none; font-family: {font};
        }}
        QTreeWidget#nexus_tree::viewport {{ background: transparent; }}
        QTreeWidget#nexus_tree::item {{
            padding: 8px 14px; border-bottom: 1px solid {ov_xs};
            border-radius: 10px; margin-bottom: 3px; background: {ov_xs};
        }}
        QTreeWidget#nexus_tree::item:selected {{
            background: {accent_subtle}; color: {accent}; border: 1px solid {border};
        }}

        /* ── Stacked widget ── */
        QStackedWidget#results_stack {{ background: transparent; border: none; }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            background: transparent; width: 6px; margin: 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {scrl}; border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {scrl_h}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """
