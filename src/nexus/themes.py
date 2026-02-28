"""Light and dark theme stylesheets for Nexus Search.

Includes the premium redesigned layout with side-panel filters,
action buttons on results, and rainbow glow animation for the input.
"""


# -- Shared animation keyframes (injected via QPainter, not CSS) --
# The rainbow glow is painted in widgets.py via RainbowFrame.


def get_dark_theme() -> str:
    """Return the premium dark-mode stylesheet."""
    return """
        /* ========== Background panel ========== */
        QWidget#nexus_bg {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(12, 20, 38, 235),
                stop:0.5 rgba(8, 14, 28, 240),
                stop:1 rgba(5, 8, 18, 245));
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
        }

        /* ========== Branding bar ========== */
        QLabel#nexus_brand {
            color: rgba(255, 255, 255, 0.6);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 3px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#nexus_version {
            color: rgba(255, 255, 255, 0.2);
            font-size: 9px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#nexus_clock {
            color: rgba(255, 255, 255, 0.4);
            font-size: 13px;
            font-weight: 700;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
            margin-top: 8px;
            letter-spacing: 2px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 8px 12px;
            border-radius: 10px;
        }
        QLabel#nexus_logo {
            background: transparent;
            border: none;
        }
        QPushButton#panel_toggle {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            color: rgba(255, 255, 255, 0.5);
            font-size: 10px;
            padding: 2px 6px;
        }
        QPushButton#panel_toggle:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
        }

        /* ========== Rainbow input wrapper ========== */
        QFrame#rainbow_frame {
            background: transparent;
            border: none;
            border-radius: 16px;
        }
        QLineEdit#nexus_search {
            background: rgba(255, 255, 255, 0.04);
            border: 2px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 12px 22px;
            color: #e5e7eb;
            font-size: 17px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
            selection-background-color: rgba(96, 165, 250, 0.3);
        }
        QLineEdit#nexus_search:focus {
            border: 2px solid transparent;
            background: rgba(0, 0, 0, 0.35);
        }
        QLabel#search_prefix {
            color: rgba(96, 165, 250, 0.7);
            font-size: 15px;
            font-weight: 700;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }

        /* ========== Left panel (full height) ========== */
        QWidget#left_panel {
            background: rgba(255, 255, 255, 0.02);
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        QWidget#right_panel {
            background: transparent;
        }
        QSplitter#nexus_splitter::handle {
            background: rgba(255, 255, 255, 0.06);
            width: 3px;
        }
        QSplitter#nexus_splitter::handle:hover {
            background: rgba(96, 165, 250, 0.4);
        }
        QLabel#panel_header {
            color: rgba(255, 255, 255, 0.3);
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 2px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QPushButton#mode_btn {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 10px;
            padding: 7px 12px;
            color: #78849e;
            font-size: 11px;
            font-weight: 600;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
            text-align: left;
        }
        QPushButton#mode_btn:checked {
            background: rgba(96, 165, 250, 0.12);
            border: 1px solid rgba(96, 165, 250, 0.35);
            color: #60a5fa;
        }
        QPushButton#mode_btn:hover {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        /* ========== Filter sub-bar ========== */
        QFrame#filter_bar {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            padding: 4px;
        }
        QLabel#filter_label {
            color: rgba(255, 255, 255, 0.3);
            font-size: 10px;
            font-weight: 600;
        }

        /* ========== Results list ========== */
        QListWidget#nexus_list {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#nexus_list::item {
            background: rgba(255, 255, 255, 0.015);
            border-radius: 14px;
            margin-bottom: 4px;
            padding: 2px 14px;
            color: #d1d5db;
            border: 1px solid transparent;
        }
        QListWidget#nexus_list::item:selected {
            background: rgba(96, 165, 250, 0.08);
            border: 1px solid rgba(96, 165, 250, 0.18);
        }
        QListWidget#nexus_list::item:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        /* ========== Result item labels ========== */
        QLabel#item_title {
            color: #f0f2f5;
            font-size: 14px;
            font-weight: 600;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#item_path {
            color: rgba(255, 255, 255, 0.35);
            font-size: 10px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }

        QLabel#shortcut_badge {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            color: rgba(255, 255, 255, 0.4);
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            margin-right: 6px;
        }

        /* ========== Inline action buttons ========== */
        QPushButton#action_btn {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 4px 10px;
            color: #78849e;
            font-size: 11px;
            font-weight: 500;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QPushButton#action_btn:hover {
            background: rgba(96, 165, 250, 0.15);
            border: 1px solid rgba(96, 165, 250, 0.3);
            color: #93bbfc;
        }

        /* ========== Status / Footer ========== */
        QLabel#status_text {
            color: rgba(255, 255, 255, 0.30);
            font-size: 10px;
            font-weight: 500;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#hint_text {
            color: rgba(255, 255, 255, 0.20);
            font-size: 10px;
            font-weight: 500;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }

        /* ========== Tree view ========== */
        QTreeWidget#nexus_tree {
            background: transparent !important;
            color: #d1d5db;
            border: none;
            font-size: 13px;
            outline: none;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QTreeWidget#nexus_tree::viewport { background: transparent; }
        QTreeWidget#nexus_tree::item {
            padding: 8px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.015);
            border-radius: 10px;
            margin-bottom: 3px;
            background: rgba(255, 255, 255, 0.01);
        }
        QTreeWidget#nexus_tree::item:selected {
            background: rgba(96, 165, 250, 0.1);
            color: #60a5fa;
            border: 1px solid rgba(96, 165, 250, 0.2);
        }

        /* ========== Stacked widget ========== */
        QStackedWidget#results_stack {
            background: transparent;
            border: none;
        }

        /* ========== Scrollbar styling ========== */
        QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 4px 0;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 3px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
    """


