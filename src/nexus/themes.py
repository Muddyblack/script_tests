"""Light and dark theme stylesheets for Nexus Search."""


def get_light_theme() -> str:
    """Return the premium light-mode stylesheet."""
    return """
        QWidget#nexus_bg {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 255, 255, 245),
                stop:1 rgba(240, 243, 248, 255));
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 30px;
        }
        QLineEdit#nexus_search {
            background: rgba(0, 0, 0, 0.04);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 12px;
            padding: 10px 20px;
            color: #111827;
            font-size: 16px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLineEdit#nexus_search:focus {
            border: 1px solid rgba(59, 130, 246, 0.5);
            background: #ffffff;
        }
        QPushButton#mode_btn {
            background: rgba(0, 0, 0, 0.03);
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 10px;
            padding: 6px 14px;
            color: #4b5563;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton#mode_btn:checked {
            background: rgba(59, 130, 246, 0.12);
            border: 1px solid rgba(59, 130, 246, 0.4);
            color: #1d4ed8;
        }
        QPushButton#mode_btn:hover {
            background: rgba(0, 0, 0, 0.08);
        }
        QListWidget#nexus_list {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#nexus_list::item {
            background: rgba(0, 0, 0, 0.02);
            border-radius: 18px;
            margin-bottom: 8px;
            padding: 2px 18px;
            color: #1f2937;
            border: 1px solid transparent;
        }
        QListWidget#nexus_list::item:selected {
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.15);
        }
        QLabel#item_title { color: #111827; font-size: 15px; font-weight: 600; }
        QLabel#item_path { color: #6b7280; font-size: 11px; }
        QLabel#status_text, QLabel#hint_text { color: #9ca3af; font-size: 11px; font-weight: 500; }
        QFrame#filter_bar { background: rgba(0, 0, 0, 0.02); border-radius: 12px; margin-bottom: 5px; }
        QTreeWidget#nexus_tree { background: transparent !important; color: #1f2937; border: none; font-size: 14px; outline: none; }
        QTreeWidget#nexus_tree::viewport { background: transparent; }
        QTreeWidget#nexus_tree::item {
            padding: 10px 14px;
            border-bottom: 1px solid rgba(0, 0, 0, 0.03);
            border-radius: 12px;
            margin-bottom: 4px;
            background: rgba(0, 0, 0, 0.015);
        }
        QTreeWidget#nexus_tree::item:selected {
            background: rgba(59, 130, 246, 0.08);
            color: #1d4ed8;
            border: 1px solid rgba(59, 130, 246, 0.2);
        }
        QStackedWidget#results_stack {
            background: transparent;
            border: none;
        }
    """


def get_dark_theme() -> str:
    """Return the premium dark-mode stylesheet."""
    return """
        QWidget#nexus_bg {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(15, 25, 45, 220),
                stop:0.4 rgba(10, 15, 30, 210),
                stop:1 rgba(7, 10, 20, 230));
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 30px;
        }
        QLineEdit#nexus_search {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 10px 20px;
            color: #e5e7eb;
            font-size: 16px;
            font-family: 'Outfit', 'Inter', 'Segoe UI';
        }
        QLineEdit#nexus_search:focus {
            border: 1px solid rgba(96, 165, 250, 0.5);
            background: rgba(0, 0, 0, 0.3);
        }
        QPushButton#mode_btn {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 6px 14px;
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton#mode_btn:checked {
            background: rgba(59, 130, 246, 0.2);
            border: 1px solid rgba(59, 130, 246, 0.5);
            color: #60a5fa;
        }
        QListWidget#nexus_list { background: transparent; border: none; outline: none; }
        QListWidget#nexus_list::item {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 18px;
            margin-bottom: 8px;
            padding: 2px 18px;
            color: #d1d5db;
            border: 1px solid transparent;
        }
        QListWidget#nexus_list::item:selected {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        QLabel#item_title { color: #ffffff; font-size: 15px; font-weight: 600; }
        QLabel#item_path { color: rgba(255, 255, 255, 0.45); font-size: 11px; }
        QLabel#status_text, QLabel#hint_text { color: rgba(255, 255, 255, 0.35); font-size: 11px; font-weight: 500; }
        QFrame#filter_bar { background: rgba(255, 255, 255, 0.02); border-radius: 12px; margin-bottom: 5px; }
        QTreeWidget#nexus_tree { background: transparent !important; color: #d1d5db; border: none; font-size: 14px; outline: none; }
        QTreeWidget#nexus_tree::viewport { background: transparent; }
        QTreeWidget#nexus_tree::item {
            padding: 10px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.02);
            border-radius: 12px;
            margin-bottom: 4px;
            background: rgba(255, 255, 255, 0.01);
        }
        QTreeWidget#nexus_tree::item:selected {
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.2);
        }
        QStackedWidget#results_stack {
            background: transparent;
            border: none;
        }
    """
