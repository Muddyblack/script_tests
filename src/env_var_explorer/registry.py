"""Windows Registry helpers for reading/writing environment variables."""

import ctypes
import winreg

_USER_REG = r"Environment"
_SYS_REG = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def read_user_vars() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _USER_REG, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(key, i)
                out[name] = val
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return out


def read_system_vars() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SYS_REG, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(key, i)
                out[name] = val
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return out


def write_user_var(name: str, value: str) -> None:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _USER_REG, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ
    )
    reg_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
    winreg.SetValueEx(key, name, 0, reg_type, value)
    winreg.CloseKey(key)


def delete_user_var(name: str) -> None:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _USER_REG, 0, winreg.KEY_SET_VALUE)
    winreg.DeleteValue(key, name)
    winreg.CloseKey(key)


def write_system_var(name: str, value: str) -> None:
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, _SYS_REG, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ
    )
    reg_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
    winreg.SetValueEx(key, name, 0, reg_type, value)
    winreg.CloseKey(key)


def delete_system_var(name: str) -> None:
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SYS_REG, 0, winreg.KEY_SET_VALUE)
    winreg.DeleteValue(key, name)
    winreg.CloseKey(key)


def broadcast_env_change() -> None:
    """Notify all windows that environment variables changed."""
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        res = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(res),
        )
    except Exception:
        pass
