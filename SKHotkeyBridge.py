# -*- coding: utf-8 -*-
"""Mac KM Link hotkey bridge.

Registers configurable global hotkeys and forwards the original tray-menu
WM_COMMAND messages to the verified MacKMLink.exe window. The original program
files are never modified or injected.

Besides the two individual toggles this version adds a single "sync" hotkey
that turns keyboard/mouse control and clipboard sharing on or off together.
To do that reliably it reads the real on/off state from the program's own tray
menu: the menu is opened programmatically, moved off-screen, read and closed
again within a few milliseconds.
"""

from __future__ import annotations

import argparse
import configparser
import ctypes
import json
import os
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path


APP_NAME = "SKHotkeyBridge"
APP_TITLE = "对拷线快捷键桥接"
HELPER_WINDOW_CLASS = "SKHotkeyBridgeWindow_v1"
HELPER_WINDOW_TITLE = "SKHotkeyBridge.HiddenWindow"
MUTEX_NAME = r"Local\SKHotkeyBridge.SingleInstance.v1"

DEFAULT_TARGET_CLASS = "SmartKMCCableWinClass"
DEFAULT_TARGET_PROCESS = "MacKMLink.exe"
DEFAULT_KM_COMMAND = 32776
DEFAULT_CLIPBOARD_COMMAND = 32777
DEFAULT_TRAY_MESSAGE = 0x8001
DEFAULT_TRAY_ICON_ID = 0
DEFAULT_KM_HOTKEY = "CTRL+ALT+F9"
DEFAULT_CLIPBOARD_HOTKEY = "CTRL+ALT+F10"
DEFAULT_BOTH_HOTKEY = "CTRL+ALT+F11"

DEFAULT_KM_ON_TEXT = "暂时关闭鼠标键盘控制"
DEFAULT_KM_OFF_TEXT = "开启鼠标键盘控制"
DEFAULT_CLIPBOARD_ON_TEXT = "暂时关闭剪贴簿分享"
DEFAULT_CLIPBOARD_OFF_TEXT = "开启剪贴簿分享"

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_COMMAND = 0x0111
WM_CONTEXTMENU = 0x007B
WM_HOTKEY = 0x0312
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_NULL = 0x0000
TRAY_CALLBACK_MESSAGE = WM_APP + 31

MN_GETHMENU = 0x01E1
MF_BYPOSITION = 0x0400
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
VK_ESCAPE = 0x1B
KEYEVENTF_KEYUP = 0x0002
OFFSCREEN_X = -30000
OFFSCREEN_Y = -30000

HOTKEY_ID_KM = 0x4B01
HOTKEY_ID_CLIPBOARD = 0x4B02
HOTKEY_ID_BOTH = 0x4B03

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

CMD_MENU_TOGGLE_BOTH = 41000
CMD_MENU_TOGGLE_KM = 41001
CMD_MENU_TOGGLE_CLIPBOARD = 41002
CMD_MENU_ALL_ON = 41006
CMD_MENU_ALL_OFF = 41007
CMD_MENU_RELOAD = 41003
CMD_MENU_STATE = 41008
CMD_MENU_ABOUT = 41004
CMD_MENU_EXIT = 41005

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_INTEGRITY_LEVEL = 25
ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183
ERROR_CLASS_ALREADY_EXISTS = 1410
IDI_APPLICATION = 32512
IDC_ARROW = 32512
MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


# Explicit result types are required on 64-bit Python so handles are not truncated.
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]

advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
advapi32.GetTokenInformation.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthorityCount.argtypes = [wintypes.LPVOID]
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
advapi32.GetSidSubAuthority.argtypes = [wintypes.LPVOID, wintypes.DWORD]

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.RegisterClassExW.restype = wintypes.WORD
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.restype = wintypes.BOOL
user32.AppendMenuW.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPCWSTR,
]
user32.TrackPopupMenu.restype = wintypes.UINT
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPRECT,
]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostMessageW.restype = wintypes.BOOL
user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.EnumWindows.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetMessageW.restype = ctypes.c_int
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.TranslateMessage.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.MessageBoxW.restype = ctypes.c_int
user32.MessageBoxW.argtypes = [
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.UINT,
]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetMenuItemCount.argtypes = [wintypes.HMENU]
user32.GetMenuItemID.argtypes = [wintypes.HMENU, ctypes.c_int]
user32.GetMenuItemID.restype = wintypes.UINT
user32.GetMenuStringW.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.keybd_event.argtypes = [
    ctypes.c_ubyte,
    ctypes.c_ubyte,
    wintypes.DWORD,
    ctypes.c_size_t,
]

shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(NOTIFYICONDATAW),
]

WM_TASKBARCREATED = user32.RegisterWindowMessageW("TaskbarCreated")


MODIFIER_ALIASES = {
    "ALT": (MOD_ALT, "Alt"),
    "CTRL": (MOD_CONTROL, "Ctrl"),
    "CONTROL": (MOD_CONTROL, "Ctrl"),
    "SHIFT": (MOD_SHIFT, "Shift"),
    "WIN": (MOD_WIN, "Win"),
    "WINDOWS": (MOD_WIN, "Win"),
}

SPECIAL_KEYS = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PGUP": 0x21,
    "PAGEDOWN": 0x22,
    "PGDN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
}


class HotkeyError(ValueError):
    pass


def base_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return base_directory() / "SKHotkeyBridge.ini"


