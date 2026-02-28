"""Theme wrapper for X-Explorer."""

from src.common.theme import ThemeManager


class Theme:
    """Legacy wrapper for ThemeManager used by X-Explorer."""

    def __init__(self, dark=True):
        self.mgr = ThemeManager()
        # Optionally switch theme based on 'dark' argument if needed
        # but the manager handles shared settings now.
        pass

    @property
    def dark(self):
        return self.mgr.is_dark

    @dark.setter
    def dark(self, value):
        # Allow legacy dark=True/False to still work?
        # For now, it might be better to just let it toggle via manager.
        pass

    def __getitem__(self, key):
        # Redirect all color lookups to the manager
        return self.mgr[key]

    def toggle(self):
        # This could switch between 'dark' and 'light' themes in the themes/ folder
        current = self.mgr.current_theme_name
        if "light" in current.lower():
            self.mgr.load_theme("midnight-marina")
        else:
            self.mgr.load_theme("light")  # if light folder exists
        self.mgr.theme_changed.emit()

    def copy(self):
        return self  # Not really copying but works for current usage
