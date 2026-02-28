"""Auto-split module."""




try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False



class Theme:
    DARK = {
        "name": "dark",
        # Surfaces
        "bg_base":        "#131920",
        "bg_elevated":    "#1a2230",
        "bg_overlay":     "#1e2840",
        "bg_control":     "#1e2840",
        "bg_control_hov": "#253050",
        "bg_control_prs": "#0f1520",
        # Accents – teal
        "accent":         "#00d4a8",
        "accent_hover":   "#00e8b8",
        "accent_pressed": "#00b890",
        "accent_subtle":  "#00d4a815",
        # Borders
        "border":         "#253050",
        "border_light":   "#304060",
        "border_focus":   "#00d4a8",
        # Text
        "text_primary":   "#e8f0f8",
        "text_secondary": "#7a9ab5",
        "text_disabled":  "#3a5070",
        "text_on_accent": "#0a1020",
        # Semantic
        "sel_bg":         "#00d4a830",
        "sel_bg_unfocus": "#1e3050",
        "row_alt":        "#161f2d",
        "icon_folder":    "#00d4a8",
        "icon_file":      "#7aa0c8",
        "icon_code":      "#7ec8a0",
        "icon_media":     "#c8a0e8",
        "icon_archive":   "#e8b870",
        "success":        "#00d4a8",
        "danger":         "#f47174",
        "warning":        "#f0c040",
        # Sidebar
        "sidebar_bg":     "#0f1520",
        "sidebar_item":   "#0f1520",
        "sidebar_hover":  "#1a2230",
        "sidebar_sel":    "#00d4a820",
        "sidebar_sel_bar":"#00d4a8",
        # Tab bar
        "tab_bg":         "#131920",
        "tab_active":     "#1a2230",
        "tab_hover":      "#161f2d",
    }

    LIGHT = {
        "name": "light",
        "bg_base":        "#f3f3f3",
        "bg_elevated":    "#ffffff",
        "bg_overlay":     "#f9f9f9",
        "bg_control":     "#efefef",
        "bg_control_hov": "#e5e5e5",
        "bg_control_prs": "#d9d9d9",
        "accent":         "#0078d4",
        "accent_hover":   "#006cbf",
        "accent_pressed": "#005ba1",
        "accent_subtle":  "#0078d412",
        "border":         "#e0e0e0",
        "border_light":   "#d0d0d0",
        "border_focus":   "#0078d4",
        "text_primary":   "#1a1a1a",
        "text_secondary": "#5d5d5d",
        "text_disabled":  "#aaaaaa",
        "text_on_accent": "#ffffff",
        "sel_bg":         "#cde6f7",
        "sel_bg_unfocus": "#e5e5e5",
        "row_alt":        "#fafafa",
        "icon_folder":    "#dcb850",
        "icon_file":      "#4a8bbf",
        "icon_code":      "#3a9a60",
        "icon_media":     "#9050c8",
        "icon_archive":   "#c08030",
        "success":        "#107c10",
        "danger":         "#c42b1c",
        "warning":        "#9d5d00",
        "sidebar_bg":     "#f3f3f3",
        "sidebar_item":   "#f3f3f3",
        "sidebar_hover":  "#e8e8e8",
        "sidebar_sel":    "#cde6f720",
        "sidebar_sel_bar":"#0078d4",
        "tab_bg":         "#ebebeb",
        "tab_active":     "#f9f9f9",
        "tab_hover":      "#f0f0f0",
    }

    def __init__(self, dark=True):
        self._t = self.DARK.copy() if dark else self.LIGHT.copy()
        self.dark = dark

    def __getitem__(self, key):
        return self._t[key]

    def toggle(self):
        self.dark = not self.dark
        self._t = self.DARK.copy() if self.dark else self.LIGHT.copy()