def default_config() -> dict[str, dict[str, str]]:
    return {
        "Hotkeys": {
            "Both": DEFAULT_BOTH_HOTKEY,
            "KeyboardMouse": DEFAULT_KM_HOTKEY,
            "Clipboard": DEFAULT_CLIPBOARD_HOTKEY,
        },
        "General": {
            "ShowFeedback": "false",
            "ShowStartupNotice": "false",
        },
        "Target": {
            "WindowClass": DEFAULT_TARGET_CLASS,
            "ProcessName": DEFAULT_TARGET_PROCESS,
            "KeyboardMouseCommand": str(DEFAULT_KM_COMMAND),
            "ClipboardCommand": str(DEFAULT_CLIPBOARD_COMMAND),
            "TrayMessage": hex(DEFAULT_TRAY_MESSAGE),
            "TrayIconId": str(DEFAULT_TRAY_ICON_ID),
        },
        "State": {
            "Detection": "auto",
            "HideProbeMenu": "true",
            "VerifyAfterCommand": "true",
            "KeyboardMouseOnText": DEFAULT_KM_ON_TEXT,
            "KeyboardMouseOffText": DEFAULT_KM_OFF_TEXT,
            "ClipboardOnText": DEFAULT_CLIPBOARD_ON_TEXT,
            "ClipboardOffText": DEFAULT_CLIPBOARD_OFF_TEXT,
        },
    }


def load_config(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict(default_config())
    if path.exists():
        with path.open("r", encoding="utf-8-sig") as handle:
            cfg.read_file(handle)
    return cfg


def parse_hotkey(text: str) -> tuple[int, int, str] | None:
    """Return (modifiers, virtual_key, label) or None when the hotkey is blank."""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return None
    parts = [part.upper() for part in compact.split("+") if part]
    if len(parts) < 2:
        raise HotkeyError(f"快捷键必须包含修饰键和主键: {text!r}")

    modifiers = 0
    modifier_labels: dict[int, str] = {}
    key_names: list[str] = []
    for part in parts:
        if part in MODIFIER_ALIASES:
            value, label = MODIFIER_ALIASES[part]
            modifiers |= value
            modifier_labels[value] = label
        else:
            key_names.append(part)

    if modifiers == 0:
        raise HotkeyError(f"快捷键缺少 Ctrl、Alt、Shift 或 Win: {text!r}")
    if len(key_names) != 1:
        raise HotkeyError(f"快捷键必须且只能包含一个主键: {text!r}")

    key_name = key_names[0]
    if len(key_name) == 1 and ("A" <= key_name <= "Z" or "0" <= key_name <= "9"):
        virtual_key = ord(key_name)
        key_label = key_name
    elif re.fullmatch(r"F(?:[1-9]|1\d|2[0-4])", key_name):
        number = int(key_name[1:])
        virtual_key = 0x70 + number - 1
        key_label = key_name
    elif key_name in SPECIAL_KEYS:
        virtual_key = SPECIAL_KEYS[key_name]
        key_label = key_name.title()
    else:
        raise HotkeyError(f"不支持的主键: {key_name}")

    ordered = []
    for value in (MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN):
        if value in modifier_labels:
            ordered.append(modifier_labels[value])
    ordered.append(key_label)
    return modifiers, virtual_key, "+".join(ordered)


def parse_int(text: str, name: str) -> int:
    value = (text or "").strip()
    if not value:
        raise ValueError(f"{name} 不能为空")
    return int(value, 0)


def message_box(text: str, title: str = APP_TITLE, warning: bool = False) -> None:
    flags = MB_OK | (MB_ICONWARNING if warning else MB_ICONINFORMATION)
    user32.MessageBoxW(None, text, title, flags)


def query_process_path(pid: int) -> str | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        )
        return buffer.value if ok else None
    finally:
        kernel32.CloseHandle(handle)


def query_integrity_level(pid: int | None = None) -> int | None:
    process_handle = None
    owns_process_handle = pid is not None
    if pid is None:
        process_handle = kernel32.GetCurrentProcess()
    else:
        process_handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not process_handle:
            return None

    token_handle = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(
            process_handle, TOKEN_QUERY, ctypes.byref(token_handle)
        ):
            return None

        required = wintypes.DWORD()
        advapi32.GetTokenInformation(
            token_handle,
            TOKEN_INTEGRITY_LEVEL,
            None,
            0,
            ctypes.byref(required),
        )
        if required.value == 0:
            return None

        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token_handle,
            TOKEN_INTEGRITY_LEVEL,
            buffer,
            required.value,
            ctypes.byref(required),
        ):
            return None

        mandatory_label = ctypes.cast(
            buffer, ctypes.POINTER(TOKEN_MANDATORY_LABEL)
        ).contents
        sid = mandatory_label.Label.Sid
        count_ptr = advapi32.GetSidSubAuthorityCount(sid)
        if not count_ptr or count_ptr.contents.value == 0:
            return None
        rid_ptr = advapi32.GetSidSubAuthority(sid, count_ptr.contents.value - 1)
        return int(rid_ptr.contents.value) if rid_ptr else None
    finally:
        if token_handle:
            kernel32.CloseHandle(token_handle)
        if owns_process_handle and process_handle:
            kernel32.CloseHandle(process_handle)


