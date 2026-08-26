"""Win32 window matching, focus, zen mode, tiling, and workspace presets."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from tars.skills.system import APP_ALIASES, open_app

_TARS_TITLES = {"tars"}
_SKIP_CLASSES = {
    "progman",
    "workerw",
    "shell_traywnd",
    "shell_secondarytraywnd",
    "notifyiconoverflowwindow",
    "windows.ui.core.corewindow",
}
_SKIP_TITLES = {
    "program manager",
    "windows input experience",
    "microsoft text input application",
}

# Extra title/exe needles so "vscode" matches Code.exe / "Visual Studio Code".
_APP_NEEDLES: dict[str, tuple[str, ...]] = {
    "vscode": ("visual studio code", "code.exe", "vscode"),
    "vs code": ("visual studio code", "code.exe", "vscode"),
    "visual studio code": ("visual studio code", "code.exe", "vscode"),
    "code": ("visual studio code", "code.exe"),
    "chrome": ("google chrome", "chrome.exe", "chrome"),
    "google chrome": ("google chrome", "chrome.exe"),
    "edge": ("microsoft edge", "msedge.exe", "edge"),
    "msedge": ("microsoft edge", "msedge.exe"),
    "firefox": ("mozilla firefox", "firefox.exe", "firefox"),
    "notepad": ("notepad", "notepad.exe"),
    "calculator": ("calculator", "calc.exe"),
    "calc": ("calculator", "calc.exe"),
    "explorer": ("file explorer", "explorer.exe"),
    "emulator": ("android emulator", "qemu", "emulator.exe", "emulator"),
    "pdf": ("adobe acrobat", "acrobat.exe", ".pdf"),
    "acrobat": ("adobe acrobat", "acrobat.exe"),
}


def _win32():
    """Import pywin32 lazily so missing installs become tool errors, not import crashes."""
    if sys.platform != "win32":
        raise RuntimeError("Window management is only available on Windows.")
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is not installed. Run: pip install pywin32"
        ) from exc
    return win32gui, win32con, win32process, win32api


def _needles(target_name: str) -> list[str]:
    raw = (target_name or "").strip().lower()
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in (raw, APP_ALIASES.get(raw, ""), *_APP_NEEDLES.get(raw, ())):
        token = (item or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
        stem = Path(token).stem.lower()
        if stem and stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def _window_title(hwnd: int) -> str:
    win32gui, *_ = _win32()
    try:
        return win32gui.GetWindowText(hwnd) or ""
    except Exception:  # noqa: BLE001
        return ""


def _window_class(hwnd: int) -> str:
    win32gui, *_ = _win32()
    try:
        return (win32gui.GetClassName(hwnd) or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _process_exe(hwnd: int) -> str:
    """Return the executable basename for a window, or ''."""
    win32gui, win32con, win32process, win32api = _win32()
    handle = None
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return ""
        access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
        try:
            handle = win32api.OpenProcess(access, False, pid)
        except Exception:  # noqa: BLE001
            handle = win32api.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        try:
            path = win32process.GetModuleFileNameEx(handle, 0)
        except Exception:  # noqa: BLE001
            import ctypes

            buf = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(32768)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                int(handle), 0, buf, ctypes.byref(size)
            )
            path = buf.value if ok else ""
        return Path(path).name.lower() if path else ""
    except Exception:  # noqa: BLE001
        return ""
    finally:
        if handle:
            try:
                win32api.CloseHandle(handle)
            except Exception:  # noqa: BLE001
                pass


def _is_visible_top_level(hwnd: int) -> bool:
    win32gui, *_ = _win32()
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
    except Exception:  # noqa: BLE001
        return False
    return True


def _is_system_or_tars(hwnd: int) -> bool:
    title = _window_title(hwnd).strip().lower()
    cls = _window_class(hwnd)
    if title in _TARS_TITLES or title in _SKIP_TITLES:
        return True
    if cls in _SKIP_CLASSES:
        return True
    if cls in {"shell_traywnd", "shell_secondarytraywnd"}:
        return True
    return False


def _matches(hwnd: int, needles: list[str]) -> bool:
    title = _window_title(hwnd).lower()
    exe = _process_exe(hwnd)
    haystacks = (title, exe, Path(exe).stem)
    return any(n and n in hay for n in needles for hay in haystacks)


def _window_area(hwnd: int) -> int:
    win32gui, *_ = _win32()
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return max(0, right - left) * max(0, bottom - top)
    except Exception:  # noqa: BLE001
        return 0


def find_window_by_name(target_name: str) -> int | None:
    """Return the best visible top-level hwnd matching title or process name."""
    needles = _needles(target_name)
    if not needles:
        return None
    win32gui, *_ = _win32()
    scored: list[tuple[tuple[int, int, int], int]] = []

    def _enum(hwnd: int, _extra: object) -> bool:
        if not _is_visible_top_level(hwnd):
            return True
        if _is_system_or_tars(hwnd):
            return True
        if not _matches(hwnd, needles):
            return True
        title = _window_title(hwnd).lower()
        exe = _process_exe(hwnd)
        exact = 1 if any(n in {title, exe, Path(exe).stem} for n in needles) else 0
        restored = 0 if win32gui.IsIconic(hwnd) else 1
        scored.append(((exact, restored, _window_area(hwnd)), hwnd))
        return True

    win32gui.EnumWindows(_enum, None)
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _wait_for_window(app_name: str, timeout_s: float = 4.0) -> int | None:
    deadline = time.time() + timeout_s
    hwnd = find_window_by_name(app_name)
    while hwnd is None and time.time() < deadline:
        time.sleep(0.2)
        hwnd = find_window_by_name(app_name)
    return hwnd


def _ensure_hwnd(app_name: str, *, launch: bool) -> tuple[int | None, str]:
    raw = (app_name or "").strip()
    if not raw:
        return None, "Error: app name is empty."
    hwnd = find_window_by_name(raw)
    if hwnd:
        return hwnd, ""
    if not launch:
        return None, f"Error: no visible window matching '{raw}'."
    launched = open_app(raw)
    if launched.startswith("Error") or launched.startswith("Failed"):
        return None, launched
    time.sleep(0.5)
    hwnd = _wait_for_window(raw, timeout_s=4.0)
    if hwnd is None:
        return None, f"Launched '{raw}' but no window appeared yet. {launched}"
    return hwnd, launched


def _force_foreground(hwnd: int) -> None:
    """Restore if minimized and steal foreground focus via AttachThreadInput."""
    import ctypes

    win32gui, win32con, win32process, win32api = _win32()
    user32 = ctypes.windll.user32

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    try:
        user32.AllowSetForegroundWindow(0xFFFFFFFF)
    except Exception:  # noqa: BLE001
        pass

    fg = win32gui.GetForegroundWindow()
    cur_tid = int(win32api.GetCurrentThreadId())
    fg_tid = 0
    tgt_tid = 0
    try:
        if fg:
            fg_tid, _ = win32process.GetWindowThreadProcessId(fg)
        tgt_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:  # noqa: BLE001
        pass

    attached_fg = False
    attached_tgt = False
    try:
        if fg_tid and fg_tid != cur_tid:
            attached_fg = bool(user32.AttachThreadInput(cur_tid, int(fg_tid), True))
        if tgt_tid and tgt_tid != cur_tid and tgt_tid != fg_tid:
            attached_tgt = bool(user32.AttachThreadInput(cur_tid, int(tgt_tid), True))
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:  # noqa: BLE001
            user32.SetForegroundWindow(int(hwnd))
    finally:
        if attached_tgt:
            user32.AttachThreadInput(cur_tid, int(tgt_tid), False)
        if attached_fg:
            user32.AttachThreadInput(cur_tid, int(fg_tid), False)


def _screen_metrics() -> tuple[int, int, int, int]:
    """Return (left, top, width, height); prefer work area, fall back to metrics 0/1."""
    _win32gui, _win32con, _win32process, win32api = _win32()
    cx = int(win32api.GetSystemMetrics(0))
    cy = int(win32api.GetSystemMetrics(1))
    try:
        info = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))
        left, top, right, bottom = info["Work"]
        return int(left), int(top), int(right - left), int(bottom - top)
    except Exception:  # noqa: BLE001
        return 0, 0, cx, cy


def _restore(hwnd: int) -> None:
    win32gui, win32con, *_ = _win32()
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)


def _move(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    win32gui, *_ = _win32()
    _restore(hwnd)
    win32gui.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)


def _first_existing(*names: str) -> tuple[int | None, str]:
    for name in names:
        hwnd = find_window_by_name(name)
        if hwnd:
            return hwnd, name
    return None, names[0] if names else ""


def bring_to_front(app_name: str) -> str:
    """Restore a matching window if minimized and force it to the foreground."""
    try:
        hwnd, err = _ensure_hwnd(app_name, launch=False)
        if hwnd is None:
            return err
        _force_foreground(hwnd)
        return f"Brought {app_name} to the front."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to bring '{app_name}' to the front: {exc}"


def focus_zen_mode(target_app: str) -> str:
    """Minimize every other app window and maximize the target."""
    try:
        target, err = _ensure_hwnd(target_app, launch=False)
        if target is None:
            return err
        win32gui, win32con, *_ = _win32()

        others: list[int] = []

        def _enum(hwnd: int, _extra: object) -> bool:
            if hwnd == target:
                return True
            if not _is_visible_top_level(hwnd):
                return True
            title = _window_title(hwnd).strip()
            if not title:
                return True
            if _is_system_or_tars(hwnd):
                return True
            others.append(hwnd)
            return True

        win32gui.EnumWindows(_enum, None)
        for hwnd in others:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            except Exception:  # noqa: BLE001
                continue

        win32gui.ShowWindow(target, win32con.SW_MAXIMIZE)
        _force_foreground(target)
        return f"Zen mode enabled for {target_app}. Background windows minimized."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to enable zen mode for '{target_app}': {exc}"


def tile_windows(left_app: str, right_app: str) -> str:
    """Snap two apps into a 50/50 split on the primary monitor."""
    try:
        left_hwnd, left_err = _ensure_hwnd(left_app, launch=True)
        if left_hwnd is None:
            return left_err
        right_hwnd, right_err = _ensure_hwnd(right_app, launch=True)
        if right_hwnd is None:
            return right_err
        if left_hwnd == right_hwnd:
            return (
                f"Error: '{left_app}' and '{right_app}' resolved to the same window. "
                "Name two different running apps."
            )

        left, top, width, height = _screen_metrics()
        half = max(width // 2, 200)
        _move(left_hwnd, left, top, half, height)
        _move(right_hwnd, left + half, top, width - half, height)
        _force_foreground(left_hwnd)
        _force_foreground(right_hwnd)
        return f"Snapped {left_app} to left and {right_app} to right."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to tile windows: {exc}"


def restore_workspace(layout_preset: str) -> str:
    """Apply a named spatial layout, launching missing apps if needed."""
    key = (layout_preset or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return "Error: layout_preset is empty."
    known = {
        "flutter",
        "mobile",
        "research",
        "deep_work",
        "deepwork",
        "reading",
        "read",
        "pdf",
    }
    if key not in known:
        return (
            f"Error: unknown layout preset '{layout_preset}'. "
            "Use flutter/mobile, research/deep_work, or reading."
        )

    try:
        win32gui, win32con, *_ = _win32()
        left, top, width, height = _screen_metrics()

        if key in {"flutter", "mobile"}:
            ide_hwnd, ide_err = _ensure_hwnd("vscode", launch=True)
            if ide_hwnd is None:
                return ide_err
            right_hwnd, _right_name = _first_existing("emulator", "chrome", "edge")
            if right_hwnd is None:
                right_hwnd, right_err = _ensure_hwnd("chrome", launch=True)
                if right_hwnd is None:
                    return right_err
            half = max(width // 2, 200)
            _move(ide_hwnd, left, top, half, height)
            _move(right_hwnd, left + half, top, width - half, height)
            _force_foreground(ide_hwnd)
            return f"Restored {layout_preset} workspace layout."

        if key in {"research", "deep_work", "deepwork"}:
            ide_hwnd, ide_err = _ensure_hwnd("vscode", launch=True)
            if ide_hwnd is None:
                return ide_err
            browser_hwnd, _browser_name = _first_existing("chrome", "edge", "firefox")
            if browser_hwnd is None:
                browser_hwnd, browser_err = _ensure_hwnd("chrome", launch=True)
                if browser_hwnd is None:
                    return browser_err
            left_w = max(int(width * 0.6), 200)
            _move(ide_hwnd, left, top, left_w, height)
            _move(browser_hwnd, left + left_w, top, width - left_w, height)
            _force_foreground(ide_hwnd)
            return f"Restored {layout_preset} workspace layout."

        if key in {"reading", "read", "pdf"}:
            reader_hwnd, _name = _first_existing(
                "acrobat", "pdf", "chrome", "edge", "firefox"
            )
            if reader_hwnd is None:
                reader_hwnd, reader_err = _ensure_hwnd("chrome", launch=True)
                if reader_hwnd is None:
                    return reader_err
            win32gui.ShowWindow(reader_hwnd, win32con.SW_MAXIMIZE)
            _force_foreground(reader_hwnd)
            return f"Restored {layout_preset} workspace layout."
    except Exception as exc:  # noqa: BLE001
        return f"Failed to restore workspace '{layout_preset}': {exc}"
