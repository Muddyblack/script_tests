import subprocess
import sys


def set_monitor_input(source: str, target_index: int | None = None) -> None:
    """
    Switch all physical monitors to the given input source.
    source: "dp" for DisplayPort, "hdmi" for HDMI, "dvi" for DVI, "vga" for VGA.
    """
    mapping = {"dp": 15, "hdmi": 17, "dvi": 3, "vga": 1}

    val = mapping.get(source.lower())
    if val is None:
        raise ValueError(f"Unknown input source: {source}")

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        dxva2 = ctypes.windll.dxva2

        class PHYSICAL_MONITOR(ctypes.Structure):
            _fields_ = [
                ("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", wintypes.WCHAR * 128),
            ]

        current_idx = [0]

        def _monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
            num_physical = wintypes.DWORD()
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                hMonitor, ctypes.byref(num_physical)
            ):
                return True

            if num_physical.value > 0:
                physical_monitors = (PHYSICAL_MONITOR * num_physical.value)()
                if dxva2.GetPhysicalMonitorsFromHMONITOR(
                    hMonitor, num_physical.value, physical_monitors
                ):
                    for pm in physical_monitors:
                        current_idx[0] += 1
                        if target_index is None or target_index == current_idx[0]:
                            dxva2.SetVCPFeature(pm.hPhysicalMonitor, 0x60, val)

                    # Important to destroy the handles
                    dxva2.DestroyPhysicalMonitors(num_physical.value, physical_monitors)

            return True

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.LPARAM,
        )

        cb_func = MonitorEnumProc(_monitor_enum_proc)
        user32.EnumDisplayMonitors(None, None, cb_func, 0)

    else:
        # Unix/Linux using ddcutil
        import shutil
        import threading

        if not shutil.which("ddcutil"):
            raise FileNotFoundError(
                "ddcutil is required on Linux to switch monitor inputs. Please install it."
            )

        def _run_ddc():
            for idx in range(1, 4):
                if target_index is None or target_index == idx:
                    subprocess.run(
                        ["ddcutil", "setvcp", "60", str(val), "--display", str(idx)],
                        capture_output=True,
                    )

        threading.Thread(target=_run_ddc, daemon=True).start()
