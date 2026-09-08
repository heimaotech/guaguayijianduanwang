
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


# ============================================================
# 呱呱一键断网与恢复
# Windows 原生 Win32 最终稳定版
#
# 正常运行：
#   Windows RegisterHotKey -> WM_HOTKEY
#   Windows Shell_NotifyIcon -> 托盘
#
# 设置快捷键：
#   只在设置期间临时使用 GetAsyncKeyState 捕获按键
#
# 断网：
#   Windows Defender Firewall 创建两条专用规则
#   不关闭 Wi-Fi / Ethernet
#   不修改 IP / DNS / 路由
#
# 第三方 Python 依赖：0
# ============================================================


APP_NAME = "呱呱一键断网与恢复"
APP_MUTEX = "Local\\GuaguaNetToggle.SingleInstance"

CONFIG_DIR = (
    Path(os.environ.get("APPDATA", str(Path.home())))
    / "GuaguaNetToggle"
)
CONFIG_FILE = CONFIG_DIR / "config.json"

WINDOW_WIDTH = 400
WINDOW_HEIGHT = 600

RULE_OUT = "GuaguaNetToggle_Block_Outbound"
RULE_IN = "GuaguaNetToggle_Block_Inbound"
RULE_GROUP = "GuaguaNetToggle"

DEFAULT_VK = 0x24       # Home
DEFAULT_MOD = 0x0000

HOTKEY_ID = 1001

# ------------------------------------------------------------
# Windows messages
# ------------------------------------------------------------

WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_HOTKEY = 0x0312
WM_CTLCOLORSTATIC = 0x0138
WM_TRAY = 0x8001
WM_ADAPTER_REFRESH = 0x8002
WM_CAPTURE_KEY = 0x8003
WM_SHOW_ERROR = 0x8004

# ------------------------------------------------------------
# Controls
# ------------------------------------------------------------

ID_BTN_TOGGLE = 3001
ID_BTN_HOTKEY = 3002
ID_BTN_REFRESH = 3003

# ------------------------------------------------------------
# Tray
# ------------------------------------------------------------

ID_TRAY_OPEN = 2001
ID_TRAY_TOGGLE = 2002
ID_TRAY_EXIT = 2003

# ------------------------------------------------------------
# Window styles
# ------------------------------------------------------------

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_EX_APPWINDOW = 0x00040000

BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001

SS_LEFT = 0x00000000
SS_LEFTNOWORDWRAP = 0x00000C00

SW_HIDE = 0
SW_SHOWNORMAL = 1

SM_CXSCREEN = 0
SM_CYSCREEN = 1

IDI_ERROR = 32513  # Windows native red X icon
IDC_ARROW = 32512

DEFAULT_GUI_FONT = 17

# ------------------------------------------------------------
# Hotkey modifiers
# ------------------------------------------------------------

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# ------------------------------------------------------------
# MessageBox
# ------------------------------------------------------------

MB_OK = 0x00000000
MB_ICONERROR = 0x00000010
MB_ICONWARNING = 0x00000030

# ------------------------------------------------------------
# GDI
# ------------------------------------------------------------

TRANSPARENT = 1
FW_NORMAL = 400
FW_SEMIBOLD = 600


# ============================================================
# Handle aliases
# ============================================================

HANDLE = ctypes.c_void_p
HWND = HANDLE
HINSTANCE = HANDLE
HMODULE = HANDLE
HICON = HANDLE
HCURSOR = HANDLE
HBRUSH = HANDLE
HFONT = HANDLE
HGDIOBJ = HANDLE
HMENU = HANDLE

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t


# ============================================================
# Structures
# ============================================================

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", HANDLE),
        ("fErase", wintypes.BOOL),
        ("rcPaint", RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", wintypes.BYTE * 32),
    ]


class LOGFONTW(ctypes.Structure):
    _fields_ = [
        ("lfHeight", wintypes.LONG),
        ("lfWidth", wintypes.LONG),
        ("lfEscapement", wintypes.LONG),
        ("lfOrientation", wintypes.LONG),
        ("lfWeight", wintypes.LONG),
        ("lfItalic", wintypes.BYTE),
        ("lfUnderline", wintypes.BYTE),
        ("lfStrikeOut", wintypes.BYTE),
        ("lfCharSet", wintypes.BYTE),
        ("lfOutPrecision", wintypes.BYTE),
        ("lfClipPrecision", wintypes.BYTE),
        ("lfQuality", wintypes.BYTE),
        ("lfPitchAndFamily", wintypes.BYTE),
        ("lfFaceName", wintypes.WCHAR * 32),
    ]


class WNDCLASSEXW(ctypes.Structure):
    pass


WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


WNDCLASSEXW._fields_ = [
    ("cbSize", wintypes.UINT),
    ("style", wintypes.UINT),
    ("lpfnWndProc", WNDPROC),
    ("cbClsExtra", ctypes.c_int),
    ("cbWndExtra", ctypes.c_int),
    ("hInstance", HINSTANCE),
    ("hIcon", HICON),
    ("hCursor", HCURSOR),
    ("hbrBackground", HBRUSH),
    ("lpszMenuName", wintypes.LPCWSTR),
    ("lpszClassName", wintypes.LPCWSTR),
    ("hIconSm", HICON),
]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", HICON),
    ]


# ============================================================
# DLLs
# ============================================================

user32 = ctypes.WinDLL(
    "user32",
    use_last_error=True,
)

kernel32 = ctypes.WinDLL(
    "kernel32",
    use_last_error=True,
)

shell32 = ctypes.WinDLL(
    "shell32",
    use_last_error=True,
)