def integrity_level_name(level: int | None) -> str:
    if level is None:
        return "unknown"
    if level < 0x1000:
        return "untrusted"
    if level < 0x2000:
        return "low"
    if level < 0x3000:
        return "medium"
    if level < 0x4000:
        return "high"
    return "system"


def find_popups_for_pid(pid: int) -> list[int]:
    """Return every visible popup-menu window owned by the given process."""
    found: list[int] = []

    @WNDENUMPROC
    def callback(hwnd: int, _lparam: int) -> bool:
        try:
            class_buffer = ctypes.create_unicode_buffer(32)
            if not user32.GetClassNameW(hwnd, class_buffer, len(class_buffer)):
                return True
            if class_buffer.value != "#32768":
                return True
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid and user32.IsWindowVisible(hwnd):
                found.append(int(hwnd))
        except (OSError, ValueError, ctypes.ArgumentError):
            return True
        return True

    user32.EnumWindows(callback, 0)
    return found


def read_menu_texts(hwnd: int) -> dict[int, str]:
    """Read every item of a popup menu window as {command_id: text}."""
    hmenu = user32.SendMessageW(hwnd, MN_GETHMENU, 0, 0)
    if not hmenu:
        return {}
    texts: dict[int, str] = {}
    for pos in range(user32.GetMenuItemCount(hmenu)):
        item_id = user32.GetMenuItemID(hmenu, pos)
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetMenuStringW(hmenu, pos, buffer, len(buffer), MF_BYPOSITION)
        texts[int(item_id)] = buffer.value
    return texts


def close_popup(hwnd: int, timeout_ms: int = 500) -> bool:
    """Close a popup menu and verify it is really gone."""
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    if not _wait_popup_gone(hwnd, timeout_ms):
        user32.keybd_event(VK_ESCAPE, 0, 0, 0)
        user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
        if not _wait_popup_gone(hwnd, timeout_ms):
            return False
    return True


def _wait_popup_gone(hwnd: int, timeout_ms: int) -> bool:
    deadline = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < deadline:
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return True
        time.sleep(0.005)
    return not (user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))


def normalize_text(text: str) -> str:
    return re.sub(r"[\s&]", "", text or "").replace("(&", "")


