"""Data-loading mixin — apps, SSH, bookmarks, settings, usage, search history."""

import glob
import json
import os
import time

from src.common.config import (
    APPS_CACHE_FILE,
    SEARCH_HISTORY_FILE,
    SETTINGS_FILE,
    USAGE_FILE,
)


class _DataMixin:
    # ------------------------------------------------------------------
    # App scanning
    # ------------------------------------------------------------------
    def load_apps_cache(self):
        if os.path.exists(APPS_CACHE_FILE):
            try:
                with open(APPS_CACHE_FILE) as f:
                    self.installed_apps = json.load(f)
            except Exception:
                pass

    def scan_installed_apps_bg(self):
        time.sleep(2)
        self.scan_installed_apps()
        try:
            with open(APPS_CACHE_FILE, "w") as f:
                json.dump(self.installed_apps, f)
        except Exception:
            pass

    def scan_installed_apps(self):
        """Scan Windows Start Menu and Desktop for application shortcuts."""
        paths = [
            os.path.join(
                os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
                r"Microsoft\Windows\Start Menu",
            ),
            os.path.join(
                os.environ.get("APPDATA", ""),
                r"Microsoft\Windows\Start Menu",
            ),
            os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        ]
        apps = []
        for p in paths:
            if not os.path.exists(p):
                continue
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        name = f.rsplit(".", 1)[0]
                        apps.append({"name": name, "path": os.path.join(root, f)})
        self.installed_apps = apps

    # ------------------------------------------------------------------
    # SSH hosts
    # ------------------------------------------------------------------
    def scan_ssh_hosts(self):
        """Parse ~/.ssh/config for SSH sessions."""
        self.ssh_hosts = []
        ssh_config = os.path.expanduser("~/.ssh/config")
        if os.path.exists(ssh_config):
            try:
                with open(ssh_config) as f:
                    for line in f:
                        line = line.strip()
                        if line.lower().startswith("host ") and "*" not in line:
                            host = line.split(" ", 1)[1].strip()
                            if host:
                                self.ssh_hosts.append(host)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------
    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.modes.update(
                            {k: v for k, v in data.items() if k not in ("light_mode",)}
                        )
        except Exception:
            pass

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.modes, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------
    def load_usage(self):
        try:
            if os.path.exists(USAGE_FILE):
                with open(USAGE_FILE) as f:
                    self.usage_stats = json.load(f)
        except Exception:
            self.usage_stats = {}

    def record_usage(self, key):
        """Increment usage count."""
        count = self.usage_stats.get(key, 0) + 1
        self.usage_stats[key] = count

        # Prevent runaway growth: if we track too many things,
        # keep only the top 1000 most used items.
        if len(self.usage_stats) > 1500:
            sorted_usage = sorted(
                self.usage_stats.items(), key=lambda x: x[1], reverse=True
            )[:1000]
            self.usage_stats = dict(sorted_usage)

        try:
            with open(USAGE_FILE, "w") as f:
                json.dump(self.usage_stats, f)
        except Exception:
            pass

    def remove_usage(self, key):
        """Remove an item from usage statistics."""
        if key in self.usage_stats:
            del self.usage_stats[key]
            try:
                with open(USAGE_FILE, "w") as f:
                    json.dump(self.usage_stats, f)
            except Exception:
                pass

    def get_usage_boost(self, key):
        """Score boost based on usage frequency."""
        count = self.usage_stats.get(key, 0)
        return min(count * 50, 600)

    # ------------------------------------------------------------------
    # Search history (raw text)
    # ------------------------------------------------------------------
    def load_search_history(self):
        try:
            if os.path.exists(SEARCH_HISTORY_FILE):
                with open(SEARCH_HISTORY_FILE) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.search_history = data
        except Exception:
            self.search_history = []

    def record_search(self, raw_text):
        """Save a search string to history to enable autocomplete."""
        text = raw_text.strip()
        if not text:
            return
        if text in self.search_history:
            self.search_history.remove(text)
        self.search_history.insert(0, text)
        self.search_history = self.search_history[:100]
        try:
            with open(SEARCH_HISTORY_FILE, "w") as f:
                json.dump(self.search_history, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Browser Bookmarks
    # ------------------------------------------------------------------
    def load_browser_bookmarks(self):
        self.browser_bookmarks = []
        paths = []
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    r"Google\Chrome\User Data\*\Bookmarks",
                )
            )
        )
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    r"Microsoft\Edge\User Data\*\Bookmarks",
                )
            )
        )
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    r"BraveSoftware\Brave-Browser\User Data\*\Bookmarks",
                )
            )
        )
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("APPDATA", ""),
                    r"Mozilla\Firefox\Profiles\*\bookmarkbackups",
                )
            )
        )

        def extract_urls(node):
            if isinstance(node, dict):
                if node.get("type") == "url":
                    self.browser_bookmarks.append(
                        {
                            "name": node.get("name", "Unnamed Bookmark"),
                            "url": node.get("url", ""),
                        }
                    )
                elif "children" in node:
                    for child in node.get("children", []):
                        extract_urls(child)

        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                        roots = data.get("roots", {})
                        for key in roots:
                            extract_urls(roots[key])
                except Exception:
                    pass

        seen = set()
        unique = []
        for b in self.browser_bookmarks:
            if b["url"] not in seen:
                seen.add(b["url"])
                unique.append(b)
        self.browser_bookmarks = unique