gdi32 = ctypes.WinDLL(
    "gdi32",
    use_last_error=True,
)


# ============================================================
# API declarations
# ============================================================

user32.RegisterClassExW.argtypes = [
    ctypes.POINTER(WNDCLASSEXW)
]
user32.RegisterClassExW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    HWND,
    HMENU,
    HINSTANCE,
    ctypes.c_void_p,
]
user32.CreateWindowExW.restype = HWND

user32.DestroyWindow.argtypes = [
    HWND
]
user32.DestroyWindow.restype = wintypes.BOOL

user32.DefWindowProcW.argtypes = [
    HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LRESULT

user32.ShowWindow.argtypes = [
    HWND,
    ctypes.c_int,
]
user32.ShowWindow.restype = wintypes.BOOL

user32.UpdateWindow.argtypes = [
    HWND
]
user32.UpdateWindow.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [
    HWND
]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.SetFocus.argtypes = [
    HWND
]
user32.SetFocus.restype = HWND

user32.SetWindowTextW.argtypes = [
    HWND,
    wintypes.LPCWSTR,
]
user32.SetWindowTextW.restype = wintypes.BOOL

user32.SendMessageW.argtypes = [
    HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.SendMessageW.restype = LRESULT

user32.InvalidateRect.argtypes = [
    HWND,
    ctypes.POINTER(RECT),
    wintypes.BOOL,
]
user32.InvalidateRect.restype = wintypes.BOOL

user32.BeginPaint.argtypes = [
    HWND,
    ctypes.POINTER(PAINTSTRUCT),
]
user32.BeginPaint.restype = HANDLE

user32.EndPaint.argtypes = [
    HWND,
    ctypes.POINTER(PAINTSTRUCT),
]
user32.EndPaint.restype = wintypes.BOOL

user32.FillRect.argtypes = [
    HANDLE,
    ctypes.POINTER(RECT),
    HBRUSH,
]
user32.FillRect.restype = ctypes.c_int

user32.GetClientRect.argtypes = [
    HWND,
    ctypes.POINTER(RECT),
]
user32.GetClientRect.restype = wintypes.BOOL

user32.GetSystemMetrics.argtypes = [
    ctypes.c_int
]
user32.GetSystemMetrics.restype = ctypes.c_int

user32.AdjustWindowRectEx.argtypes = [
    ctypes.POINTER(RECT),
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
user32.AdjustWindowRectEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [
    ctypes.POINTER(MSG),
    HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.c_int

user32.TranslateMessage.argtypes = [
    ctypes.POINTER(MSG)
]

user32.DispatchMessageW.argtypes = [
    ctypes.POINTER(MSG)
]

user32.PostQuitMessage.argtypes = [
    ctypes.c_int
]

user32.PostMessageW.argtypes = [
    HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostMessageW.restype = wintypes.BOOL

user32.RegisterHotKey.argtypes = [
    HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [
    HWND,
    ctypes.c_int,
]
user32.UnregisterHotKey.restype = wintypes.BOOL

user32.GetAsyncKeyState.argtypes = [
    ctypes.c_int
]
user32.GetAsyncKeyState.restype = wintypes.SHORT

user32.GetCursorPos.argtypes = [
    ctypes.POINTER(POINT)
]
user32.GetCursorPos.restype = wintypes.BOOL

user32.MessageBoxW.argtypes = [
    HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.UINT,
]
user32.MessageBoxW.restype = ctypes.c_int

user32.RegisterWindowMessageW.argtypes = [
    wintypes.LPCWSTR,
]
user32.RegisterWindowMessageW.restype = wintypes.UINT

user32.LoadIconW.argtypes = [
    HINSTANCE,
    wintypes.LPCWSTR,
]
user32.LoadIconW.restype = HICON

user32.LoadCursorW.argtypes = [
    HINSTANCE,
    wintypes.LPCWSTR,
]
user32.LoadCursorW.restype = HCURSOR

user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = HMENU

user32.AppendMenuW.argtypes = [
    HMENU,
    wintypes.UINT,
    ULONG_PTR,
    wintypes.LPCWSTR,
]
user32.AppendMenuW.restype = wintypes.BOOL

user32.TrackPopupMenu.argtypes = [
    HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    HWND,
    ctypes.POINTER(RECT),
]
user32.TrackPopupMenu.restype = wintypes.UINT

user32.DestroyMenu.argtypes = [
    HMENU
]
user32.DestroyMenu.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [
    wintypes.LPCWSTR
]
kernel32.GetModuleHandleW.restype = HMODULE

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

kernel32.CreateMutexW.argtypes = [
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.LPCWSTR,
]
kernel32.CreateMutexW.restype = HANDLE

kernel32.CloseHandle.argtypes = [
    HANDLE
]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.Sleep.argtypes = [
    wintypes.DWORD
]
kernel32.Sleep.restype = None

shell32.Shell_NotifyIconW.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(NOTIFYICONDATAW),
]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

gdi32.CreateSolidBrush.argtypes = [
    wintypes.COLORREF
]
gdi32.CreateSolidBrush.restype = HBRUSH

gdi32.CreateFontIndirectW.argtypes = [
    ctypes.POINTER(LOGFONTW)
]
gdi32.CreateFontIndirectW.restype = HFONT

gdi32.DeleteObject.argtypes = [
    HGDIOBJ
]
gdi32.DeleteObject.restype = wintypes.BOOL

gdi32.SetBkMode.argtypes = [
    HANDLE,
    ctypes.c_int,
]
gdi32.SetBkMode.restype = ctypes.c_int

gdi32.SetTextColor.argtypes = [
    HANDLE,
    wintypes.COLORREF,
]
gdi32.SetTextColor.restype = wintypes.COLORREF


# ============================================================
# Globals
# ============================================================

main_hwnd = None
status_hwnd = None
detail_hwnd = None
hotkey_hwnd = None
adapter_hwnd = None
admin_hwnd = None

toggle_button = None
hotkey_button = None
refresh_button = None

tray_added = False

offline = False
busy = False
capture_mode = False
shutdown_requested = False

hotkey_vk = DEFAULT_VK
hotkey_mod = DEFAULT_MOD

adapter_text_pending = None
pending_error = None

adapter_lock = threading.Lock()
error_lock = threading.Lock()
state_lock = threading.RLock()

mutex_handle = None
background_brush = None

font_handles = []

CLASS_NAME = "GuaguaNetToggleNativeV2"

TASKBAR_CREATED = user32.RegisterWindowMessageW(
    "TaskbarCreated"
)


# ============================================================
# Colors
# COLORREF 0x00BBGGRR
# ============================================================

COLOR_BG = 0x00F7F7F7
COLOR_TEXT = 0x001D1D1F
COLOR_SECONDARY = 0x006E6E73
COLOR_GREEN = 0x0034C759
COLOR_RED = 0x003B3BFF


# ============================================================
# Utility
# ============================================================

def make_int_resource(value):
    return ctypes.cast(
        ctypes.c_void_p(value),
        wintypes.LPCWSTR,
    )


def is_admin():
    try:
        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except Exception:
        return False


def set_text(hwnd, text):
    if hwnd:
        user32.SetWindowTextW(
            hwnd,
            str(text),
        )


def show_error(title, text):

    user32.MessageBoxW(
        main_hwnd,
        str(text),
        title,
        MB_OK | MB_ICONERROR,
    )


def show_warning(title, text):

    user32.MessageBoxW(
        main_hwnd,
        str(text),
        title,
        MB_OK | MB_ICONWARNING,
    )


# ============================================================
# PowerShell
# ============================================================

def run_powershell(command):

    process = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    if process.returncode != 0:

        error = process.stderr.strip()

        raise RuntimeError(
            error or "PowerShell 执行失败"
        )

    return process.stdout.strip()


# ============================================================
# Firewall
# ============================================================

firewall_ready = False


def prepare_firewall_rules():
    """启动时一次性准备两条 Disabled 规则。"""
    global firewall_ready

    command = f"""
$ruleOut = Get-NetFirewallRule -Name '{RULE_OUT}' -ErrorAction SilentlyContinue
if (-not $ruleOut) {{
    New-NetFirewallRule `
        -Name '{RULE_OUT}' `
        -DisplayName '{RULE_OUT}' `
        -Group '{RULE_GROUP}' `
        -Direction Outbound `
        -Action Block `
        -Profile Any `
        -Protocol Any `
        -Enabled False `
        -ErrorAction Stop | Out-Null
}}

$ruleIn = Get-NetFirewallRule -Name '{RULE_IN}' -ErrorAction SilentlyContinue
if (-not $ruleIn) {{
    New-NetFirewallRule `
        -Name '{RULE_IN}' `
        -DisplayName '{RULE_IN}' `
        -Group '{RULE_GROUP}' `
        -Direction Inbound `
        -Action Block `
        -Profile Any `
        -Protocol Any `
        -Enabled False `
        -ErrorAction Stop | Out-Null
}}

Set-NetFirewallRule -Name '{RULE_OUT}','{RULE_IN}' -Enabled False -ErrorAction Stop
"""
    try:
        run_powershell(command)
        firewall_ready = True
        return True
    except Exception:
        firewall_ready = False
        return False


def cleanup_rules():
    """退出时只删除本程序自己的两条规则。"""
    global firewall_ready
    try:
        run_powershell(
            f"Get-NetFirewallRule -Name '{RULE_OUT}','{RULE_IN}' "
            f"-ErrorAction SilentlyContinue | "
            f"Remove-NetFirewallRule -ErrorAction SilentlyContinue"
        )
        firewall_ready = False
        return True
    except Exception:
        firewall_ready = False
        return False


def set_firewall_enabled(enabled):
    """正常切换只启用/禁用预创建规则，不创建/删除规则。"""
    global firewall_ready

    state = "yes" if enabled else "no"

    process = subprocess.run(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "set",
            "rule",
            f"group={RULE_GROUP}",
            f"new",
            f"enable={state}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    if process.returncode != 0:
        firewall_ready = False
        raise RuntimeError(
            process.stderr.strip()
            or process.stdout.strip()
            or "Windows 防火墙规则切换失败"
        )

    firewall_ready = True
    return True


def block_network():
    global offline

    if not firewall_ready:
        if not prepare_firewall_rules():
            raise RuntimeError("无法准备 Windows 防火墙规则。")

    set_firewall_enabled(True)

    with state_lock:
        offline = True


def unblock_network():
    global offline

    if not firewall_ready:
        if not prepare_firewall_rules():
            raise RuntimeError("无法准备 Windows 防火墙规则。")

    set_firewall_enabled(False)

    with state_lock:
        offline = False


def toggle_worker():

    global busy
    global pending_error

    try:

        with state_lock:
            should_unblock = offline

        if should_unblock:
            unblock_network()
        else:
            block_network()

    except Exception as error:

        with error_lock:
            pending_error = str(error)

        if main_hwnd:
            user32.PostMessageW(
                main_hwnd,
                WM_SHOW_ERROR,
                0,
                0,
            )

    finally:

        with state_lock:
            busy = False

        if main_hwnd:
            user32.PostMessageW(
                main_hwnd,
                WM_UI_REFRESH,
                0,
                0,
            )


def toggle_async():

    global busy

    with state_lock:

        if busy:
            return

        busy = True

    update_ui()

    threading.Thread(
        target=toggle_worker,
        name="GuaguaNetwork",
        daemon=True,
    ).start()


# ============================================================
# Network adapters
# ============================================================

def read_adapters():

    try:

        output = run_powershell(
            "Get-NetAdapter -Physical | "
            "Select-Object Name, Status | "
            "ConvertTo-Json -Compress"
        )

        if not output:
            return "未检测到物理网络适配器"

        data = json.loads(
            output
        )

        if isinstance(data, dict):
            data = [data]

        lines = []

        for item in data:

            name = str(
                item.get(
                    "Name",
                    "未知",
                )
            )

            status = str(
                item.get(
                    "Status",
                    "Unknown",
                )
            )

            if status.lower() == "up":

                lines.append(
                    f"●  {name}    已连接"
                )

            else:

                lines.append(
                    f"○  {name}    未连接"
                )

        return "\n".join(
            lines
        )

    except Exception as error:

        return (
            f"读取网络适配器失败：{error}"
        )


def refresh_adapters_async():

    def worker():

        global adapter_text_pending

        text = read_adapters()

        with adapter_lock:

            adapter_text_pending = text

        if main_hwnd:

            user32.PostMessageW(
                main_hwnd,
                WM_ADAPTER_REFRESH,
                0,
                0,
            )

    threading.Thread(
        target=worker,
        name="GuaguaAdapterRefresh",
        daemon=True,
    ).start()


# ============================================================
# Config
# ============================================================

def load_config():

    global hotkey_vk
    global hotkey_mod

    try:

        data = json.loads(
            CONFIG_FILE.read_text(
                encoding="utf-8"
            )
        )

        vk = int(
            data.get(
                "hotkey_vk",
                DEFAULT_VK,
            )
        )

        mod = int(
            data.get(
                "hotkey_mod",
                DEFAULT_MOD,
            )
        )

        if 1 <= vk <= 255:
            hotkey_vk = vk
        else:
            hotkey_vk = DEFAULT_VK

        hotkey_mod = mod & 0x0F

    except Exception:

        hotkey_vk = DEFAULT_VK
        hotkey_mod = DEFAULT_MOD


def save_config():

    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = CONFIG_FILE.with_suffix(
        ".tmp"
    )

    temp_file.write_text(
        json.dumps(
            {
                "hotkey_vk": int(
                    hotkey_vk
                ),
                "hotkey_mod": int(
                    hotkey_mod
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_file.replace(
        CONFIG_FILE
    )


# ============================================================
# Key names
# ============================================================

SPECIAL_KEYS = {
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "Page Up",
    0x22: "Page Down",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2C: "Print Screen",
    0x2D: "Insert",
    0x2E: "Delete",
    0x5B: "Left Win",
    0x5C: "Right Win",
    0x5D: "Menu",

    0x60: "Num 0",
    0x61: "Num 1",
    0x62: "Num 2",
    0x63: "Num 3",
    0x64: "Num 4",
    0x65: "Num 5",
    0x66: "Num 6",
    0x67: "Num 7",
    0x68: "Num 8",
    0x69: "Num 9",
    0x6A: "Num *",
    0x6B: "Num +",
    0x6D: "Num -",
    0x6E: "Num .",
    0x6F: "Num /",

    0x70: "F1",
    0x71: "F2",
    0x72: "F3",
    0x73: "F4",
    0x74: "F5",
    0x75: "F6",
    0x76: "F7",
    0x77: "F8",
    0x78: "F9",
    0x79: "F10",
    0x7A: "F11",
    0x7B: "F12",
    0x7C: "F13",
    0x7D: "F14",
    0x7E: "F15",
    0x7F: "F16",
    0x80: "F17",
    0x81: "F18",
    0x82: "F19",
    0x83: "F20",
    0x84: "F21",
    0x85: "F22",
    0x86: "F23",
    0x87: "F24",

    0x90: "Num Lock",
    0x91: "Scroll Lock",

    0xA0: "Left Shift",
    0xA1: "Right Shift",
    0xA2: "Left Ctrl",
    0xA3: "Right Ctrl",
    0xA4: "Left Alt",
    0xA5: "Right Alt",

    0xA6: "Browser Back",
    0xA7: "Browser Forward",
    0xA8: "Browser Refresh",
    0xA9: "Browser Stop",
    0xAA: "Browser Search",
    0xAB: "Browser Favorites",
    0xAC: "Browser Home",

    0xAD: "Volume Mute",
    0xAE: "Volume Down",
    0xAF: "Volume Up",
    0xB0: "Media Next",
    0xB1: "Media Previous",
    0xB2: "Media Stop",
    0xB3: "Media Play/Pause",

    0xBA: ";",
    0xBB: "=",
    0xBC: ",",
    0xBD: "-",
    0xBE: ".",
    0xBF: "/",
    0xC0: "`",
    0xDB: "[",
    0xDC: "\\",
    0xDD: "]",
    0xDE: "'",
}


def key_name(vk):

    vk = int(vk)

    if vk in SPECIAL_KEYS:
        return SPECIAL_KEYS[vk]

    if 0x30 <= vk <= 0x39:
        return chr(vk)

    if 0x41 <= vk <= 0x5A:
        return chr(vk)

    return f"VK {vk}"


def hotkey_display():

    parts = []

    if hotkey_mod & MOD_CONTROL:
        parts.append("Ctrl")

    if hotkey_mod & MOD_ALT:
        parts.append("Alt")

    if hotkey_mod & MOD_SHIFT:
        parts.append("Shift")

    if hotkey_mod & MOD_WIN:
        parts.append("Win")

    parts.append(
        key_name(hotkey_vk)
    )

    return " + ".join(
        parts
    )


def current_modifiers():

    modifiers = 0

    if user32.GetAsyncKeyState(
        0x11
    ) & 0x8000:

        modifiers |= MOD_CONTROL

    if user32.GetAsyncKeyState(
        0x12
    ) & 0x8000:

        modifiers |= MOD_ALT

    if user32.GetAsyncKeyState(
        0x10
    ) & 0x8000:

        modifiers |= MOD_SHIFT

    if (
        user32.GetAsyncKeyState(0x5B)
        & 0x8000
        or user32.GetAsyncKeyState(0x5C)
        & 0x8000
    ):

        modifiers |= MOD_WIN

    return modifiers


# ============================================================
# RegisterHotKey
# ============================================================

def register_hotkey(
    vk=None,
    modifiers=None,
):

    if vk is None:
        vk = hotkey_vk

    if modifiers is None:
        modifiers = hotkey_mod

    user32.UnregisterHotKey(
        main_hwnd,
        HOTKEY_ID,
    )

    return bool(
        user32.RegisterHotKey(
            main_hwnd,
            HOTKEY_ID,
            modifiers | MOD_NOREPEAT,
            vk,
        )
    )


# ============================================================
# Shortcut capture
# ============================================================

def begin_capture():

    global capture_mode

    if capture_mode:
        return

    capture_mode = True

    set_text(
        hotkey_button,
        "请按键",
    )

    set_text(
        hotkey_hwnd,
        "请按下新的快捷键",
    )

    user32.SetForegroundWindow(
        main_hwnd
    )

    threading.Thread(
        target=capture_watcher,
        name="GuaguaHotkeyCapture",
        daemon=True,
    ).start()


def capture_watcher():

    previous = set()

    # 第一次读取，防止点击“修改”时鼠标动作/原有键状态被误判。
    for vk in range(8, 256):

        try:

            if (
                user32.GetAsyncKeyState(vk)
                & 0x8000
            ):

                previous.add(vk)

        except Exception:
            pass

    while capture_mode:

        current = set()

        for vk in range(8, 256):

            try:

                if (
                    user32.GetAsyncKeyState(vk)
                    & 0x8000
                ):

                    current.add(vk)

            except Exception:
                pass

        newly_pressed = (
            current - previous
        )

        if newly_pressed:

            modifiers = current_modifiers()

            candidates = [
                vk
                for vk in newly_pressed
                if vk not in (
                    0x10,
                    0x11,
                    0x12,
                    0x5B,
                    0x5C,
                )
            ]

            # Escape 单独按下用于取消。
            if 0x1B in candidates and modifiers == 0:

                user32.PostMessageW(
                    main_hwnd,
                    WM_CAPTURE_KEY,
                    0x1B,
                    0,
                )

                return

            if candidates:

                vk = min(
                    candidates
                )

                user32.PostMessageW(
                    main_hwnd,
                    WM_CAPTURE_KEY,
                    vk,
                    modifiers,
                )

                return

        previous = current

        kernel32.Sleep(
            8
        )


def finish_capture(
    vk,
    modifiers,
):

    global capture_mode
    global hotkey_vk
    global hotkey_mod

    if not capture_mode:
        return

    if (
        vk == 0x1B
        and modifiers == 0
    ):

        capture_mode = False

        set_text(
            hotkey_button,
            "修改",
        )

        update_ui()

        return

    if vk in (
        0x10,
        0x11,
        0x12,
        0x5B,
        0x5C,
    ):

        return

    old_vk = hotkey_vk
    old_mod = hotkey_mod

    if not register_hotkey(
        vk,
        modifiers,
    ):

        # 恢复旧快捷键。
        register_hotkey(
            old_vk,
            old_mod,
        )

        capture_mode = False

        set_text(
            hotkey_button,
            "修改",
        )

        set_text(
            hotkey_hwnd,
            hotkey_display(),
        )

        show_warning(
            "快捷键不可用",
            "这个快捷键已被 Windows 或其他程序占用，请换一个。",
        )

        return

    hotkey_vk = int(vk)
    hotkey_mod = int(
        modifiers
    )

    try:

        save_config()

    except Exception as error:

        hotkey_vk = old_vk
        hotkey_mod = old_mod

        register_hotkey(
            old_vk,
            old_mod,
        )

        show_error(
            "快捷键保存失败",
            str(error),
        )

    capture_mode = False

    set_text(
        hotkey_button,
        "修改",
    )

    update_ui()


# ============================================================
# UI
# ============================================================

def create_font(
    size,
    weight=FW_NORMAL,
):

    lf = LOGFONTW()

    lf.lfHeight = -size
    lf.lfWeight = weight
    lf.lfCharSet = 134
    lf.lfQuality = 5
    lf.lfPitchAndFamily = 0

    # Windows 标准 UI 字体。
    # 中文系统如不存在对应字形时由 Windows 自动字体回退。
    lf.lfFaceName = "Segoe UI"

    handle = gdi32.CreateFontIndirectW(
        ctypes.byref(lf)
    )

    if handle:

        font_handles.append(
            handle
        )

    return handle


def apply_font(
    hwnd,
    size=10,
    weight=FW_NORMAL,
):

    font = create_font(
        size,
        weight,
    )

    if font:

        user32.SendMessageW(
            hwnd,
            0x0030,
            font,
            1,
        )


def create_control(
    class_name,
    text,
    style,
    x,
    y,
    w,
    h,
    control_id=0,
    size=10,
    weight=FW_NORMAL,
):

    hwnd = user32.CreateWindowExW(
        0,
        class_name,
        text,
        WS_CHILD
        | WS_VISIBLE
        | style,
        x,
        y,
        w,
        h,
        main_hwnd,
        ctypes.c_void_p(
            control_id
        ),
        kernel32.GetModuleHandleW(
            None
        ),
        None,
    )

    if not hwnd:

        raise ctypes.WinError(
            ctypes.get_last_error()
        )

    apply_font(
        hwnd,
        size,
        weight,
    )

    return hwnd


def paint_window(hwnd):

    paint = PAINTSTRUCT()

    hdc = user32.BeginPaint(
        hwnd,
        ctypes.byref(paint),
    )

    if not hdc:
        return

    client = RECT()

    user32.GetClientRect(
        hwnd,
        ctypes.byref(client),
    )

    if background_brush:

        user32.FillRect(
            hdc,
            ctypes.byref(client),
            background_brush,
        )

    user32.EndPaint(
        hwnd,
        ctypes.byref(paint),
    )


def update_ui():

    if not main_hwnd:
        return

    with state_lock:

        current_offline = offline
        current_busy = busy

    if current_busy:

        set_text(
            status_hwnd,
            "切换中…",
        )

        set_text(
            detail_hwnd,
            "正在切换网络状态",
        )

    elif current_offline:

        set_text(
            status_hwnd,
            "已断网",
        )

        set_text(
            detail_hwnd,
            "网络流量已被临时阻断",
        )

    else:

        set_text(
            status_hwnd,
            "网络正常",
        )

        set_text(
            detail_hwnd,
            "网络连接正常，可正常访问互联网",
        )

    if not capture_mode:

        set_text(
            hotkey_hwnd,
            hotkey_display(),
        )

    set_text(
        admin_hwnd,
        "已获得管理员权限"
        if is_admin()
        else "未获得管理员权限",
    )

    if tray_added:

        update_tray_tip()


# ============================================================
# Tray
# ============================================================

def tray_data():

    data = NOTIFYICONDATAW()

    data.cbSize = ctypes.sizeof(
        NOTIFYICONDATAW
    )

    data.hWnd = main_hwnd
    data.uID = 1

    data.uFlags = (
        0x00000001
        | 0x00000002
        | 0x00000004
    )

    data.uCallbackMessage = WM_TRAY

    data.hIcon = user32.LoadIconW(
        None,
        make_int_resource(
            IDI_ERROR
        ),
    )

    data.szTip = (
        f"{APP_NAME} · "
        f"{'已断网' if offline else '网络正常'}"
    )

    return data


def add_tray():

    global tray_added

    data = tray_data()

    tray_added = bool(
        shell32.Shell_NotifyIconW(
            0x00000000,
            ctypes.byref(data),
        )
    )


def recreate_tray():

    global tray_added

    tray_added = False
    add_tray()


def update_tray_tip():

    if not tray_added:
        return

    data = tray_data()

    shell32.Shell_NotifyIconW(
        0x00000001,
        ctypes.byref(data),
    )


def remove_tray():

    global tray_added

    if not tray_added:
        return

    data = tray_data()

    shell32.Shell_NotifyIconW(
        0x00000002,
        ctypes.byref(data),
    )

    tray_added = False


def show_tray_menu():

    menu = user32.CreatePopupMenu()

    user32.AppendMenuW(
        menu,
        0x00000000,
        ID_TRAY_OPEN,
        "打开主界面",
    )

    user32.AppendMenuW(
        menu,
        0x00000000,
        ID_TRAY_TOGGLE,
        "切换网络",
    )

    user32.AppendMenuW(
        menu,
        0x00000800,
        0,
        None,
    )

    user32.AppendMenuW(
        menu,
        0x00000000,
        ID_TRAY_EXIT,
        "退出程序",
    )

    point = POINT()

    user32.GetCursorPos(
        ctypes.byref(point)
    )

    user32.SetForegroundWindow(
        main_hwnd
    )

    command = user32.TrackPopupMenu(
        menu,
        0x0002 | 0x0100,
        point.x,
        point.y,
        0,
        main_hwnd,
        None,
    )

    user32.DestroyMenu(
        menu
    )

    if command == ID_TRAY_OPEN:

        show_main_window()

    elif command == ID_TRAY_TOGGLE:

        toggle_async()

    elif command == ID_TRAY_EXIT:

        request_exit()


def show_main_window():

    user32.ShowWindow(
        main_hwnd,
        SW_SHOWNORMAL,
    )

    user32.SetForegroundWindow(
        main_hwnd
    )

    update_ui()
    refresh_adapters_async()


# ============================================================
# Exit
# ============================================================

def request_exit():

    global shutdown_requested
    global capture_mode

    if shutdown_requested:
        return

    with state_lock:

        if busy:

            show_warning(
                "正在切换网络",
                "请等待当前操作完成后再退出程序。",
            )

            return

        shutdown_requested = True

    capture_mode = False

    cleanup_rules()

    user32.DestroyWindow(
        main_hwnd
    )


# ============================================================
# Window procedure
# ============================================================

def wnd_proc(
    hwnd,
    msg,
    wparam,
    lparam,
):

    global adapter_text_pending
    global pending_error
    global capture_mode

    if msg == TASKBAR_CREATED:

        recreate_tray()
        return 0

    if msg == WM_PAINT:

        paint_window(
            hwnd
        )

        return 0

    if msg == WM_CTLCOLORSTATIC:

        hdc = wparam

        gdi32.SetBkMode(
            hdc,
            TRANSPARENT,
        )

        # 统一使用 Windows 原生浅灰背景。
        gdi32.SetTextColor(
            hdc,
            COLOR_TEXT,
        )

        return background_brush

    if msg == WM_ADAPTER_REFRESH:

        with adapter_lock:

            text = adapter_text_pending
            adapter_text_pending = None

        if text is not None:

            set_text(
                adapter_hwnd,
                text,
            )

        return 0

    if msg == WM_ERROR:

        with error_lock:

            error = pending_error
            pending_error = None

        if error:

            show_error(
                "网络切换失败",
                error,
            )

        update_ui()

        return 0

    if msg == WM_UI_REFRESH:

        update_ui()

        return 0

    if msg == WM_CAPTURE_KEY:

        finish_capture(
            int(wparam),
            int(lparam),
        )

        return 0

    if msg == WM_COMMAND:

        control_id = (
            int(wparam)
            & 0xFFFF
        )

        if control_id == ID_BTN_TOGGLE:

            toggle_async()

            return 0

        if control_id == ID_BTN_HOTKEY:

            begin_capture()

            return 0

        if control_id == ID_BTN_REFRESH:

            refresh_adapters_async()

            return 0

    if msg == WM_HOTKEY:

        if not capture_mode:

            toggle_async()

        return 0

    if msg == WM_TRAY:

        if lparam in (
            WM_LBUTTONUP,
            WM_LBUTTONDBLCLK,
        ):

            show_main_window()

            return 0

        if lparam == WM_RBUTTONUP:

            show_tray_menu()

            return 0

    if msg == WM_CLOSE:

        # 关闭主窗口 = 隐藏到系统托盘。
        user32.ShowWindow(
            hwnd,
            SW_HIDE,
        )

        return 0

    if msg == WM_DESTROY:

        user32.UnregisterHotKey(
            hwnd,
            HOTKEY_ID,
        )

        remove_tray()

        cleanup_rules()

        user32.PostQuitMessage(
            0
        )

        return 0

    return user32.DefWindowProcW(
        hwnd,
        msg,
        wparam,
        lparam,
    )


# ============================================================
# Window class / create
# ============================================================

def register_window_class():

    instance = kernel32.GetModuleHandleW(
        None
    )

    proc = WNDPROC(
        wnd_proc
    )

    wc = WNDCLASSEXW()

    wc.cbSize = ctypes.sizeof(
        WNDCLASSEXW
    )

    wc.style = 0
    wc.lpfnWndProc = proc
    wc.cbClsExtra = 0
    wc.cbWndExtra = 0
    wc.hInstance = instance

    wc.hIcon = user32.LoadIconW(
        None,
        make_int_resource(
            IDI_ERROR
        ),
    )

    wc.hCursor = user32.LoadCursorW(
        None,
        make_int_resource(
            IDC_ARROW
        ),
    )

    wc.hbrBackground = None
    wc.lpszMenuName = None
    wc.lpszClassName = CLASS_NAME
    wc.hIconSm = wc.hIcon

    atom = user32.RegisterClassExW(
        ctypes.byref(wc)
    )

    if not atom:

        error = ctypes.get_last_error()

        if error != 1410:

            raise ctypes.WinError(
                error
            )

    # 必须保持 Python 回调引用。
    register_window_class.proc = proc


def create_main_window():

    global main_hwnd
    global status_hwnd
    global detail_hwnd
    global hotkey_hwnd
    global adapter_hwnd
    global admin_hwnd
    global toggle_button
    global hotkey_button
    global refresh_button
    global background_brush

    instance = kernel32.GetModuleHandleW(
        None
    )

    style = (
        WS_OVERLAPPED
        | WS_CAPTION
        | WS_SYSMENU
        | WS_MINIMIZEBOX
    )

    exstyle = WS_EX_APPWINDOW

    rect = RECT(
        0,
        0,
        400,
        600,
    )

    user32.AdjustWindowRectEx(
        ctypes.byref(rect),
        style,
        False,
        exstyle,
    )

    outer_width = (
        rect.right - rect.left
    )

    outer_height = (
        rect.bottom - rect.top
    )

    screen_width = user32.GetSystemMetrics(
        SM_CXSCREEN
    )

    screen_height = user32.GetSystemMetrics(
        SM_CYSCREEN
    )

    x = max(
        0,
        (screen_width - outer_width) // 2,
    )

    y = max(
        0,
        (screen_height - outer_height) // 2,
    )

    main_hwnd = user32.CreateWindowExW(
        exstyle,
        CLASS_NAME,
        APP_NAME,
        style,
        x,
        y,
        outer_width,
        outer_height,
        None,
        None,
        instance,
        None,
    )

    if not main_hwnd:

        raise ctypes.WinError(
            ctypes.get_last_error()
        )

    background_brush = (
        gdi32.CreateSolidBrush(
            COLOR_BG
        )
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    create_control(
        "STATIC",
        APP_NAME,
        SS_LEFTNOWORDWRAP,
        24,
        22,
        340,
        30,
        size=17,
        weight=FW_SEMIBOLD,
    )

    create_control(
        "STATIC",
        "快速切换系统网络状态",
        SS_LEFTNOWORDWRAP,
        24,
        53,
        340,
        20,
        size=9,
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "当前状态",
        SS_LEFTNOWORDWRAP,
        24,
        94,
        120,
        20,
        size=9,
        weight=FW_SEMIBOLD,
    )

    status_hwnd = create_control(
        "STATIC",
        "网络正常",
        SS_LEFTNOWORDWRAP,
        24,
        119,
        220,
        31,
        size=18,
        weight=FW_SEMIBOLD,
    )

    detail_hwnd = create_control(
        "STATIC",
        "网络连接正常，可正常访问互联网",
        SS_LEFT,
        24,
        153,
        245,
        36,
        size=8,
    )

    toggle_button = create_control(
        "BUTTON",
        "立即切换",
        BS_DEFPUSHBUTTON | WS_TABSTOP,
        276,
        112,
        88,
        36,
        ID_BTN_TOGGLE,
        size=9,
        weight=FW_SEMIBOLD,
    )

    # --------------------------------------------------------
    # Settings
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "设置",
        SS_LEFTNOWORDWRAP,
        24,
        218,
        200,
        22,
        size=9,
        weight=FW_SEMIBOLD,
    )

    create_control(
        "STATIC",
        "断网快捷键",
        SS_LEFTNOWORDWRAP,
        24,
        252,
        80,
        22,
        size=9,
    )

    hotkey_hwnd = create_control(
        "STATIC",
        hotkey_display(),
        SS_LEFTNOWORDWRAP,
        125,
        252,
        145,
        22,
        size=10,
        weight=FW_SEMIBOLD,
    )

    hotkey_button = create_control(
        "BUTTON",
        "修改",
        WS_TABSTOP,
        300,
        246,
        64,
        30,
        ID_BTN_HOTKEY,
        size=9,
    )

    create_control(
        "STATIC",
        "点击修改后直接按下新的快捷键，不会弹出额外设置窗口。",
        SS_LEFT,
        24,
        282,
        340,
        35,
        size=7,
    )

    # --------------------------------------------------------
    # Adapters
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "物理网络适配器",
        SS_LEFTNOWORDWRAP,
        24,
        330,
        200,
        22,
        size=9,
        weight=FW_SEMIBOLD,
    )

    adapter_hwnd = create_control(
        "STATIC",
        "读取中…",
        SS_LEFT,
        24,
        358,
        330,
        70,
        size=9,
    )

    # --------------------------------------------------------
    # Permission
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "管理员权限",
        SS_LEFTNOWORDWRAP,
        24,
        446,
        80,
        22,
        size=9,
    )

    admin_hwnd = create_control(
        "STATIC",
        "检测中…",
        SS_LEFTNOWORDWRAP,
        125,
        446,
        210,
        22,
        size=9,
        weight=FW_SEMIBOLD,
    )

    refresh_button = create_control(
        "BUTTON",
        "刷新",
        WS_TABSTOP,
        300,
        477,
        64,
        30,
        ID_BTN_REFRESH,
        size=9,
    )

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "Windows 防火墙临时阻断网络流量\r\n"
        "不关闭 Wi-Fi / Ethernet，不修改 IP、DNS 或路由",
        SS_LEFT,
        24,
        520,
        340,
        48,
        size=7,
    )


# ============================================================
# Message loop
# ============================================================

def message_loop():

    msg = MSG()

    while True:

        result = user32.GetMessageW(
            ctypes.byref(msg),
            None,
            0,
            0,
        )

        if result <= 0:
            break

        user32.TranslateMessage(
            ctypes.byref(msg)
        )

        user32.DispatchMessageW(
            ctypes.byref(msg)
        )


# ============================================================
# Main
# ============================================================

def main():

    global mutex_handle

    if os.name != "nt":

        print(
            "此程序仅支持 Windows。"
        )

        return

    if not is_admin():

        user32.MessageBoxW(
            None,
            "程序需要管理员权限才能控制 Windows 防火墙。\n"
            "请使用管理员身份运行。",
            APP_NAME,
            MB_OK | MB_ICONERROR,
        )

        return

    mutex_handle = kernel32.CreateMutexW(
        None,
        False,
        APP_MUTEX,
    )

    if not mutex_handle:

        raise ctypes.WinError(
            ctypes.get_last_error()
        )

    if (
        kernel32.GetLastError()
        == 183
    ):

        user32.MessageBoxW(
            None,
            "程序已经在运行中。",
            APP_NAME,
            MB_OK | MB_ICONWARNING,
        )

        kernel32.CloseHandle(
            mutex_handle
        )

        return

    load_config()

    # 启动时一次性预创建规则并保持 Disabled。
    # 即使准备失败，也允许程序启动；真正切换时再报告实际错误。
    prepare_firewall_rules()

    try:

        register_window_class()
        create_main_window()

        if not register_hotkey():

            old_vk = hotkey_vk
            old_mod = hotkey_mod

            hotkey_vk = DEFAULT_VK
            hotkey_mod = DEFAULT_MOD

            if not register_hotkey():

                hotkey_vk = old_vk
                hotkey_mod = old_mod

                show_error(
                    "快捷键注册失败",
                    "Home 也无法注册，请检查是否有其他程序占用快捷键。",
                )

            else:

                save_config()

        add_tray()

        user32.ShowWindow(
            main_hwnd,
            SW_SHOWNORMAL,
        )

        user32.UpdateWindow(
            main_hwnd
        )

        update_ui()
        refresh_adapters_async()

        message_loop()

    finally:

        user32.UnregisterHotKey(
            main_hwnd,
            HOTKEY_ID,
        )

        cleanup_rules()
        remove_tray()

        if background_brush:

            gdi32.DeleteObject(
                background_brush
            )

        for font in font_handles:

            try:

                gdi32.DeleteObject(
                    font
                )

            except Exception:
                pass

        if mutex_handle:

            kernel32.CloseHandle(
                mutex_handle
            )


if __name__ == "__main__":
    main()