class TargetController:
    def __init__(self, cfg: configparser.ConfigParser):
        self.update(cfg)

    def update(self, cfg: configparser.ConfigParser) -> None:
        self.window_class = cfg.get(
            "Target", "WindowClass", fallback=DEFAULT_TARGET_CLASS
        ).strip()
        self.process_name = cfg.get(
            "Target", "ProcessName", fallback=DEFAULT_TARGET_PROCESS
        ).strip()
        self.km_command = cfg.getint(
            "Target", "KeyboardMouseCommand", fallback=DEFAULT_KM_COMMAND
        )
        self.clipboard_command = cfg.getint(
            "Target", "ClipboardCommand", fallback=DEFAULT_CLIPBOARD_COMMAND
        )
        for name, command_id in (
            ("KeyboardMouseCommand", self.km_command),
            ("ClipboardCommand", self.clipboard_command),
        ):
            if not 1 <= command_id <= 0xFFFF:
                raise ValueError(f"{name} 必须在 1 到 65535 之间")

        self.tray_message = parse_int(
            cfg.get("Target", "TrayMessage", fallback=hex(DEFAULT_TRAY_MESSAGE)),
            "TrayMessage",
        )
        self.tray_icon_id = parse_int(
            cfg.get("Target", "TrayIconId", fallback=str(DEFAULT_TRAY_ICON_ID)),
            "TrayIconId",
        )
        if not 0 <= self.tray_message <= 0xFFFF:
            raise ValueError("TrayMessage 必须在 0 到 65535 之间")
        if not 0 <= self.tray_icon_id <= 0xFFFF:
            raise ValueError("TrayIconId 必须在 0 到 65535 之间")

        self.detection = cfg.get("State", "Detection", fallback="auto").strip().lower()
        self.hide_probe_menu = cfg.getboolean(
            "State", "HideProbeMenu", fallback=True
        )
        self.verify_after_command = cfg.getboolean(
            "State", "VerifyAfterCommand", fallback=True
        )
        self.km_on_text = normalize_text(
            cfg.get("State", "KeyboardMouseOnText", fallback=DEFAULT_KM_ON_TEXT)
        )
        self.km_off_text = normalize_text(
            cfg.get("State", "KeyboardMouseOffText", fallback=DEFAULT_KM_OFF_TEXT)
        )
        self.clipboard_on_text = normalize_text(
            cfg.get("State", "ClipboardOnText", fallback=DEFAULT_CLIPBOARD_ON_TEXT)
        )
        self.clipboard_off_text = normalize_text(
            cfg.get("State", "ClipboardOffText", fallback=DEFAULT_CLIPBOARD_OFF_TEXT)
        )

    def find_window(self) -> tuple[int, int, str] | None:
        matches: list[tuple[int, int, str]] = []

        @WNDENUMPROC
        def callback(hwnd: int, _lparam: int) -> bool:
            try:
                class_buffer = ctypes.create_unicode_buffer(256)
                if not user32.GetClassNameW(hwnd, class_buffer, len(class_buffer)):
                    return True
                if class_buffer.value != self.window_class:
                    return True

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                path = query_process_path(pid.value)
                if not path:
                    return True
                if os.path.basename(path).lower() != self.process_name.lower():
                    return True
                matches.append((int(hwnd), pid.value, path))
                return False
            except (OSError, ValueError, ctypes.ArgumentError):
                return True

        user32.EnumWindows(callback, 0)
        return matches[0] if matches else None

    def check_access(self, pid: int) -> str | None:
        current_integrity = query_integrity_level()
        target_integrity = query_integrity_level(pid)
        if (
            current_integrity is not None
            and target_integrity is not None
            and target_integrity > current_integrity
        ):
            return (
                "原版对拷线程序以更高权限运行，Windows 会拦截快捷键命令。"
                "请退出桥接工具并以管理员身份重新运行。"
            )
        return None

    def send_command(self, hwnd: int, command_id: int) -> tuple[bool, str]:
        ctypes.set_last_error(0)
        ok = user32.PostMessageW(hwnd, WM_COMMAND, command_id, 0)
        if not ok:
            return (
                False,
                f"命令发送失败，Windows 错误码: {ctypes.get_last_error()}。"
                "请确认两个程序权限级别一致。",
            )
        return True, "命令已发送。"

    def toggle(self, command_id: int) -> tuple[bool, str, dict[str, object]]:
        target = self.find_window()
        if not target:
            return (
                False,
                f"未找到正在运行的 {self.process_name}。请先启动原版对拷线程序。",
                {},
            )
        hwnd, pid, path = target
        details = {"hwnd": hex(hwnd), "pid": pid, "path": path, "command_id": command_id}
        blocked = self.check_access(pid)
        if blocked:
            return False, blocked, details
        ok, message = self.send_command(hwnd, command_id)
        return ok, message, details

    def toggle_km(self) -> tuple[bool, str, dict[str, object]]:
        return self.toggle(self.km_command)

    def toggle_clipboard(self) -> tuple[bool, str, dict[str, object]]:
        return self.toggle(self.clipboard_command)

    def interpret(self, text: str, on_text: str, off_text: str) -> bool | None:
        """Map a menu caption to True (currently on) / False (off) / None."""
        normalized = normalize_text(text)
        if not normalized:
            return None
        if on_text and normalized == on_text:
            return True
        if off_text and normalized == off_text:
            return False
        # Language independent fallback: the caption describes the action,
        # so "disable/关闭" means it is currently on.
        lowered = normalized.lower()
        if "disable" in lowered or "关闭" in normalized:
            return True
        if "enable" in lowered or "开启" in normalized:
            return False
        return None

    def probe_state(self) -> dict[str, object]:
        """Read the real on/off state from the program's own tray menu."""
        target = self.find_window()
        if not target:
            return {
                "ok": False,
                "error": f"未找到正在运行的 {self.process_name}。"
                "请先启动原版对拷线程序。",
            }
        hwnd, pid, path = target
        blocked = self.check_access(pid)
        if blocked:
            return {"ok": False, "error": blocked}

        # Clear any menu left open by an earlier failed attempt.
        for leftover in find_popups_for_pid(pid):
            close_popup(leftover)

        user32.PostMessageW(hwnd, self.tray_message, self.tray_icon_id, WM_RBUTTONUP)

        popup = 0
        deadline = time.perf_counter() + 1.0
        while time.perf_counter() < deadline:
            popups = find_popups_for_pid(pid)
            if popups:
                popup = popups[0]
                break
            time.sleep(0.001)
        if not popup:
            return {"ok": False, "error": "无法读取状态：托盘菜单没有弹出。"}

        try:
            if self.hide_probe_menu:
                user32.SetWindowPos(
                    popup,
                    None,
                    OFFSCREEN_X,
                    OFFSCREEN_Y,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                )
            texts = read_menu_texts(popup)
        finally:
            closed = close_popup(popup)

        km_text = texts.get(self.km_command)
        clipboard_text = texts.get(self.clipboard_command)
        if km_text is None or clipboard_text is None:
            return {
                "ok": False,
                "error": "无法识别托盘菜单中的开关项，请检查命令编号配置。",
                "texts": texts,
            }
        if not closed:
            return {
                "ok": False,
                "error": "状态菜单未能正常关闭，请手动按一次 Esc 键。",
            }

        return {
            "ok": True,
            "km": self.interpret(km_text, self.km_on_text, self.km_off_text),
            "clipboard": self.interpret(
                clipboard_text, self.clipboard_on_text, self.clipboard_off_text
            ),
            "km_text": km_text,
            "clipboard_text": clipboard_text,
            "details": {"hwnd": hex(hwnd), "pid": pid, "path": path},
        }

    def apply_state(self, km: bool | None, clipboard: bool | None) -> tuple[bool, str]:
        """Turn each channel on or off, skipping the ones already correct."""
        target = self.find_window()
        if not target:
            return (
                False,
                f"未找到正在运行的 {self.process_name}。请先启动原版对拷线程序。",
            )
        hwnd, pid, _path = target
        blocked = self.check_access(pid)
        if blocked:
            return False, blocked

        if km is not None:
            ok, message = self.send_command(hwnd, self.km_command)
            if not ok:
                return False, message
        if clipboard is not None:
            ok, message = self.send_command(hwnd, self.clipboard_command)
            if not ok:
                return False, message
        return True, "命令已发送。"

    def set_both(self, turn_on: bool) -> tuple[bool, str]:
        """Bring both channels to the requested state."""
        if self.detection == "off":
            return self.apply_state(True, True) if not turn_on else (True, "忽略。")

        state = self.probe_state()
        if not state.get("ok"):
            return False, str(state.get("error"))

        km = state.get("km")
        clipboard = state.get("clipboard")
        if km is None or clipboard is None:
            return False, "无法识别当前开关状态，请检查菜单文字配置。"

        wanted_km = None if km == turn_on else self.km_command
        wanted_clipboard = None if clipboard == turn_on else self.clipboard_command

        if wanted_km is None and wanted_clipboard is None:
            return True, "已经是目标状态，无需操作。"

        ok, message = self.apply_state(
            self.km_command if wanted_km else None,
            self.clipboard_command if wanted_clipboard else None,
        )
        if not ok:
            return False, message

        if self.verify_after_command:
            time.sleep(0.25)
            state = self.probe_state()
            if not state.get("ok"):
                return True, f"命令已发送，但状态确认失败: {state.get('error')}"
            km = state.get("km")
            clipboard = state.get("clipboard")
            if km is None or clipboard is None:
                return True, "命令已发送，但状态无法确认。"
            if km != turn_on or clipboard != turn_on:
                return (
                    False,
                    "状态切换后校验未通过，可能被其他操作打断，请再按一次快捷键。",
                )
        return True, "已同步切换。"

    def sync_toggle(self) -> tuple[bool, str]:
        """One key: stop both when anything is on, resume both when all is off."""
        if self.detection == "off":
            return self.apply_state(True, True)

        state = self.probe_state()
        if not state.get("ok"):
            return False, str(state.get("error"))
        km = state.get("km")
        clipboard = state.get("clipboard")
        if km is None or clipboard is None:
            return False, "无法识别当前开关状态，请检查菜单文字配置。"
        return self.set_both(not (km or clipboard))


