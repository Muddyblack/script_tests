"""Search-logic mixin — perform_search and helpers."""

import os
import re
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
        raw_search = self.search_input.text().strip()
        search = raw_search.lower()
        self.results_list.clear()
        self.results_tree.clear()
        self.pending_icons.clear()
        candidates = []

        def matches_all_terms(text, terms):
            if not terms:
                return True
            tl = text.lower()
            return all(t in tl for t in terms)

        # 0. CHRONOS QUICK-LOG (Achievement)
        if search.startswith("+") and len(search) > 1:
            raw_text = search[1:].strip()
            content, priority, tags, due_date = parse_chronos_input(raw_text)
            candidates.append(
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
            candidates.append(
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

        # 0.1. EXACT PATH DETECTION
        if os.path.exists(raw_search) and (
            os.path.isabs(raw_search)
            or (len(raw_search) > 2 and raw_search[1:3] == ":\\")
        ):
            is_dir = os.path.isdir(raw_search)
            candidates.append(
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
            url_pattern.match(raw_search)
            and ("." in raw_search or "localhost" in raw_search.lower())
            and not os.path.exists(raw_search)
        ):
            url = raw_search
            if not url.lower().startswith("http"):
                url = "https://" + url
            candidates.append(
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
                search_term = search[len(pref):].strip()
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
                    candidates.append(
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
                    candidates.append(
                        {
                            "score": 1000 + boost,
                            "title": app["name"],
                            "path": f"App • {app['path']}",
                            "file_path": app["path"],
                            "icon": "package.svg",
                            "data": {"type": "app", "path": app["path"]},
                        }
                    )

        # System Commands & Toggles
        if active_modes.get("toggles") or search.startswith(">"):
            score_base = 1100 if search.startswith(">") or not search else 500
            t_terms = [t.strip(">") for t in terms]

            mgmt_cmds = [
                ("xexplorer - File Manager", "Modern explorer with fast search", "xexplorer", "xexplorer.png", "#3b82f6"),
                ("Re-index Files (X-Explorer)", "Background re-index of search cache", "reindex_files", "refresh.svg", "#60a5fa"),
                ("Regex Helper", "Offline Pattern Tester", "regex_helper", "regex_sandbox.png", "#f472b6"),
                ("Color Picker", "Hex & RGB preview + color tool", "color_picker", "color_picker.png", "#8b5cf6"),
                ("File Ops", "Fast copy • move • delete", "file_ops", "fileops.png", "#22c55e"),
                ("Chronos Hub", "Achievement & Mission Tracker", "chronos_hub", "chronos.png", "#fbbf24"),
                ("Archiver", "Zip • tar • 7z compress & extract", "archiver", "package.svg", "#a78bfa"),
                ("Snip → Text (OCR)", "Select an area on screen and copy text to clipboard", "img_to_text", "ocr_icon.png", "#22c55e"),
                ("Image → Text (OCR)", "Open file / drag-drop / paste image and extract text", "img_to_text_gui", "ocr_icon.png", "#34d399"),
                ("Clipboard Manager", "Persistent multi-history clipboard with search & pin", "clipboard_manager", "clipboard_manager.png", "#f472b6"),
                ("Port Inspector", "Real-time network ports · kill by PID", "port_inspector", "port_inspector.png", "#38bdf8"),
                ("Hash Tool", "MD5 · SHA-1 · SHA-256 · SHA-512 hashing + Base64 encode/decode", "hash_tool", "hash_tool.png", "#a3e635"),
                ("Ghost Typist", "Text expansion · snippets · macros", "ghost_typist", "ghost_typist.png", "#a855f7"),
                ("SQLite Viewer", "Browse & query SQLite databases", "sqlite_viewer", "sqlite_viewer.png", "#0ea5e9"),
            ]
            for title, path, cmd, icon, color in mgmt_cmds:
                if not terms or matches_all_terms(title, t_terms):
                    candidates.append(
                        {
                            "score": score_base,
                            "title": title,
                            "path": f"System • {path}",
                            "icon": icon,
                            "color": color,
                            "data": {"type": "cmd", "cmd": cmd},
                        }
                    )

            power_commands = [
                ("Toggle Nexus Theme (App Only)", "Theme", "toggle_nexus_theme", "moon.svg", ["dark", "light", "nexus", "app"]),
                ("Toggle Windows Theme (System)", "Theme", "toggle_dark_mode", "moon.svg", ["dark", "light", "theme", "night", "system", "windows"]),
                ("Toggle Hidden Files", "Explorer", "toggle_hidden_files", "eye.svg", ["hidden", "files", "view", "explorer"]),
                ("Toggle Desktop Icons", "Desktop", "toggle_desktop_icons", "menu.svg", ["icons", "desktop", "shortcuts"]),
                ("Toggle System Mute", "Audio", "toggle_mute", "eye.svg", ["mute", "audio", "volume", "sound"]),
                ("Show / Hide Desktop", "Windows", "toggle_desktop", "file-axis-3d.svg", ["desktop", "reveal", "hide"]),
                ("Restart Windows Explorer", "System", "restart_explorer", "refresh.svg", ["restart", "explorer", "refresh", "taskbar"]),
                ("Flush DNS Cache", "Network", "flush_dns", "refresh.svg", ["dns", "flush", "network", "reset"]),
                ("Lock Workstation", "Security", "cmd_lock", "arrow-right.svg", ["lock", "security", "sign out"]),
                ("Put PC to Sleep", "Power", "cmd_sleep", "arrow-right.svg", ["sleep", "standby", "power"]),
                ("Restart Computer", "Power", "cmd_restart", "refresh.svg", ["restart", "reboot", "power"]),
                ("Shutdown System", "Power", "cmd_shutdown", "power.svg", ["shutdown", "power off", "exit"]),
                ("Windows Settings", "ms-settings", "ms-settings:default", "arrow-right.svg", ["settings", "config", "windows"]),
                ("Display Settings", "ms-settings", "ms-settings:display", "arrow-right.svg", ["display", "monitor", "resolution", "brightness"]),
                ("Wi-Fi Settings", "ms-settings", "ms-settings:network-wifi", "arrow-right.svg", ["wifi", "internet", "wireless"]),
            ]
            for title, path, cmd, icon, keywords in power_commands:
                if (
                    not terms
                    or matches_all_terms(title, t_terms)
                    or any(matches_all_terms(kw, t_terms) for kw in keywords)
                ):
                    score = score_base - 10
                    if search_term and search_term in title.lower():
                        score += 150
                    candidates.append(
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
                    candidates.append(
                        {
                            "score": 600,
                            "title": b["name"],
                            "path": b["url"],
                            "icon": "star.svg",
                            "color": "#fcd34d",
                            "data": {"type": "url", "url": b["url"]},
                        }
                    )

        # File Search
        if active_modes.get("files"):
            files_only = active_modes.get("files_only", False)
            folders_only = active_modes.get("folders_only", False)
            target_folders = active_modes.get("target_folders", [])

            results = self.search_engine.search_files(
                query_terms=terms,
                target_folders=target_folders,
                files_only=files_only,
                folders_only=folders_only,
                limit=100,
            )

            for f_path, is_dir, f_name in results:
                score = 200 + (50 if is_dir else 0)
                if search_term and f_name.lower() == search_term:
                    score += 500
                score += self.get_usage_boost(f"file_{f_path}")

                icon = (
                    "globe.svg"
                    if self._is_unc_path(f_path)
                    else "folder.svg"
                    if is_dir
                    else "file.svg"
                )

                candidates.append(
                    {
                        "score": score,
                        "title": format_display_name(f_name),
                        "path": f_path,
                        "file_path": f_path,
                        "icon": icon,
                        "data": {"type": "file", "path": f_path},
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
                    grouped[name]["count"] += 1
                    grouped[name]["pids"].append(p["pid"])
                    grouped[name]["mem_sum"] += p["mem_bytes"]

            for name, info in grouped.items():
                mem_mb = info["mem_sum"] // 1024 // 1024
                desc_suff = f" • {info['desc']}" if info["desc"] else ""

                if info["count"] > 1:
                    candidates.append(
                        {
                            "score": 750 + (100 if name.lower().startswith(search_term) else 0),
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
                    candidates.append(
                        {
                            "score": 700 + (100 if name.lower().startswith(search_term) else 0),
                            "title": name if info["count"] == 1 else f"{name} (PID: {pid})",
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
                is_explicit = True
            elif search.startswith("b ") and len(search) > 2:
                engine_url = "https://www.bing.com/search?q="
                web_query = search[2:].strip()
                is_explicit = True
            elif search.startswith("yt ") and len(search) > 3:
                engine_url = "https://www.youtube.com/results?search_query="
                web_query = search[3:].strip()
                is_explicit = True

            if is_explicit or not candidates:
                encoded_query = urllib.parse.quote(web_query)
                candidates.append(
                    {
                        "score": 6000 if is_explicit else 300,
                        "title": f"Web Search: {web_query}",
                        "path": f"Search online • {web_query}",
                        "icon": "globe.svg",
                        "color": "#3b82f6",
                        "data": {"type": "url", "url": engine_url + encoded_query},
                    }
                )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        if self.view_mode == "tree":
            self.populate_tree_results(candidates)
        else:
            self.populate_list_results(candidates)