def get_light_theme() -> str:
    """Return the premium light-mode stylesheet."""
    return """
        /* ========== Background panel ========== */
        QWidget#nexus_bg {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 255, 255, 250),
                stop:0.5 rgba(248, 250, 253, 255),
                stop:1 rgba(241, 245, 249, 255));
            border: 1px solid rgba(0, 0, 0, 0.06);
            border-radius: 24px;
        }

        /* ========== Branding bar ========== */
        QLabel#nexus_brand {
            color: rgba(0, 0, 0, 0.4);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 3px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#nexus_version {
            color: rgba(0, 0, 0, 0.3);
            font-size: 9px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#nexus_clock {
            color: rgba(0, 0, 0, 0.5);
            font-size: 13px;
            font-weight: 700;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
            margin-top: 8px;
            letter-spacing: 2px;
            background: rgba(0, 0, 0, 0.03);
            border: 1px solid rgba(0, 0, 0, 0.05);
            padding: 8px 12px;
            border-radius: 10px;
        }
        QLabel#nexus_logo {
            background: transparent;
            border: none;
        }
        QPushButton#panel_toggle {
            background: rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 6px;
            color: rgba(0, 0, 0, 0.5);
            font-size: 10px;
            padding: 2px 6px;
        }
        QPushButton#panel_toggle:hover {
            background: rgba(0, 0, 0, 0.1);
            color: black;
        }

        /* ========== Rainbow input wrapper ========== */
        QFrame#rainbow_frame {
            background: transparent;
            border: none;
            border-radius: 16px;
        }
        QLineEdit#nexus_search {
            background: rgba(0, 0, 0, 0.02);
            border: 2px solid rgba(0, 0, 0, 0.06);
            border-radius: 14px;
            padding: 12px 22px;
            color: #111827;
            font-size: 17px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
            selection-background-color: rgba(59, 130, 246, 0.2);
        }
        QLineEdit#nexus_search:focus {
            border: 2px solid transparent;
            background: rgba(255, 255, 255, 0.9);
        }
        QLabel#search_prefix {
            color: rgba(59, 130, 246, 0.7);
            font-size: 15px;
            font-weight: 700;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }

        /* ========== Left panel (full height) ========== */
        QWidget#left_panel {
            background: rgba(0, 0, 0, 0.015);
            border-right: 1px solid rgba(0, 0, 0, 0.06);
        }
        QWidget#right_panel {
            background: transparent;
        }
        QSplitter#nexus_splitter::handle {
            background: rgba(0, 0, 0, 0.06);
            width: 3px;
        }
        QSplitter#nexus_splitter::handle:hover {
            background: rgba(59, 130, 246, 0.4);
        }
        QLabel#panel_header {
            color: rgba(0, 0, 0, 0.3);
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 2px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QPushButton#mode_btn {
            background: rgba(0, 0, 0, 0.02);
            border: 1px solid rgba(0, 0, 0, 0.05);
            border-radius: 10px;
            padding: 7px 12px;
            color: #6b7280;
            font-size: 11px;
            font-weight: 600;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
            text-align: left;
        }
        QPushButton#mode_btn:checked {
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.25);
            color: #2563eb;
        }
        QPushButton#mode_btn:hover {
            background: rgba(0, 0, 0, 0.04);
            border: 1px solid rgba(0, 0, 0, 0.08);
        }

        /* ========== Filter sub-bar ========== */
        QFrame#filter_bar {
            background: rgba(0, 0, 0, 0.015);
            border: 1px solid rgba(0, 0, 0, 0.04);
            border-radius: 12px;
            padding: 4px;
        }
        QLabel#filter_label {
            color: rgba(0, 0, 0, 0.3);
            font-size: 10px;
            font-weight: 600;
        }

        /* ========== Results list ========== */
        QListWidget#nexus_list {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#nexus_list::item {
            background: rgba(0, 0, 0, 0.015);
            border-radius: 14px;
            margin-bottom: 4px;
            padding: 2px 14px;
            color: #1f2937;
            border: 1px solid transparent;
        }
        QListWidget#nexus_list::item:selected {
            background: rgba(59, 130, 246, 0.06);
            border: 1px solid rgba(59, 130, 246, 0.12);
        }
        QListWidget#nexus_list::item:hover {
            background: rgba(0, 0, 0, 0.03);
        }

        /* ========== Result item labels ========== */
        QLabel#item_title {
            color: #111827;
            font-size: 14px;
            font-weight: 600;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#item_path {
            color: #9ca3af;
            font-size: 10px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }

        QLabel#shortcut_badge {
            background: rgba(0, 0, 0, 0.05);
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 6px;
            color: rgba(0, 0, 0, 0.4);
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            margin-right: 6px;
        }

        /* ========== Inline action buttons ========== */
        QPushButton#action_btn {
            background: rgba(0, 0, 0, 0.03);
            border: 1px solid rgba(0, 0, 0, 0.06);
            border-radius: 8px;
            padding: 4px 10px;
            color: #6b7280;
            font-size: 11px;
            font-weight: 500;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QPushButton#action_btn:hover {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.2);
            color: #2563eb;
        }

        /* ========== Status / Footer ========== */
        QLabel#status_text {
            color: #9ca3af;
            font-size: 10px;
            font-weight: 500;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLabel#hint_text {
            color: #c0c7d1;
            font-size: 10px;
            font-weight: 500;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }

        /* ========== Tree view ========== */
        QTreeWidget#nexus_tree {
            background: transparent !important;
            color: #1f2937;
            border: none;
            font-size: 13px;
            outline: none;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QTreeWidget#nexus_tree::viewport { background: transparent; }
        QTreeWidget#nexus_tree::item {
            padding: 8px 14px;
            border-bottom: 1px solid rgba(0, 0, 0, 0.02);
            border-radius: 10px;
            margin-bottom: 3px;
            background: rgba(0, 0, 0, 0.01);
        }
        QTreeWidget#nexus_tree::item:selected {
            background: rgba(59, 130, 246, 0.06);
            color: #1d4ed8;
            border: 1px solid rgba(59, 130, 246, 0.15);
        }

        /* ========== Stacked widget ========== */
        QStackedWidget#results_stack {
            background: transparent;
            border: none;
        }

        /* ========== Scrollbar styling ========== */
        QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 4px 0;
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 0, 0, 0.08);
            border-radius: 3px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(0, 0, 0, 0.15);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
    """
