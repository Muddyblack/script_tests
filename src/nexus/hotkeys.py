import ctypes
import ctypes.wintypes as wt
import threading

from PyQt6.QtCore import QObject, pyqtSignal

# --------------------------------------------------------------------------
# Windows API setup
# --------------------------------------------------------------------------
_LRESULT = ctypes.c_longlong
_WndProc = ctypes.WINFUNCTYPE(_LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_HWND_MESSAGE = -3

_user32 = ctypes.windll.user32
_user32.DefWindowProcW.restype = _LRESULT
_user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.CreateWindowExW.restype = wt.HWND
_user32.CreateWindowExW.argtypes = [
    wt.DWORD,
    wt.LPCWSTR,
    wt.LPCWSTR,
    wt.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wt.HWND,
    wt.HMENU,
    wt.HINSTANCE,
    wt.LPVOID,
]
_user32.RegisterHotKey.restype = wt.BOOL
_user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]

_WM_HOTKEY = 0x0312
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_ALT = 0x0001
_MOD_WIN = 0x0008

_SPECIAL_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}


def _parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+q' into (modifiers, vk_code) for RegisterHotKey."""
    mods = 0
    vk = 0
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if part in ("ctrl", "control"):
            mods |= _MOD_CONTROL
        elif part == "shift":
            mods |= _MOD_SHIFT
        elif part == "alt":
            mods |= _MOD_ALT
        elif part in ("win", "windows"):
            mods |= _MOD_WIN
        elif part in _SPECIAL_KEYS:
            vk = _SPECIAL_KEYS[part]
        elif len(part) == 1:
            vk = ord(part.upper())
    return mods, vk


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", _WndProc),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class _HotkeyWindow(QObject):
    """Message-only window that uses RegisterHotKey.

    Unlike WH_KEYBOARD_LL hooks, RegisterHotKey hotkeys survive screen
    lock / hibernate / resume without any re-registration.
    """

    toggle_signal = pyqtSignal()
    ocr_signal = pyqtSignal()

    _TOGGLE_ID = 1
    _OCR_ID = 2

    def start(self, toggle_hotkey: str, ocr_hotkey: str):
        self._toggle_mods, self._toggle_vk = _parse_hotkey(toggle_hotkey)
        self._ocr_mods, self._ocr_vk = _parse_hotkey(ocr_hotkey)
        threading.Thread(target=self._run, daemon=True, name="HotkeyWindow").start()

    def _run(self):
        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == _WM_HOTKEY:
                if wparam == self._TOGGLE_ID:
                    self.toggle_signal.emit()
                elif wparam == self._OCR_ID:
                    self.ocr_signal.emit()
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = _WndProc(wnd_proc)

        wc = WNDCLASSW()
        wc.lpfnWndProc = proc
        wc.lpszClassName = "NexusHotkeyWindow"
        if not _user32.RegisterClassW(ctypes.byref(wc)):
            print(f"[HotkeyWindow] RegisterClassW failed: {ctypes.GetLastError()}")
            return

        hwnd = _user32.CreateWindowExW(
            0,
            "NexusHotkeyWindow",
            None,
            0,
            0,
            0,
            0,
            0,
            wt.HWND(_HWND_MESSAGE),
            None,
            None,
            None,
        )
        if not hwnd:
            print(f"[HotkeyWindow] CreateWindowExW failed: {ctypes.GetLastError()}")
            return

        if not _user32.RegisterHotKey(
            hwnd, self._TOGGLE_ID, self._toggle_mods, self._toggle_vk
        ):
            print(
                f"[HotkeyWindow] RegisterHotKey (toggle) failed: {ctypes.GetLastError()}"
            )
        if not _user32.RegisterHotKey(hwnd, self._OCR_ID, self._ocr_mods, self._ocr_vk):
            print(
                f"[HotkeyWindow] RegisterHotKey (ocr) failed: {ctypes.GetLastError()}"
            )

        msg = wt.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
