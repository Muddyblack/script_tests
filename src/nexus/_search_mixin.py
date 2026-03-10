"""Search-logic mixin — perform_search and helpers."""

import os
import re
import threading
import urllib.parse

from .system_commands import update_process_cache as _update_procs
from .utils import format_display_name, parse_chronos_input


class _SearchMixin:
    # ------------------------------------------------------------------
    # UNC path helper
    # ------------------------------------------------------------------
    def _is_unc_path(self, path: str) -> bool:
        """Return True if *path* is a UNC / network path."""
        return path.startswith("\\\\") or path.startswith("//")

    # ------------------------------------------------------------------
    # Search engine
    # ------------------------------------------------------------------
    def perform_search(self):
        """Full search: instant in-memory results + async file DB query."""
        self.perform_search_instant()
        self.perform_search_files()

    def perform_search_instant(self):
        raw_search = self.search_input.text().strip()
        search = raw_search.lower()
        self.results_list.clear()
        self.results_tree.clear()
        self.pending_icons.clear()
        candidates = []
        seen = set()

        def add_candidate(c):
            # Generate a unique key for deduplication
            ctype = c.get("data", {}).get("type")
            key = None
            if ctype == "app":
                key = f"app_{c['data'].get('path')}"
            elif ctype == "cmd":
                key = f"cmd_{c['data'].get('cmd')}"
            elif ctype == "file":
                key = f"file_{c['data'].get('path')}"
            elif ctype == "url":
                key = f"url_{c['data'].get('url')}"
            elif ctype == "ssh":
                key = f"ssh_{c['data'].get('host')}"
            elif ctype == "process":
                key = f"proc_{c['data'].get('pid')}"
            elif ctype in ["filter_toggle", "filter_clear"]:
                key = f"filt_{c['title']}"

            if key and key in seen:
                return False
            if key:
                seen.add(key)
            candidates.append(c)
            return True

        # Generation counter — incremented each search so stale async results
        # from a previous query are silently discarded when they arrive.
        if not hasattr(self, "_search_gen"):
            self._search_gen = 0
        self._search_gen += 1
        _gen = self._search_gen

        def matches_all_terms(text, terms):
            if not terms:
                return True
            t_low = text.lower()
            return all(term.lower() in t_low for term in terms)

        # 0. CHRONOS QUICK-LOG (Achievement)
        if search.startswith("+") and len(search) > 1:
            raw_text = search[1:].strip()
            content, priority, tags, due_date = parse_chronos_input(raw_text)
            add_candidate(
                {
                    "score": 10000,
                    "title": f"🏆 {content}",
                    "path": f"Achievement • {priority} • {', '.join(tags) if tags else 'No tags'}",
                    "icon": "clock.svg",
                    "color": "#fbbf24",
                    "data": {
                        "type": "chronos_log",
                        "content": raw_text,
                        "parsed": {
                            "content": content,
                            "priority": priority,
                            "tags": tags,
                            "due_date": due_date,
                        },
                    },
                }
            )
            self.results_list.clear()
            self.results_tree.clear()
            self.populate_list_results(candidates)
            return

        # 0.5 CHRONOS QUICK-TASK
        if search.startswith("-") and len(search) > 1:
            raw_text = search[1:].strip()
            content, priority, tags, due_date = parse_chronos_input(raw_text)
            add_candidate(
                {
                    "score": 10000,
                    "title": f"📋 {content}",
                    "path": f"Mission • {priority} • {', '.join(tags) if tags else 'No tags'}",
                    "icon": "clock.svg",
                    "color": "#3b82f6",
                    "data": {
                        "type": "chronos_task",
                        "content": raw_text,
                        "parsed": {
                            "content": content,
                            "priority": priority,
                            "tags": tags,
                            "due_date": due_date,
                        },
                    },
                }
            )
            self.results_list.clear()
            self.results_tree.clear()
            self.populate_list_results(candidates)
            return

        # 0.1. DIRECT PATH DETECTION (e.g. C:\Windows or /etc/passwd)
        if raw_search and (
            raw_search.startswith("\\\\")
            or (
                len(raw_search) >= 2
                and raw_search[1] == ":"
                and raw_search[0].isalpha()
            )
            or (raw_search.startswith("/") and not raw_search.startswith("//"))
        ):
            is_dir = os.path.isdir(raw_search)
            if os.path.exists(raw_search):
                add_candidate(
                    {
                        "score": 5000,
                        "title": f"Open {'Folder' if is_dir else 'File'}: {os.path.basename(raw_search) or raw_search}",
                        "path": raw_search,
                        "icon": "folder.svg" if is_dir else "file.svg",
                        "file_path": raw_search,
                        "data": {"type": "file", "path": raw_search},
                    }
                )

        # 0.2. URL DETECTION
        url_pattern = re.compile(
            r"^(https?://)?"
            r"(([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
            r"(:\d+)?"
            r"(/.*)?$"
        )
        if (
            "." in raw_search
            or "localhost" in raw_search
            or raw_search.startswith("http")
        ) and url_pattern.match(raw_search):
            url = raw_search
            if not url.startswith("http"):
                url = "https://" + url
            add_candidate(
                {
                    "score": 4500,
                    "title": f"Open Web URL: {raw_search}",
                    "path": f"Browse to {url}",
                    "icon": "globe.svg",
                    "color": "#3b82f6",
                    "data": {"type": "url", "url": url},
                }
            )

        # Prefix logic
        prefixes = {
            ":b": "bookmarks",
            ":f": "files",
            ":p": "processes",
            ":t": "toggles",
            ":ssh": "ssh",
            ":s": "ssh",
            ":a": "apps",
        }
        active_modes = self.modes.copy()
        search_term = search

        for pref, mode_key in prefixes.items():
            if search.startswith(pref + " ") or search == pref:
                for k in active_modes:
                    if k in prefixes.values():
                        active_modes[k] = False
                active_modes[mode_key] = True
                search_term = search[len(pref) :].strip()
                break

        terms = [t for t in search_term.split() if t]

        # Footer hint
        if active_modes.get("processes"):
            self.status_lbl.setText(
                "Executioner Mode • Select and Press Enter to Finish It"
            )
            self.status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            self.status_lbl.setText("Nexus Engine Ready...")
            self.status_lbl.setStyleSheet("color: #6b7280;")

        # SSH Hosts
        if active_modes.get("ssh"):
            for host in self.ssh_hosts:
                if matches_all_terms(host, terms):
                    add_candidate(
                        {
                            "score": 980,
                            "title": f"SSH: {host}",
                            "path": f"Remote Node • ssh {host}",
                            "icon": "server.svg",
                            "data": {"type": "ssh", "host": host},
                        }
                    )

        # Apps
        if active_modes.get("apps"):
            for app in self.installed_apps:
                if matches_all_terms(app["name"], terms):
                    boost = self.get_usage_boost(app["path"])
                    add_candidate(
                        {
                            "score": 1000 + boost,
                            "title": app["name"],
                            "path": f"App • {app['path']}",
                            "file_path": app["path"],
                            "icon": "package.svg",
                            "data": {"type": "app", "path": app["path"]},
                        }
                    )

        # Frequent / Top Hits (When search is empty OR frequent mode active)
        if (not search and self.modes.get("frequent")) or active_modes.get("frequent"):
            f_type = None
            major_srcs = ["apps", "files", "toggles"]
            active_ones = [m for m in major_srcs if active_modes.get(m)]
            if len(active_ones) == 1:
                _map = {"apps": "app", "files": "file", "toggles": "cmd"}
                f_type = _map.get(active_ones[0])

            # Limit favorites when searching OR when an explicit filter is active
            # (default has apps + toggles active in major_srcs)
            is_filtered = len(active_ones) == 1
            fav_limit = 3 if (search or is_filtered) else 10
            frequent = self.get_frequent_candidates(limit=fav_limit, filter_type=f_type)

            # Determine display filtering terms (strip > if present)
            display_terms = (
                [t.strip(">") for t in terms]
                if (search.startswith(">") or active_modes.get("toggles"))
                else terms
            )

            for f_item in frequent:
                # If user typed something, filter favorites by matches too
                if display_terms and not matches_all_terms(
                    f_item["title"], display_terms
                ):
                    continue

                # Score them very high so they appear first
                # If searching, give them a high score but one that can be beaten by direct typed matches
                f_item["score"] = 5000 if not search else 1200
                add_candidate(f_item)

        # System Commands & Toggles
        if active_modes.get("toggles") or search.startswith(">"):
            score_base = 1100 if search.startswith(">") or not search else 500
            t_terms = [t.strip(">") for t in terms]

            mgmt_cmds = self.get_management_commands()
            for title, path, cmd, icon, color in mgmt_cmds:
                if not terms or matches_all_terms(title, t_terms):
                    add_candidate(
                        {
                            "score": score_base,
                            "title": title,
                            "path": f"System • {path}",
                            "icon": icon,
                            "color": color,
                            "data": {"type": "cmd", "cmd": cmd},
                        }
                    )

            power_commands = self.get_power_commands()
            for title, path, cmd, icon, keywords in power_commands:
                if (
                    not terms
                    or matches_all_terms(title, t_terms)
                    or any(matches_all_terms(kw, t_terms) for kw in keywords)
                ):
                    score = score_base - 10
                    if search_term and search_term in title.lower():
                        score += 500  # Stronger boost for typed hits
                    add_candidate(
                        {
                            "score": score,
                            "title": title,
                            "path": f"System › {path}",
                            "icon": icon,
                            "color": "#94a3b8",
                            "data": {"type": "cmd", "cmd": cmd},
                        }
                    )

        # Bookmarks
        if active_modes.get("bookmarks"):
            for b in self.browser_bookmarks:
                if (
                    not terms
                    or matches_all_terms(b["name"], terms)
                    or matches_all_terms(b["url"], terms)
                ):
                    add_candidate(
                        {
                            "score": 600,
                            "title": b["name"],
                            "path": b["url"],
                            "icon": "star.svg",
                            "color": "#fcd34d",
                            "data": {"type": "url", "url": b["url"]},
                        }
                    )

        # Processes
        is_explicit_process = search.startswith(":p")
        if active_modes.get("processes") and (terms or is_explicit_process):
            _update_procs(self)
            grouped = {}
            for p in self.process_cache:
                name = p["name"]
                if matches_all_terms(name, terms):
                    if name not in grouped:
                        grouped[name] = {
                            "count": 0,
                            "pids": [],
                            "mem_sum": 0,
                            "path": p["path"],
                            "desc": p["desc"],
                        }
                    # Use int() to satisfy type checking although it's redundant at runtime
                    grouped[name]["count"] = int(grouped[name]["count"]) + 1
                    grouped[name]["pids"].append(p["pid"])
                    grouped[name]["mem_sum"] = int(grouped[name]["mem_sum"]) + int(p["mem_bytes"])

            for name, info in grouped.items():
                mem_mb = info["mem_sum"] // 1024 // 1024
                desc_suff = f" • {info['desc']}" if info["desc"] else ""

                if info["count"] > 1:
                    add_candidate(
                        {
                            "score": 750
                            + (100 if name.lower().startswith(search_term) else 0),
                            "title": f"{name} ({info['count']} instances)",
                            "path": f"Total: {mem_mb} MB{desc_suff}",
                            "file_path": info["path"],
                            "icon": "power.svg",
                            "color": "#f87171",
                            "data": {"type": "process_kill_all", "name": name},
                        }
                    )

                limit_individuals = 1 if info["count"] > 3 else info["count"]
                for i in range(limit_individuals):
                    pid = info["pids"][i]
                    m_val = mem_mb if info["count"] == 1 else "?"
                    add_candidate(
                        {
                            "score": 700
                            + (100 if name.lower().startswith(search_term) else 0),
                            "title": name
                            if info["count"] == 1
                            else f"{name} (PID: {pid})",
                            "path": f"PID: {pid} • {m_val} MB{desc_suff}",
                            "file_path": info["path"],
                            "icon": "power.svg",
                            "color": "#ef4444",
                            "data": {"type": "process", "pid": pid, "name": name},
                        }
                    )

        # Web Search Fallback
        if search:
            web_query = search
            engine_url = "https://www.google.com/search?q="
            is_explicit = False

            if search.startswith("g ") and len(search) > 2:
                web_query = search[2:].strip()
                engine_url = "https://www.google.com/search?q="
                is_explicit = True
            elif search.startswith("b ") and len(search) > 2:
                web_query = search[2:].strip()
                engine_url = "https://www.bing.com/search?q="
                is_explicit = True
            elif search.startswith("yt ") and len(search) > 3:
                engine_url = "https://www.youtube.com/results?search_query="
                web_query = search[3:].strip()
                is_explicit = True

            q_url = engine_url + urllib.parse.quote_plus(web_query)
            add_candidate(
                {
                    "score": 100 if not is_explicit else 4000,
                    "title": f"Search Web: {web_query}",
                    "path": f"Open in browser • {engine_url}",
                    "icon": "globe.svg",
                    "data": {"type": "web_search", "url": q_url},
                }
            )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        # Keep a copy of the non-file candidates for the async file-search
        # callback to merge into (populate_list_results caps current_candidates).
        self._pre_file_candidates = list(candidates)
        if self.view_mode == "tree":
            self.populate_tree_results(candidates)
        else:
            self.populate_list_results(candidates)

    def get_management_commands(self):
        return [
            (
                "xexplorer - File Manager",
                "Modern explorer with fast search",
                "xexplorer",
                "xexplorer.png",
                "#3b82f6",
            ),
            (
                "Re-index Files (X-Explorer)",
                "Background re-index of search cache",
                "reindex_files",
                "refresh.svg",
                "#60a5fa",
            ),
            (
                "Regex Helper",
                "Offline Pattern Tester",
                "regex_helper",
                "regex_sandbox.png",
                "#f472b6",
            ),
            (
                "Color Picker",
                "Hex & RGB preview + color tool",
                "color_picker",
                "color_picker.png",
                "#8b5cf6",
            ),
            (
                "File Ops",
                "Fast copy • move • delete",
                "file_ops",
                "fileops.png",
                "#22c55e",
            ),
            (
                "Chronos Hub",
                "Achievement & Mission Tracker",
                "chronos_hub",
                "chronos.png",
                "#fbbf24",
            ),
            (
                "Archiver",
                "Zip • tar • 7z compress & extract",
                "archiver",
                "package.svg",
                "#a78bfa",
            ),
            (
                "Snip → Text (OCR)",
                "Select an area on screen and copy text to clipboard",
                "img_to_text",
                "ocr_icon.png",
                "#22c55e",
            ),
            (
                "Image → Text (OCR)",
                "Open file / drag-drop / paste image and extract text",
                "img_to_text_gui",
                "ocr_icon.png",
                "#34d399",
            ),
            (
                "Clipboard Manager",
                "Persistent multi-history clipboard with search & pin",
                "clipboard_manager",
                "clipboard_manager.png",
                "#f472b6",
            ),
            (
                "Port Inspector",
                "Real-time network ports · kill by PID",
                "port_inspector",
                "port_inspector.png",
                "#38bdf8",
            ),
            (
                "Hash Tool",
                "MD5 · SHA-1 · SHA-256 · SHA-512 hashing + Base64 encode/decode",
                "hash_tool",
                "hash_tool.png",
                "#a3e635",
            ),
            (
                "Ghost Typist",
                "Text expansion · snippets · macros",
                "ghost_typist",
                "ghost_typist.png",
                "#a855f7",
            ),
            (
                "SQLite Viewer",
                "Browse & query SQLite databases",
                "sqlite_viewer",
                "sqlite_viewer.png",
                "#0ea5e9",
            ),
        ]

    def get_power_commands(self):
        return [
            (
                "Toggle Nexus Theme (App Only)",
                "Theme",
                "toggle_nexus_theme",
                "moon.svg",
                ["dark", "light", "nexus", "app"],
            ),
            (
                "Toggle Windows Theme (System)",
                "Theme",
                "toggle_dark_mode",
                "moon.svg",
                ["dark", "light", "theme", "night", "system", "windows"],
            ),
            (
                "Toggle Hidden Files",
                "Explorer",
                "toggle_hidden_files",
                "eye.svg",
                ["hidden", "files", "view", "explorer"],
            ),
            (
                "Toggle Desktop Icons",
                "Desktop",
                "toggle_desktop_icons",
                "menu.svg",
                ["icons", "desktop", "shortcuts"],
            ),
            (
                "Toggle System Mute",
                "Audio",
                "toggle_mute",
                "eye.svg",
                ["mute", "audio", "volume", "sound"],
            ),
            (
                "Show / Hide Desktop",
                "Windows",
                "toggle_desktop",
                "file-axis-3d.svg",
                ["desktop", "reveal", "hide"],
            ),
            (
                "Restart Windows Explorer",
                "System",
                "restart_explorer",
                "refresh.svg",
                ["restart", "explorer", "refresh", "taskbar"],
            ),
            (
                "Flush DNS Cache",
                "Network",
                "flush_dns",
                "refresh.svg",
                ["dns", "flush", "network", "reset"],
            ),
            (
                "Switch Monitor -> DisplayPort",
                "Display",
                "cmd_monitor_dp",
                "monitor.svg",
                [
                    "displayport",
                    "dp",
                    "monitor",
                    "screen",
                    "display",
                    "input",
                    "source",
                ],
            ),
            (
                "Switch Monitor -> HDMI",
                "Display",
                "cmd_monitor_hdmi",
                "monitor.svg",
                ["hdmi", "monitor", "screen", "display", "input", "source"],
            ),
            (
                "Switch Monitor -> DVI",
                "Display",
                "cmd_monitor_dvi",
                "monitor.svg",
                ["dvi", "monitor", "screen", "display", "input", "source"],
            ),
            (
                "Display Mode -> PC Screen Only",
                "Display",
                "cmd_display_internal",
                "monitor.svg",
                ["display", "screen", "pc", "internal", "only"],
            ),
            (
                "Display Mode -> Duplicate",
                "Display",
                "cmd_display_clone",
                "monitor.svg",
                ["display", "screen", "duplicate", "clone", "mirror"],
            ),
            (
                "Display Mode -> Extend",
                "Display",
                "cmd_display_extend",
                "monitor.svg",
                ["display", "screen", "extend"],
            ),
            (
                "Display Mode -> Second Screen Only",
                "Display",
                "cmd_display_external",
                "monitor.svg",
                ["display", "screen", "second", "external", "only"],
            ),
            (
                "Lock Workstation",
                "Security",
                "cmd_lock",
                "arrow-right.svg",
                ["lock", "security", "sign out"],
            ),
            (
                "Put PC to Sleep",
                "Power",
                "cmd_sleep",
                "arrow-right.svg",
                ["sleep", "standby", "power"],
            ),
            (
                "Restart Computer",
                "Power",
                "cmd_restart",
                "refresh.svg",
                ["restart", "reboot", "power"],
            ),
            (
                "Shutdown System",
                "Power",
                "cmd_shutdown",
                "power.svg",
                ["shutdown", "power off", "exit"],
            ),
            (
                "Windows Settings",
                "ms-settings",
                "ms-settings:default",
                "arrow-right.svg",
                ["settings", "config", "windows"],
            ),
            (
                "Display Settings",
                "ms-settings",
                "ms-settings:display",
                "arrow-right.svg",
                ["display", "monitor", "resolution", "brightness"],
            ),
            (
                "Wi-Fi Settings",
                "ms-settings",
                "ms-settings:network-wifi",
                "arrow-right.svg",
                ["wifi", "internet", "wireless"],
            ),
        ]

    def get_frequent_candidates(self, limit=15, filter_type=None):
        """Build candidate objects for the top used items, optionally filtered by type."""
        if not hasattr(self, "usage_stats") or not self.usage_stats:
            return []

        sorted_stats = sorted(
            self.usage_stats.items(), key=lambda x: x[1], reverse=True
        )
        frequent_candidates = []

        mgmt_cmds = self.get_management_commands()
        power_cmds = self.get_power_commands()

        for key, _count in sorted_stats:
            if len(frequent_candidates) >= limit:
                break

            dtype = None
            if key.startswith("app_"):
                dtype = "app"
                path = key[4:]
            elif key.startswith("cmd_"):
                dtype = "cmd"
                cmd_id = key[4:]
            elif key.startswith("file_"):
                dtype = "file"
                path = key[5:]
            elif key.startswith("script_"):
                dtype = "script"
                path = key[7:]

            if filter_type and dtype != filter_type:
                continue

            if dtype == "app":
                app_data = next(
                    (a for a in self.installed_apps if a["path"] == path), None
                )
                if app_data:
                    frequent_candidates.append(
                        {
                            "score": 1,
                            "title": f"⭐️ {app_data['name']}",
                            "path": f"Frequent App • {path}",
                            "file_path": path,
                            "icon": "package.svg",
                            "data": {"type": "app", "path": path},
                        }
                    )
            elif dtype == "cmd":
                cmd_found = next((c for c in mgmt_cmds if c[2] == cmd_id), None)
                if not cmd_found:
                    cmd_found = next((c for c in power_cmds if c[2] == cmd_id), None)

                if cmd_found:
                    title, path_hint, _, icon, color_or_kws = cmd_found
                    color = color_or_kws if isinstance(color_or_kws, str) else "#94a3b8"
                    frequent_candidates.append(
                        {
                            "score": 1,
                            "title": f"⭐️ {title}",
                            "path": f"Frequent Cmd • {path_hint}",
                            "icon": icon,
                            "color": color,
                            "data": {"type": "cmd", "cmd": cmd_id},
                        }
                    )
            elif dtype == "file":
                if os.path.exists(path):
                    is_dir = os.path.isdir(path)
                    frequent_candidates.append(
                        {
                            "score": 1,
                            "title": f"⭐️ {os.path.basename(path)}",
                            "path": f"Frequent File • {path}",
                            "file_path": path,
                            "icon": "folder.svg" if is_dir else "file.svg",
                            "data": {"type": "file", "path": path},
                        }
                    )
            elif dtype == "script":
                if os.path.exists(path):
                    frequent_candidates.append(
                        {
                            "score": 1,
                            "title": f"⭐️ {os.path.basename(path)}",
                            "path": f"Frequent Script • {path}",
                            "file_path": path,
                            "icon": "terminal.svg",
                            "data": {"type": "script", "path": path},
                        }
                    )

        return frequent_candidates

    def perform_search_files(self):
        """Run the SQLite file search off the main thread and merge results in."""
        search = self.search_input.text().strip().lower()

        prefixes = {
            ":b": "bookmarks",
            ":f": "files",
            ":p": "processes",
            ":t": "toggles",
            ":ssh": "ssh",
            ":s": "ssh",
            ":a": "apps",
        }
        active_modes = self.modes.copy()
        search_term = search
        for pref, mode_key in prefixes.items():
            if search.startswith(pref + " ") or search == pref:
                for k in active_modes:
                    if k in prefixes.values():
                        active_modes[k] = False
                active_modes[mode_key] = True
                search_term = search[len(pref) :].strip()
                break

        if not active_modes.get("files"):
            return

        terms = [t for t in search_term.split() if t]
        files_only = active_modes.get("files_only", False)
        folders_only = active_modes.get("folders_only", False)
        target_folders = active_modes.get("target_folders", [])
        _gen = self._search_gen

        def _do_file_search(
            _terms=terms,
            _tf=target_folders,
            _fo=files_only,
            _fdo=folders_only,
            _st=search_term,
            _gen=_gen,
        ):
            try:
                # If search is empty, we return top 100 items from DB.
                # In empty state, we prioritize recently added or just first ones.
                results = self.search_engine.search_files(
                    query_terms=_terms,
                    target_folders=_tf,
                    files_only=_fo,
                    folders_only=_fdo,
                    limit=100,
                )
            except Exception:
                results = []

            file_candidates = []
            for f_path, is_dir, f_name, *_rest in results:
                # Base score for file results.
                # If search is empty, we give them enough score to be visible
                # but lower than frequent pinned items.
                score = 300 + (50 if is_dir else 0)

                if _st:
                    if f_name.lower() == _st:
                        score += 500
                    elif _st in f_name.lower():
                        score += 150

                score += self.get_usage_boost(f"file_{f_path}")

                icon = "folder.svg" if is_dir else "file.svg"
                if self._is_unc_path(f_path):
                    icon = "globe.svg"

                file_candidates.append(
                    {
                        "score": score,
                        "title": format_display_name(f_name),
                        "path": f_path,
                        "file_path": f_path,
                        "icon": icon,
                        "data": {"type": "file", "path": f_path},
                    }
                )

            self.file_search_finished.emit(file_candidates, _gen)

        threading.Thread(target=_do_file_search, daemon=True).start()

    def _handle_file_results(self, file_candidates, generation):
        """Main-thread callback to merge and display file search results."""
        if self._search_gen != generation:
            return

        # Merge with existing instant results (apps, bookmarks, etc)
        # _pre_file_candidates was saved in perform_search_instant
        pre_file = getattr(self, "_pre_file_candidates", [])

        # Deduplicate: if an item with the same path is already in pre_file,
        # skip it from file_candidates.
        seen_paths = set()
        for item in pre_file:
            path = item.get("data", {}).get("path")
            if path:
                seen_paths.add(path)

        unique_file_cands = []
        for item in file_candidates:
            path = item.get("data", {}).get("path")
            if path not in seen_paths:
                unique_file_cands.append(item)
                if path:
                    seen_paths.add(path)

        merged = list(pre_file) + unique_file_cands

        # Re-sort everything to ensure file hits are integrated properly by score
        merged.sort(key=lambda x: x["score"], reverse=True)

        self.results_list.clear()
        self.results_tree.clear()
        self.pending_icons.clear()

        if self.view_mode == "tree":
            self.populate_tree_results(merged)
        else:
            self.populate_list_results(merged)