APP_INSTANCE: "HotkeyBridgeApp | None" = None


@WNDPROC
def global_wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
    if APP_INSTANCE is not None:
        try:
            handled, result = APP_INSTANCE.handle_message(hwnd, msg, wparam, lparam)
            if handled:
                return result
        except Exception as exc:
            APP_INSTANCE.report_error(f"消息处理异常: {exc}")
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


class HotkeyBridgeApp:
    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.cfg = load_config(cfg_path)
        self.controller = TargetController(self.cfg)
        self.hwnd = 0
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.icon = user32.LoadIconW(
            None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR)
        )
        self.nid = NOTIFYICONDATAW()
        self.tray_added = False
        self.cleaned = False
        self.mutex = None
        self.hotkeys: dict[int, tuple[int, int, str]] = {}
        self.km_hotkey_text = DEFAULT_KM_HOTKEY
        self.clipboard_hotkey_text = DEFAULT_CLIPBOARD_HOTKEY
        self.both_hotkey_text = DEFAULT_BOTH_HOTKEY
        self.show_feedback = False
        self.show_startup_notice = False
        self.last_state_text = "未知"

    def report_error(self, text: str) -> None:
        if self.tray_added:
            self.show_balloon("快捷键桥接异常", text, warning=True)
        else:
            message_box(text, warning=True)

    def acquire_single_instance(self) -> bool:
        ctypes.set_last_error(0)
        self.mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        error = ctypes.get_last_error()
        if not self.mutex:
            if error == ERROR_ACCESS_DENIED:
                self.report_error(
                    "检测到可能由更高权限运行的桥接实例，请先退出该实例后再试。"
                )
            else:
                self.report_error(f"无法创建单实例互斥量，Windows 错误码: {error}")
            return False
        if error == ERROR_ALREADY_EXISTS:
            message_box("快捷键桥接已经在运行，无需重复启动。")
            return False
        return True

    def create_hidden_window(self) -> bool:
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        window_class.style = 0
        window_class.lpfnWndProc = global_wnd_proc
        window_class.cbClsExtra = 0
        window_class.cbWndExtra = 0
        window_class.hInstance = self.hinstance
        window_class.hIcon = self.icon
        window_class.hCursor = user32.LoadCursorW(
            None, ctypes.cast(IDC_ARROW, wintypes.LPCWSTR)
        )
        window_class.hbrBackground = None
        window_class.lpszMenuName = None
        window_class.lpszClassName = HELPER_WINDOW_CLASS
        window_class.hIconSm = self.icon

        ctypes.set_last_error(0)
        atom = user32.RegisterClassExW(ctypes.byref(window_class))
        if not atom and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            self.report_error(
                f"注册隐藏窗口失败，Windows 错误码: {ctypes.get_last_error()}"
            )
            return False

        self.hwnd = user32.CreateWindowExW(
            0,
            HELPER_WINDOW_CLASS,
            HELPER_WINDOW_TITLE,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            self.hinstance,
            None,
        )
        if not self.hwnd:
            self.report_error(
                f"创建隐藏窗口失败，Windows 错误码: {ctypes.get_last_error()}"
            )
            return False
        return True

    def tray_tooltip(self) -> str:
        return f"{APP_TITLE} - {self.last_state_text}"[:127]

    def add_tray_icon(self) -> bool:
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = TRAY_CALLBACK_MESSAGE
        self.nid.hIcon = self.icon
        self.nid.szTip = self.tray_tooltip()
        ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        self.tray_added = bool(ok)
        if not ok:
            message_box("无法创建快捷键桥接托盘图标。", warning=True)
        return bool(ok)

    def update_tray_tip(self) -> None:
        if not self.tray_added:
            return
        self.nid.uFlags = NIF_TIP
        self.nid.szTip = self.tray_tooltip()
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP

    def show_balloon(self, title: str, text: str, warning: bool = False) -> None:
        if not self.tray_added:
            return
        self.nid.uFlags = NIF_INFO
        self.nid.szInfoTitle = title[:63]
        self.nid.szInfo = text[:255]
        self.nid.dwInfoFlags = NIIF_WARNING if warning else NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP

    def unregister_hotkeys(self) -> None:
        if not self.hwnd:
            return
        for hotkey_id in list(self.hotkeys):
            user32.UnregisterHotKey(self.hwnd, hotkey_id)
        self.hotkeys.clear()

    def reload_config(self, notify: bool = True) -> bool:
        try:
            new_cfg = load_config(self.cfg_path)
            both = parse_hotkey(
                new_cfg.get("Hotkeys", "Both", fallback=DEFAULT_BOTH_HOTKEY)
            )
            km = parse_hotkey(
                new_cfg.get(
                    "Hotkeys", "KeyboardMouse", fallback=DEFAULT_KM_HOTKEY
                )
            )
            clipboard = parse_hotkey(
                new_cfg.get("Hotkeys", "Clipboard", fallback=DEFAULT_CLIPBOARD_HOTKEY)
            )
            show_feedback = new_cfg.getboolean(
                "General", "ShowFeedback", fallback=False
            )
            show_startup_notice = new_cfg.getboolean(
                "General", "ShowStartupNotice", fallback=False
            )
            new_controller = TargetController(new_cfg)
        except (OSError, configparser.Error, HotkeyError, ValueError) as exc:
            self.report_error(f"配置文件读取失败: {exc}")
            return False

        if not both and not km and not clipboard:
            self.report_error("至少需要配置一个快捷键。")
            return False

        old_hotkeys = dict(self.hotkeys)
        self.unregister_hotkeys()
        registered: dict[int, tuple[int, int, str]] = {}
        errors = []
        candidates = (
            (HOTKEY_ID_BOTH, both),
            (HOTKEY_ID_KM, km),
            (HOTKEY_ID_CLIPBOARD, clipboard),
        )
        for hotkey_id, value in candidates:
            if value is None:
                continue
            modifiers, virtual_key, label = value
            ctypes.set_last_error(0)
            ok = user32.RegisterHotKey(
                self.hwnd,
                hotkey_id,
                modifiers | MOD_NOREPEAT,
                virtual_key,
            )
            if ok:
                registered[hotkey_id] = value
            else:
                errors.append(f"{label} (错误码 {ctypes.get_last_error()})")

        if errors:
            for hotkey_id in registered:
                user32.UnregisterHotKey(self.hwnd, hotkey_id)

            restored: dict[int, tuple[int, int, str]] = {}
            restore_errors = []
            for hotkey_id, value in old_hotkeys.items():
                modifiers, virtual_key, label = value
                ctypes.set_last_error(0)
                if user32.RegisterHotKey(
                    self.hwnd,
                    hotkey_id,
                    modifiers | MOD_NOREPEAT,
                    virtual_key,
                ):
                    restored[hotkey_id] = value
                else:
                    restore_errors.append(
                        f"{label} (错误码 {ctypes.get_last_error()})"
                    )
            self.hotkeys = restored

            text = "以下全局快捷键注册失败，可能已被其他程序占用:\n" + "\n".join(errors)
            if restore_errors:
                text += "\n原快捷键恢复失败:\n" + "\n".join(restore_errors)
            self.report_error(text)
            return False

        self.hotkeys = registered
        self.cfg = new_cfg
        self.controller = new_controller
        self.both_hotkey_text = both[2] if both else "未设置"
        self.km_hotkey_text = km[2] if km else "未设置"
        self.clipboard_hotkey_text = clipboard[2] if clipboard else "未设置"
        self.show_feedback = show_feedback
        self.show_startup_notice = show_startup_notice

        if self.tray_added:
            self.update_tray_tip()

        if notify:
            self.show_balloon(
                "配置已重新载入",
                f"一键同步: {self.both_hotkey_text}\n"
                f"鼠标键盘: {self.km_hotkey_text}\n"
                f"剪贴簿: {self.clipboard_hotkey_text}",
            )
        return True

    def refresh_state_text(self) -> bool | None:
        if self.controller.detection == "off":
            self.last_state_text = "状态检测已关闭"
            self.update_tray_tip()
            return None
        state = self.controller.probe_state()
        if not state.get("ok"):
            self.last_state_text = "状态未知"
            self.update_tray_tip()
            return None
        km = state.get("km")
        clipboard = state.get("clipboard")
        if km is None or clipboard is None:
            self.last_state_text = "状态未知"
        elif km and clipboard:
            self.last_state_text = "已共享"
        elif not km and not clipboard:
            self.last_state_text = "已暂停"
        else:
            self.last_state_text = "鼠标键盘:开 剪贴簿:关" if km else "鼠标键盘:关 剪贴簿:开"
        self.update_tray_tip()
        return bool(km and clipboard)

    def run_action(self, action: str) -> None:
        if action == "sync":
            ok, message = self.controller.sync_toggle()
            title = "一键同步切换"
        elif action == "on":
            ok, message = self.controller.set_both(True)
            title = "全部开启"
        elif action == "off":
            ok, message = self.controller.set_both(False)
            title = "全部关闭"
        elif action == "km":
            ok, message, _details = self.controller.toggle_km()
            title = "鼠标键盘控制"
        else:
            ok, message, _details = self.controller.toggle_clipboard()
            title = "剪贴簿分享"

        if not ok:
            self.report_error(message)
            return

        self.refresh_state_text()
        if self.show_feedback:
            self.show_balloon(title, f"{message} 当前状态: {self.last_state_text}")

    def show_about(self) -> None:
        target = self.controller.find_window()
        target_text = "已连接到原程序" if target else "未检测到原程序"
        text = (
            f"{APP_TITLE}\n\n"
            f"一键同步开关: {self.both_hotkey_text}\n"
            f"鼠标键盘控制: {self.km_hotkey_text}\n"
            f"剪贴簿分享: {self.clipboard_hotkey_text}\n"
            f"原程序: {target_text}\n"
            f"当前状态: {self.last_state_text}\n\n"
            "本工具不修改、不注入原版程序，只向已验证的 MacKMLink.exe "
            "发送原托盘菜单命令。"
        )
        message_box(text)

    def show_state(self) -> None:
        self.refresh_state_text()
        state = self.controller.probe_state()
        if not state.get("ok"):
            self.report_error(str(state.get("error")))
            return
        message_box(
            f"鼠标键盘控制: {'开' if state.get('km') else '关'}\n"
            f"剪贴簿分享: {'开' if state.get('clipboard') else '关'}\n\n"
            f"菜单原文:\n{state.get('km_text')}\n{state.get('clipboard_text')}"
        )

    def show_tray_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(
                menu,
                MF_STRING,
                CMD_MENU_TOGGLE_BOTH,
                f"一键同步开关\t{self.both_hotkey_text}",
            )
            user32.AppendMenuW(menu, MF_STRING, CMD_MENU_ALL_ON, "全部开启")
            user32.AppendMenuW(menu, MF_STRING, CMD_MENU_ALL_OFF, "全部关闭")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(
                menu,
                MF_STRING,
                CMD_MENU_TOGGLE_KM,
                f"切换鼠标键盘控制\t{self.km_hotkey_text}",
            )
            user32.AppendMenuW(
                menu,
                MF_STRING,
                CMD_MENU_TOGGLE_CLIPBOARD,
                f"切换剪贴簿分享\t{self.clipboard_hotkey_text}",
            )
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_MENU_STATE, "查看当前状态")
            user32.AppendMenuW(menu, MF_STRING, CMD_MENU_RELOAD, "重新载入配置")
            user32.AppendMenuW(menu, MF_STRING, CMD_MENU_ABOUT, "状态与说明")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_MENU_EXIT, "退出快捷键桥接")

            point = POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(self.hwnd)
            command = user32.TrackPopupMenu(
                menu,
                TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x,
                point.y,
                0,
                self.hwnd,
                None,
            )
            if command:
                self.execute_menu_command(command)
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)

    def execute_menu_command(self, command: int) -> None:
        if command == CMD_MENU_TOGGLE_BOTH:
            self.run_action("sync")
        elif command == CMD_MENU_ALL_ON:
            self.run_action("on")
        elif command == CMD_MENU_ALL_OFF:
            self.run_action("off")
        elif command == CMD_MENU_TOGGLE_KM:
            self.run_action("km")
        elif command == CMD_MENU_TOGGLE_CLIPBOARD:
            self.run_action("clipboard")
        elif command == CMD_MENU_STATE:
            self.show_state()
        elif command == CMD_MENU_RELOAD:
            self.reload_config(notify=True)
        elif command == CMD_MENU_ABOUT:
            self.show_about()
        elif command == CMD_MENU_EXIT:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def handle_message(
        self, hwnd: int, msg: int, wparam: int, lparam: int
    ) -> tuple[bool, int]:
        if msg == WM_TASKBARCREATED:
            self.tray_added = False
            self.add_tray_icon()
            return True, 0

        if msg == WM_HOTKEY:
            if wparam == HOTKEY_ID_BOTH:
                self.run_action("sync")
                return True, 0
            if wparam == HOTKEY_ID_KM:
                self.run_action("km")
                return True, 0
            if wparam == HOTKEY_ID_CLIPBOARD:
                self.run_action("clipboard")
                return True, 0
            return False, 0

        if msg == TRAY_CALLBACK_MESSAGE:
            event = lparam & 0xFFFF
            if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self.show_tray_menu()
            elif event == WM_LBUTTONDBLCLK:
                self.show_about()
            return True, 0

        if msg == WM_COMMAND:
            self.execute_menu_command(wparam & 0xFFFF)
            return True, 0

        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return True, 0

        if msg == WM_QUERYENDSESSION:
            return True, 1

        if msg == WM_ENDSESSION:
            if wparam:
                self.cleanup()
                user32.PostQuitMessage(0)
            return True, 0

        if msg == WM_DESTROY:
            self.cleanup()
            user32.PostQuitMessage(0)
            return True, 0

        return False, 0

    def cleanup(self) -> None:
        if self.cleaned:
            return
        self.cleaned = True
        self.unregister_hotkeys()
        if self.tray_added:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.tray_added = False
        if self.mutex:
            kernel32.CloseHandle(self.mutex)
            self.mutex = None

    def run(self) -> int:
        global APP_INSTANCE
        APP_INSTANCE = self
        if not self.acquire_single_instance():
            self.cleanup()
            return 2
        if not self.create_hidden_window():
            self.cleanup()
            return 3
        if not self.add_tray_icon():
            self.cleanup()
            return 4

        if not self.reload_config(notify=False) and not self.hotkeys:
            self.report_error("没有任何全局快捷键注册成功，桥接程序将退出。")
            self.cleanup()
            return 6
        if self.show_startup_notice:
            self.show_balloon(
                "快捷键桥接已启动",
                f"一键同步: {self.both_hotkey_text}\n"
                f"鼠标键盘: {self.km_hotkey_text}\n"
                f"剪贴簿: {self.clipboard_hotkey_text}",
            )

        message = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == 0:
                break
            if result == -1:
                self.report_error("Windows 消息循环异常。")
                self.cleanup()
                return 5
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        self.cleanup()
        return 0


