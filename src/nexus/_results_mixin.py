"""Results-population mixin — list/tree rendering, icon loading, action helpers."""

import os
import subprocess
import sys
import webbrowser

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.common.config import PROJECT_ROOT
from src.common.theme import ThemeManager

from .system_commands import kill_all_processes as _kill_all_procs
from .utils import format_display_name
from .widgets import IconWorker


class _ResultsMixin:
    # ------------------------------------------------------------------
    # SVG icon helper
    # ------------------------------------------------------------------
    def _create_svg_icon(self, svg_name, color="#9ca3af"):
        svg_path = os.path.join(PROJECT_ROOT, "assets", "svgs", svg_name)
        if not os.path.exists(svg_path):
            return QIcon()
        try:
            with open(svg_path, encoding="utf-8") as f:
                data = f.read().replace("currentColor", color)
            pix = QPixmap()
            pix.loadFromData(QByteArray(data.encode("utf-8")), "SVG")
            return QIcon(pix)
        except Exception:
            return QIcon()

    # ------------------------------------------------------------------
    # Path action helpers
    # ------------------------------------------------------------------
    def _action_copy_path(self, path: str):
        norm = os.path.normpath(path)
        from src.nexus.utils import copy_to_clipboard
        copy_to_clipboard(norm)
        short = norm if len(norm) < 50 else "…" + norm[-45:]
        self.status_lbl.setText(f"Copied: {short}")

    def _action_copy_dir(self, path: str):
        d = path if os.path.isdir(path) else os.path.dirname(path)
        norm = os.path.normpath(d)
        from src.nexus.utils import copy_to_clipboard
        copy_to_clipboard(norm)
        short = norm if len(norm) < 50 else "…" + norm[-45:]
        self.status_lbl.setText(f"Copied: {short}")

    def _action_open_folder(self, path: str):
        norm = os.path.normpath(path)
        if os.path.exists(norm):
            if os.path.isdir(norm):
                from .utils import open_path
                open_path(norm)
            else:
                if sys.platform == "win32":
                    subprocess.Popen(f'explorer /select,"{norm}"')
                else:
                    # On Linux, opening the directory of the file is the best fallback
                    from .utils import open_path
                    open_path(os.path.dirname(norm))
        else:
            self.status_lbl.setText("Path not found on disk")

    # ------------------------------------------------------------------
    # List result population
    # ------------------------------------------------------------------
    def populate_list_results(self, candidates):
        self.current_candidates = candidates[:50]
        self.results_list.setUpdatesEnabled(False)

        for idx, c in enumerate(self.current_candidates):
            d = c["data"]
            dtype = d.get("type")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, c["data"])
            item.setData(Qt.ItemDataRole.UserRole + 1, c)
            self.results_list.addItem(item)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 0, 8, 0)
            row_layout.setSpacing(14)

            # -- Icon (UNC-aware) --
            icon_label = QLabel()
            icon_label.setObjectName(f"icon_{idx}")
            icon_label.setFixedSize(38, 38)
            icon_label.setScaledContents(True)

            icon_name = c.get("icon", "file.svg")
            file_path = c.get("file_path") or c["data"].get("path", "")
            if file_path and self._is_unc_path(file_path):
                icon_name = "globe.svg"

            # Attempt cached native icon
            cached_pixmap = None
            if file_path:
                ext = os.path.splitext(file_path)[1].lower()
                is_dir = os.path.isdir(file_path) if os.path.exists(file_path) else False
                cache_key = (
                    "__dir__" if is_dir
                    else (file_path if ext in (".exe", ".lnk", ".url") else ext)
                )
                cached_pixmap = self.icon_cache.get(cache_key)

            if cached_pixmap:
                icon_label.setPixmap(cached_pixmap)
                icon_label.setProperty("native_loaded", True)
            else:
                asset_path = os.path.join(PROJECT_ROOT, "assets", icon_name)
                if os.path.exists(asset_path) and icon_name.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".ico")
                ):
                    icon_label.setPixmap(QPixmap(asset_path))
                else:
                    color_hex = c.get("color", "#9ca3af")
                    svg_path = os.path.join(PROJECT_ROOT, "assets", "svgs", icon_name)
                    if not os.path.exists(svg_path):
                        svg_path = os.path.join(PROJECT_ROOT, "assets", "svgs", "file.svg")
                    try:
                        with open(svg_path, encoding="utf-8") as fs:
                            svg_data = fs.read()
                        svg_data = svg_data.replace("currentColor", color_hex)
                        pix = QPixmap()
                        pix.loadFromData(QByteArray(svg_data.encode("utf-8")), "SVG")
                        icon_label.setPixmap(pix)
                    except Exception:
                        pass

            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(icon_label)

            # -- Text column --
            text_container = QVBoxLayout()
            text_container.setContentsMargins(0, 0, 0, 0)
            text_container.setSpacing(1)

            title_lbl = QLabel(c["title"])
            title_lbl.setObjectName("item_title")
            if "color" in c:
                title_lbl.setStyleSheet(f"color: {c['color']};")

            display_path = c.get("path", "")
            if file_path and self._is_unc_path(file_path):
                display_path = f"{display_path}"
            path_lbl = QLabel(format_display_name(display_path, max_len=72))
            path_lbl.setObjectName("item_path")

            text_container.addWidget(title_lbl)

            # Chronos Badges
            if dtype in ("chronos_log", "chronos_task"):
                badge_layout = QHBoxLayout()
                badge_layout.setSpacing(6)
                parsed = d.get("parsed", {})

                pri = parsed.get("priority", "Medium")
                if pri != "Medium":
                    pri_lbl = QLabel(pri)
                    mgr = ThemeManager()
                    is_dark = mgr.is_dark
                    if pri == "High":
                        pri_bg = "#450a0a" if is_dark else "#fee2e2"
                        pri_fg = "#f87171" if is_dark else "#991b1b"
                    else:
                        pri_bg = "#064e3b" if is_dark else "#d1fae5"
                        pri_fg = "#34d399" if is_dark else "#065f46"
                    pri_lbl.setStyleSheet(
                        f"background: {pri_bg}; color: {pri_fg}; font-size: 9px; "
                        f"font-weight: bold; border-radius: 4px; padding: 2px 6px;"
                    )
                    badge_layout.addWidget(pri_lbl)

                due = parsed.get("due_date")
                if due:
                    due_lbl = QLabel(f"📅 {due}")
                    mgr = ThemeManager()
                    is_dark = mgr.is_dark
                    due_bg = "#1e293b" if is_dark else "#f1f5f9"
                    due_fg = "#94a3b8" if is_dark else "#475569"
                    due_lbl.setStyleSheet(
                        f"background: {due_bg}; color: {due_fg}; font-size: 9px; "
                        f"font-weight: bold; border-radius: 4px; padding: 2px 6px;"
                    )
                    badge_layout.addWidget(due_lbl)

                for tag in parsed.get("tags", []):
                    tag_lbl = QLabel(f"#{tag}")
                    mgr = ThemeManager()
                    is_dark = mgr.is_dark
                    tag_bg = "#1e1b4b" if is_dark else "#e0e7ff"
                    tag_fg = "#818cf8" if is_dark else "#3730a3"
                    tag_lbl.setStyleSheet(
                        f"background: {tag_bg}; color: {tag_fg}; font-size: 9px; "
                        f"font-weight: bold; border-radius: 4px; padding: 2px 6px;"
                    )
                    badge_layout.addWidget(tag_lbl)

                badge_layout.addStretch()
                text_container.addLayout(badge_layout)

            text_container.addWidget(path_lbl)
            row_layout.addLayout(text_container, stretch=1)

            # Alt Shortcut Badge
            if idx < 9:
                hk_lbl = QLabel(f"{idx + 1}")
                hk_lbl.setObjectName("shortcut_badge")
                hk_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row_layout.addWidget(hk_lbl)

            # Action buttons
            if dtype in ("file", "app", "script", None) and d.get("path"):
                p_val = d["path"]
                btn_copy = QPushButton()
                btn_copy.setIcon(self._create_svg_icon("copy.svg"))
                btn_copy.setObjectName("action_btn")
                btn_copy.setToolTip("Copy path")
                btn_copy.setFixedSize(32, 32)
                btn_copy.clicked.connect(lambda _, p=p_val: self._action_copy_path(p))
                row_layout.addWidget(btn_copy)

                btn_dir = QPushButton()
                btn_dir.setIcon(self._create_svg_icon("folder.svg"))
                btn_dir.setObjectName("action_btn")
                btn_dir.setToolTip("Open containing folder")
                btn_dir.setFixedSize(32, 32)
                btn_dir.clicked.connect(lambda _, p=p_val: self._action_open_folder(p))
                row_layout.addWidget(btn_dir)

            elif dtype == "process":
                p_id = d["pid"]
                p_name = d["name"]
                p_path = c.get("file_path")

                if p_path and os.path.exists(p_path):
                    btn_dir = QPushButton()
                    btn_dir.setIcon(self._create_svg_icon("folder.svg"))
                    btn_dir.setObjectName("action_btn")
                    btn_dir.setToolTip("Open process location")
                    btn_dir.setFixedSize(32, 32)
                    btn_dir.clicked.connect(
                        lambda _, p=p_path: self._action_open_folder(p)
                    )
                    row_layout.addWidget(btn_dir)

                btn_info = QPushButton()
                btn_info.setIcon(self._create_svg_icon("info.svg"))
                btn_info.setObjectName("action_btn")
                btn_info.setToolTip(f"Search web for {p_name}")
                btn_info.setFixedSize(32, 32)
                btn_info.clicked.connect(
                    lambda _, n=p_name: webbrowser.open(
                        f"https://www.google.com/search?q={n}+process+info"
                    )
                )
                row_layout.addWidget(btn_info)

                btn_kill = QPushButton()
                btn_kill.setIcon(self._create_svg_icon("power.svg", color="#f87171"))
                btn_kill.setObjectName("action_btn_danger")
                btn_kill.setToolTip(f"Kill process {p_id}")
                btn_kill.setFixedSize(32, 32)
                btn_kill.setStyleSheet(
                    "background: #450a0a; border: 1px solid #7f1d1d; border-radius: 4px;"
                )
                btn_kill.clicked.connect(
                    lambda _, pid=p_id, n=p_name: self.kill_process(pid, n)
                )
                row_layout.addWidget(btn_kill)

            elif dtype == "process_kill_all":
                p_name = d["name"]
                btn_kill_all = QPushButton("Kill All")
                btn_kill_all.setIcon(self._create_svg_icon("power.svg", color="#ffffff"))
                btn_kill_all.setObjectName("action_btn_danger")
                btn_kill_all.setToolTip(f"Kill all instances of {p_name}")
                btn_kill_all.setFixedSize(80, 32)
                btn_kill_all.setStyleSheet(
                    "background: #ef4444; color: white; border-radius: 4px; "
                    "font-weight: bold; font-size: 10px;"
                )
                btn_kill_all.clicked.connect(
                    lambda _, n=p_name: _kill_all_procs(self, n)
                )
                row_layout.addWidget(btn_kill_all)

            item.setSizeHint(QSize(row_widget.sizeHint().width(), 62))
            self.results_list.setItemWidget(item, row_widget)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

        self.results_list.setUpdatesEnabled(True)

        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.lazy_load_visible_icons)

    # ------------------------------------------------------------------
    # Tree result population
    # ------------------------------------------------------------------
    def populate_tree_results(self, candidates):
        self.results_tree.setUpdatesEnabled(False)
        tree_data = {}
        for c in candidates[:150]:
            path = c.get("path", "")
            if os.path.isabs(path):
                parts = path.split(os.sep)
                current = tree_data
                for i, part in enumerate(parts):
                    if not part and i == 0:
                        continue
                    if part not in current:
                        current[part] = {"_data": None, "_children": {}}
                    if i == len(parts) - 1:
                        current[part]["_data"] = c
                    current = current[part]["_children"]
            else:
                cat = "System & Core"
                if cat not in tree_data:
                    tree_data[cat] = {"_data": None, "_children": {}}
                tree_data[cat]["_children"][c["title"]] = {"_data": c, "_children": {}}

        def add_items_to_tree(parent_item, data_dict):
            for name, content in sorted(data_dict.items()):
                item = QTreeWidgetItem(
                    parent_item if parent_item is not None else self.results_tree
                )
                item.setText(0, name)
                if content["_data"]:
                    item.setData(0, Qt.ItemDataRole.UserRole, content["_data"]["data"])
                    file_path = content["_data"].get("file_path")
                    icon_name = content["_data"].get("icon", "")

                    loaded_icon = None
                    if file_path:
                        ext = os.path.splitext(file_path)[1].lower()
                        cache_key = (
                            file_path if ext in [".exe", ".lnk", ".url"] else ext
                        )
                        if cache_key in self.icon_cache:
                            loaded_icon = QIcon(self.icon_cache[cache_key])
                        elif cache_key not in self.pending_icons:
                            self.pending_icons.add(cache_key)
                            worker = IconWorker(file_path, cache_key, self)
                            self.thread_pool.start(worker)

                    if not loaded_icon and icon_name:
                        asset_path = os.path.join(PROJECT_ROOT, "assets", icon_name)
                        if os.path.exists(asset_path) and icon_name.lower().endswith(
                            (".png", ".jpg", ".jpeg", ".ico")
                        ):
                            loaded_icon = QIcon(asset_path)

                    if loaded_icon:
                        item.setIcon(0, loaded_icon)
                        item.setText(0, name)
                    else:
                        display_icon = icon_name if len(icon_name) <= 2 else "🔹"
                        item.setText(0, f"{display_icon} {name}")
                else:
                    item.setIcon(
                        0,
                        self.icon_provider.icon(QFileIconProvider.IconType.Folder),
                    )
                    item.setText(0, name)
                    item.setForeground(0, QColor("#60a5fa"))

                if content["_children"]:
                    add_items_to_tree(item, content["_children"])
                    item.setExpanded(True)

        add_items_to_tree(None, tree_data)
        self.results_tree.setUpdatesEnabled(True)

    # ------------------------------------------------------------------
    # Icon lazy loading
    # ------------------------------------------------------------------
    def on_item_hover(self, row):
        pass  # Reserved for future hover metadata

    def lazy_load_visible_icons(self):
        """Load icons only for items visible in the viewport."""
        if not hasattr(self, "current_candidates"):
            return

        viewport = self.results_list.viewport()
        first_visible = self.results_list.indexAt(viewport.rect().topLeft()).row()
        last_visible = self.results_list.indexAt(viewport.rect().bottomLeft()).row()

        if first_visible < 0:
            first_visible = 0
        if last_visible < 0:
            last_visible = self.results_list.count() - 1

        start = max(0, first_visible - 5)
        end = min(self.results_list.count(), last_visible + 6)

        for idx in range(start, end):
            item = self.results_list.item(idx)
            if not item:
                continue
            c = item.data(Qt.ItemDataRole.UserRole + 1)
            if not c:
                continue
            file_path = c.get("file_path")
            if not file_path:
                continue

            row_widget = self.results_list.itemWidget(item)
            if not row_widget:
                continue
            icon_label = row_widget.findChild(QLabel, f"icon_{idx}")
            if not icon_label:
                continue
            if icon_label.property("native_loaded"):
                continue

            ext = os.path.splitext(file_path)[1].lower()
            is_dir = os.path.isdir(file_path) if os.path.exists(file_path) else False
            cache_key = (
                "__dir__"
                if is_dir
                else (file_path if ext in [".exe", ".lnk", ".url"] else ext)
            )

            if cache_key in self.icon_cache:
                icon_label.setPixmap(self.icon_cache[cache_key])
                icon_label.setText("")
                icon_label.setStyleSheet("")
                icon_label.setProperty("native_loaded", True)
            elif cache_key not in self.pending_icons:
                self.pending_icons.add(cache_key)
                worker = IconWorker(file_path, cache_key, self)
                worker.setAutoDelete(True)
                self.thread_pool.start(worker)