def run_self_test() -> int:
    hotkey_cases = {
        "CTRL+ALT+F9": (MOD_CONTROL | MOD_ALT, 0x78, "Ctrl+Alt+F9"),
        "shift+win+a": (MOD_SHIFT | MOD_WIN, ord("A"), "Shift+Win+A"),
        "CTRL+PAGEUP": (MOD_CONTROL, 0x21, "Ctrl+Pageup"),
        "": None,
    }
    results = []
    passed = True
    for raw, expected in hotkey_cases.items():
        actual = parse_hotkey(raw)
        ok = actual == expected
        passed = passed and ok
        results.append(
            {"input": raw, "expected": expected, "actual": actual, "passed": ok}
        )

    controller = TargetController(load_config(config_path()))
    text_cases = {
        "暂时关闭鼠标键盘控制": True,
        "开启鼠标键盘控制": False,
        "暂时关闭剪贴簿分享": True,
        "开启剪贴簿分享": False,
        "Disable Keyboard and Mouse Control temporarily": True,
        "Enable Keyboard and Mouse Control": False,
    }
    for text, expected in text_cases.items():
        is_km = "鼠标键盘" in text or "Keyboard" in text
        actual = (
            controller.interpret(text, controller.km_on_text, controller.km_off_text)
            if is_km
            else controller.interpret(
                text, controller.clipboard_on_text, controller.clipboard_off_text
            )
        )
        ok = actual == expected
        passed = passed and ok
        results.append(
            {"text": text, "expected": expected, "actual": actual, "passed": ok}
        )

    print(json.dumps({"passed": passed, "cases": results}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def stop_running_instance() -> int:
    hwnd = user32.FindWindowW(HELPER_WINDOW_CLASS, HELPER_WINDOW_TITLE)
    if not hwnd:
        return 1
    return 0 if user32.PostMessageW(hwnd, WM_CLOSE, 0, 0) else 2


def one_shot(action: str, cfg: configparser.ConfigParser) -> int:
    controller = TargetController(cfg)
    if action == "km":
        ok, message, details = controller.toggle_km()
    elif action == "clipboard":
        ok, message, details = controller.toggle_clipboard()
    elif action == "state":
        state = controller.probe_state()
        ok = bool(state.get("ok"))
        message = str(state.get("error")) if not ok else "状态读取成功。"
        details = state
    elif action == "on":
        ok, message = controller.set_both(True)
        details = {}
    elif action == "off":
        ok, message = controller.set_both(False)
        details = {}
    else:
        ok, message = controller.sync_toggle()
        details = {}
    if not ok:
        message_box(message, warning=True)
    if sys.stdout is not None:
        try:
            print(
                json.dumps(
                    {"ok": ok, "message": message, "details": details},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except OSError:
            pass
    return 0 if ok else 1


def check_target(cfg: configparser.ConfigParser) -> int:
    controller = TargetController(cfg)
    target = controller.find_window()
    result = {
        "found": bool(target),
        "window_class": controller.window_class,
        "process_name": controller.process_name,
    }
    if target:
        hwnd, pid, path = target
        result.update({"hwnd": hex(hwnd), "pid": pid, "path": path})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if target else 1


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--toggle-both", action="store_true", help="一键同步开关后退出")
    group.add_argument("--all-on", action="store_true", help="同时开启两项后退出")
    group.add_argument("--all-off", action="store_true", help="同时关闭两项后退出")
    group.add_argument("--toggle-km", action="store_true", help="切换鼠标键盘控制后退出")
    group.add_argument(
        "--toggle-clipboard", action="store_true", help="切换剪贴簿分享后退出"
    )
    group.add_argument("--state", action="store_true", help="读取当前开关状态")
    group.add_argument("--stop", action="store_true", help="停止正在运行的桥接程序")
    group.add_argument("--check-target", action="store_true", help="检查原程序窗口")
    group.add_argument("--self-test", action="store_true", help="运行内部测试")
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    if args.self_test:
        return run_self_test()
    if args.stop:
        return stop_running_instance()

    try:
        cfg = load_config(config_path())
    except (OSError, configparser.Error) as exc:
        message_box(f"配置文件读取失败: {exc}", warning=True)
        return 2

    if args.check_target:
        return check_target(cfg)
    if args.toggle_both:
        return one_shot("sync", cfg)
    if args.all_on:
        return one_shot("on", cfg)
    if args.all_off:
        return one_shot("off", cfg)
    if args.toggle_km:
        return one_shot("km", cfg)
    if args.toggle_clipboard:
        return one_shot("clipboard", cfg)
    if args.state:
        return one_shot("state", cfg)

    app = HotkeyBridgeApp(config_path())
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
