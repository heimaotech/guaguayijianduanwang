
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
# Windows 原生轻量稳定版
#
# 核心设计：
#   1. 纯 Win32 GUI
#   2. 原生 Shell_NotifyIcon 托盘
#   3. 不使用 Tkinter / pystray / Pillow / Qt / Electron
#   4. 正常运行时只监听“当前设置的一个按键”
#   5. 使用 GetAsyncKeyState，独立高优先级线程，不依赖键盘 Hook
#   6. 修改快捷键时临时扫描所有 VK，完成后立即停止扫描
#   7. 防火墙只创建本程序自己的两条规则
#   8. 不禁用 Wi-Fi / Ethernet，不修改 IP / DNS / 路由
# ============================================================


APP_NAME = "呱呱一键断网与恢复"

CONFIG_DIR = (
    Path(os.environ.get("APPDATA", str(Path.home())))
    / "GuaguaNetToggle"
)
CONFIG_FILE = CONFIG_DIR / "config.json"

APP_MUTEX = "Local\\GuaguaNetToggle.SingleInstance"

WINDOW_WIDTH = 400
WINDOW_HEIGHT = 600

# 默认 Home
DEFAULT_VK = 0x24
DEFAULT_MOD = 0x0000

# 防火墙规则使用精确 Name。
# 只操作这两条规则。
RULE_OUT = "GuaguaNetToggle_Block_Outbound"
RULE_IN = "GuaguaNetToggle_Block_Inbound"

# 控件 ID
ID_BTN_TOGGLE = 3001
ID_BTN_HOTKEY = 3002
ID_BTN_REFRESH = 3003

# 托盘菜单
ID_TRAY_OPEN = 4001
ID_TRAY_TOGGLE = 4002
ID_TRAY_EXIT = 4003

# Windows message
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_HOTKEY = 0x0312
WM_CTLCOLORSTATIC = 0x0138
WM_APP = 0x8000
WM_UI_REFRESH = WM_APP + 1
WM_ADAPTER_REFRESH = WM_APP + 2
WM_CAPTURE_RESULT = WM_APP + 3
WM_ERROR = WM_APP + 4
WM_TRAY = WM_APP + 5

# 托盘事件
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

# 窗口样式
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

CW_USEDEFAULT = 0x80000000

SM_CXSCREEN = 0
SM_CYSCREEN = 1

IDI_APPLICATION = 32512
IDC_ARROW = 32512

# 热键修饰键（用于保存/显示）
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# 线程优先级
THREAD_PRIORITY_HIGHEST = 2

# 单键修饰符 VK
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_ALT = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_ESCAPE = 0x1B


# ============================================================
# Handle aliases
# 不使用 wintypes.HCURSOR / HICON / HHOOK 等不存在于部分
# Python 版本中的类型别名。
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
HDC = HANDLE

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
        ("hdc", HDC),
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
# Win32 API declarations
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

user32.DestroyWindow.argtypes = [HWND]
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

user32.GetAsyncKeyState.argtypes = [
    ctypes.c_int
]
user32.GetAsyncKeyState.restype = wintypes.SHORT

user32.GetCursorPos.argtypes = [
    ctypes.POINTER(POINT)
]
user32.GetCursorPos.restype = wintypes.BOOL

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

user32.MessageBoxW.argtypes = [
    HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.UINT,
]
user32.MessageBoxW.restype = ctypes.c_int

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

user32.EnableWindow.argtypes = [
    HWND,
    wintypes.BOOL,
]
user32.EnableWindow.restype = wintypes.BOOL

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

kernel32.GetCurrentThread.argtypes = []
kernel32.GetCurrentThread.restype = HANDLE

kernel32.SetThreadPriority.argtypes = [
    HANDLE,
    ctypes.c_int,
]
kernel32.SetThreadPriority.restype = wintypes.BOOL

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
    HDC,
    ctypes.c_int,
]
gdi32.SetBkMode.restype = ctypes.c_int

gdi32.SetTextColor.argtypes = [
    HDC,
    wintypes.COLORREF,
]
gdi32.SetTextColor.restype = wintypes.COLORREF

user32.FillRect.argtypes = [
    HDC,
    ctypes.POINTER(RECT),
    HBRUSH,
]
user32.FillRect.restype = ctypes.c_int

user32.GetClientRect.argtypes = [
    HWND,
    ctypes.POINTER(RECT)
]
user32.GetClientRect.restype = wintypes.BOOL

user32.BeginPaint.argtypes = [
    HWND,
    ctypes.POINTER(PAINTSTRUCT),
]
user32.BeginPaint.restype = HDC

user32.EndPaint.argtypes = [
    HWND,
    ctypes.POINTER(PAINTSTRUCT),
]
user32.EndPaint.restype = wintypes.BOOL


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

background_brush = None
font_handles = []

tray_added = False

offline = False
busy = False
capture_mode = False
shutdown_requested = False

hotkey_vk = DEFAULT_VK
hotkey_mod = DEFAULT_MOD

adapter_text_pending = None
pending_error = None

state_lock = threading.RLock()
adapter_lock = threading.Lock()
error_lock = threading.Lock()

mutex_handle = None

# 键盘线程控制
keyboard_thread = None
keyboard_stop = threading.Event()

# 修改快捷键后，需要等当前按键释放，防止立即触发。
hotkey_wait_release = True

CLASS_NAME = "GuaguaNetToggleNativeStable"


# ============================================================
# Basic helpers
# ============================================================

def make_int_resource(value):
    return ctypes.cast(
        ctypes.c_void_p(value),
        wintypes.LPCWSTR,
    )


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


def is_admin():
    try:
        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except Exception:
        return False


# ============================================================
# PowerShell + firewall
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
        raise RuntimeError(
            process.stderr.strip()
            or "PowerShell 执行失败"
        )

    return process.stdout.strip()


def run_netsh(args):
    process = subprocess.run(
        ["netsh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    if process.returncode != 0:
        raise RuntimeError(
            process.stderr.strip()
            or process.stdout.strip()
            or "netsh 执行失败"
        )

    return process.stdout.strip()


def cleanup_firewall_rules():
    """
    只清理本程序自己的规则。
    启动时失败不会阻止程序启动。
    """

    ps_ok = False

    try:
        run_powershell(
            f"Get-NetFirewallRule -Name '{RULE_OUT}','{RULE_IN}' "
            f"-ErrorAction SilentlyContinue | "
            f"Remove-NetFirewallRule "
            f"-ErrorAction SilentlyContinue"
        )
        ps_ok = True
    except Exception:
        pass

    # PowerShell 失败时，再用 Windows 自带 netsh 清理。
    try:
        run_netsh([
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            f"name={RULE_OUT}",
        ])
    except Exception:
        pass

    try:
        run_netsh([
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            f"name={RULE_IN}",
        ])
    except Exception:
        pass

    return ps_ok


def block_network():
    """
    创建两条系统级防火墙规则：
        Outbound Block
        Inbound Block

    不触碰任何网络适配器。
    """

    cleanup_firewall_rules()

    ps_command = f"""
New-NetFirewallRule `
    -Name '{RULE_OUT}' `
    -DisplayName '{RULE_OUT}' `
    -Direction Outbound `
    -Action Block `
    -Profile Any `
    -Protocol Any `
    -ErrorAction Stop | Out-Null

New-NetFirewallRule `
    -Name '{RULE_IN}' `
    -DisplayName '{RULE_IN}' `
    -Direction Inbound `
    -Action Block `
    -Profile Any `
    -Protocol Any `
    -ErrorAction Stop | Out-Null
"""

    try:

        run_powershell(
            ps_command
        )

    except Exception:

        # 如果 PowerShell 不可用，用 Windows 原生 netsh。
        try:

            run_netsh([
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={RULE_OUT}",
                "dir=out",
                "action=block",
                "enable=yes",
                "profile=any",
            ])

            run_netsh([
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={RULE_IN}",
                "dir=in",
                "action=block",
                "enable=yes",
                "profile=any",
            ])

        except Exception:

            cleanup_firewall_rules()
            raise

    return True


def unblock_network():
    """
    删除本程序自己的两条规则。
    如果第一种方式失败，会继续尝试 netsh。
    """

    ps_error = None

    try:

        run_powershell(
            f"Get-NetFirewallRule "
            f"-Name '{RULE_OUT}','{RULE_IN}' "
            f"-ErrorAction SilentlyContinue | "
            f"Remove-NetFirewallRule "
            f"-ErrorAction Stop"
        )

        return True

    except Exception as error:

        ps_error = error

    # netsh fallback
    success = True

    for name in (
        RULE_OUT,
        RULE_IN,
    ):

        try:

            run_netsh([
                "advfirewall",
                "firewall",
                "delete",
                "rule",
                f"name={name}",
            ])

        except Exception:

            success = False

    if success:
        return True

    raise RuntimeError(
        str(ps_error)
        if ps_error
        else "无法删除呱呱创建的防火墙规则。"
    )


# ============================================================
# Network toggle worker
# ============================================================

def toggle_worker():

    global busy
    global offline
    global pending_error

    try:

        with state_lock:
            current = offline

        if current:

            unblock_network()

            with state_lock:
                offline = False

        else:

            block_network()

            with state_lock:
                offline = True

    except Exception as error:

        with error_lock:
            pending_error = str(error)

        if main_hwnd:

            user32.PostMessageW(
                main_hwnd,
                WM_ERROR,
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

        if busy or shutdown_requested:
            return

        busy = True

    update_ui()

    threading.Thread(
        target=toggle_worker,
        name="GuaguaNetwork",
        daemon=True,
    ).start()


# ============================================================
# Adapter information
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
            f"读取适配器失败：{error}"
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

        hotkey_mod = mod & (
            MOD_ALT
            | MOD_CONTROL
            | MOD_SHIFT
            | MOD_WIN
        )

        # 修饰键不能作为目标键本身。
        if hotkey_vk in (
            VK_SHIFT,
            VK_CONTROL,
            VK_ALT,
            VK_LWIN,
            VK_RWIN,
        ):
            hotkey_vk = DEFAULT_VK
            hotkey_mod = DEFAULT_MOD

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

    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"

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
        VK_CONTROL
    ) & 0x8000:

        modifiers |= MOD_CONTROL

    if user32.GetAsyncKeyState(
        VK_ALT
    ) & 0x8000:

        modifiers |= MOD_ALT

    if user32.GetAsyncKeyState(
        VK_SHIFT
    ) & 0x8000:

        modifiers |= MOD_SHIFT

    if (
        user32.GetAsyncKeyState(
            VK_LWIN
        ) & 0x8000
        or
        user32.GetAsyncKeyState(
            VK_RWIN
        ) & 0x8000
    ):

        modifiers |= MOD_WIN

    return modifiers


# ============================================================
# High-priority keyboard polling
# ============================================================

def key_is_down(vk):

    return bool(
        user32.GetAsyncKeyState(
            int(vk)
        ) & 0x8000
    )


def capture_keys_pressed():

    result = []

    for vk in range(8, 256):

        if key_is_down(vk):
            result.append(vk)

    return result


def keyboard_worker():

    global hotkey_wait_release

    # 只提升这个轻量线程的调度优先级。
    # 不是 REALTIME，不会把系统变成高优先级进程。
    try:

        kernel32.SetThreadPriority(
            kernel32.GetCurrentThread(),
            THREAD_PRIORITY_HIGHEST,
        )

    except Exception:
        pass

    previous_target_down = False
    previous_any = set()

    while not keyboard_stop.is_set():

        # ----------------------------------------------------
        # 快捷键设置模式
        # ----------------------------------------------------

        if capture_mode:

            current = set(
                capture_keys_pressed()
            )

            newly_pressed = (
                current - previous_any
            )

            if newly_pressed:

                # Esc 单独按下 = 取消
                if (
                    VK_ESCAPE in newly_pressed
                    and current_modifiers() == 0
                ):

                    user32.PostMessageW(
                        main_hwnd,
                        WM_CAPTURE_RESULT,
                        VK_ESCAPE,
                        0,
                    )

                    previous_any = current
                    time.sleep(0.008)
                    continue

                candidates = [
                    vk
                    for vk in newly_pressed
                    if vk not in (
                        VK_SHIFT,
                        VK_CONTROL,
                        VK_ALT,
                        VK_LWIN,
                        VK_RWIN,
                    )
                ]

                if candidates:

                    vk = min(
                        candidates
                    )

                    modifiers = (
                        current_modifiers()
                    )

                    user32.PostMessageW(
                        main_hwnd,
                        WM_CAPTURE_RESULT,
                        vk,
                        modifiers,
                    )

                    previous_any = current
                    time.sleep(0.008)
                    continue

            previous_any = current

            time.sleep(0.008)
            continue

        # ----------------------------------------------------
        # 正常运行
        # ----------------------------------------------------

        with state_lock:

            target_vk = hotkey_vk
            target_mod = hotkey_mod

        current_down = key_is_down(
            target_vk
        )

        if not current_down:

            hotkey_wait_release = False

        elif (
            current_down
            and not previous_target_down
            and not hotkey_wait_release
        ):

            current_mod = (
                current_modifiers()
            )

            # 要求修饰键完全匹配。
            if current_mod == target_mod:

                toggle_async()

                hotkey_wait_release = True

        previous_target_down = (
            current_down
        )

        time.sleep(0.008)


def start_keyboard_thread():

    global keyboard_thread

    keyboard_stop.clear()

    keyboard_thread = threading.Thread(
        target=keyboard_worker,
        name="GuaguaKeyboardPriority",
        daemon=True,
    )

    keyboard_thread.start()


def stop_keyboard_thread():

    keyboard_stop.set()


# ============================================================
# Shortcut UI
# ============================================================

def begin_capture():

    global capture_mode
    global hotkey_wait_release

    if capture_mode:
        return

    capture_mode = True
    hotkey_wait_release = True

    set_text(
        hotkey_button,
        "按键中…",
    )

    set_text(
        hotkey_hwnd,
        "请按下新的快捷键",
    )

    user32.SetForegroundWindow(
        main_hwnd
    )


def finish_capture(
    vk,
    modifiers,
):

    global capture_mode
    global hotkey_vk
    global hotkey_mod
    global hotkey_wait_release

    if not capture_mode:
        return

    # Esc 取消
    if (
        vk == VK_ESCAPE
        and modifiers == 0
    ):

        capture_mode = False

        set_text(
            hotkey_button,
            "修改",
        )

        update_ui()

        return

    # 不能单独选择修饰键。
    if vk in (
        VK_SHIFT,
        VK_CONTROL,
        VK_ALT,
        VK_LWIN,
        VK_RWIN,
    ):

        return

    old_vk = hotkey_vk
    old_mod = hotkey_mod

    hotkey_vk = int(vk)
    hotkey_mod = int(
        modifiers
    )

    try:

        save_config()

    except Exception:

        hotkey_vk = old_vk
        hotkey_mod = old_mod

        show_error(
            "保存失败",
            "快捷键配置无法保存。",
        )

    capture_mode = False

    # 当前键必须释放后才重新允许触发。
    hotkey_wait_release = True

    set_text(
        hotkey_button,
        "修改",
    )

    update_ui()


# ============================================================
# Native font / UI
# ============================================================

def create_font(
    size,
    weight=FW_NORMAL,
):

    font = LOGFONTW()

    font.lfHeight = -size
    font.lfWeight = weight
    font.lfCharSet = 134
    font.lfQuality = 5
    font.lfPitchAndFamily = 0

    # Windows UI 标准字体。
    # 中文系统缺少部分字形时由系统自动 fallback。
    font.lfFaceName = (
        "Microsoft YaHei UI"
    )

    handle = (
        gdi32.CreateFontIndirectW(
            ctypes.byref(font)
        )
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
    width,
    height,
    control_id=0,
    size=9,
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
        width,
        height,
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


def draw_card(
    hdc,
    x,
    y,
    width,
    height,
):

    brush = gdi32.CreateSolidBrush(
        0x00FFFFFF
    )

    if not brush:
        return

    rect = RECT(
        x,
        y,
        x + width,
        y + height,
    )

    user32.FillRect(
        hdc,
        ctypes.byref(rect),
        brush,
    )

    gdi32.DeleteObject(
        brush
    )


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

    # 状态卡片
    draw_card(
        hdc,
        18,
        82,
        364,
        150,
    )

    # 设置卡片
    draw_card(
        hdc,
        18,
        245,
        364,
        215,
    )

    user32.EndPaint(
        hwnd,
        ctypes.byref(paint),
    )


# ============================================================
# UI refresh
# ============================================================

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
            "Windows 防火墙正在阻断系统网络流量",
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

    if capture_mode:

        set_text(
            hotkey_hwnd,
            "请按下新的快捷键",
        )

    else:

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

    user32.InvalidateRect(
        main_hwnd,
        None,
        True,
    )


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
            IDI_APPLICATION
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

    stop_keyboard_thread()

    # 无论当前 UI 状态如何，都尝试清理自己的规则。
    cleanup_firewall_rules()

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

    if msg == WM_PAINT:

        paint_window(
            hwnd
        )

        return 0

    if msg == WM_CTLCOLORSTATIC:

        hdc = wparam

        gdi32.SetBkMode(
            hdc,
            1,
        )

        gdi32.SetTextColor(
            hdc,
            0x001D1D1F,
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
                "操作失败",
                error,
            )

        update_ui()

        return 0

    if msg == WM_UI_REFRESH:

        update_ui()

        return 0

    if msg == WM_CAPTURE_RESULT:

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

        # 关闭窗口 = 隐藏到托盘。
        user32.ShowWindow(
            hwnd,
            SW_HIDE,
        )

        return 0

    if msg == WM_DESTROY:

        stop_keyboard_thread()

        remove_tray()

        cleanup_firewall_rules()

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
    wc.hInstance = instance

    wc.hIcon = user32.LoadIconW(
        None,
        make_int_resource(
            IDI_APPLICATION
        ),
    )

    wc.hCursor = user32.LoadCursorW(
        None,
        make_int_resource(
            IDC_ARROW
        ),
    )

    wc.hbrBackground = None
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

    # 保证 Python callback 一直存活。
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
        WINDOW_WIDTH,
        WINDOW_HEIGHT,
    )

    user32.AdjustWindowRectEx(
        ctypes.byref(rect),
        style,
        False,
        exstyle,
    )

    outer_width = (
        rect.right
        - rect.left
    )

    outer_height = (
        rect.bottom
        - rect.top
    )

    screen_width = user32.GetSystemMetrics(
        SM_CXSCREEN
    )

    screen_height = user32.GetSystemMetrics(
        SM_CYSCREEN
    )

    x = max(
        0,
        (
            screen_width
            - outer_width
        ) // 2,
    )

    y = max(
        0,
        (
            screen_height
            - outer_height
        ) // 2,
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
            0x00F7F7F7
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
        20,
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
        51,
        340,
        20,
        size=9,
    )

    # --------------------------------------------------------
    # Status card
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "当前状态",
        SS_LEFTNOWORDWRAP,
        35,
        103,
        120,
        20,
        size=9,
        weight=FW_SEMIBOLD,
    )

    status_hwnd = create_control(
        "STATIC",
        "网络正常",
        SS_LEFTNOWORDWRAP,
        35,
        127,
        220,
        32,
        size=18,
        weight=FW_SEMIBOLD,
    )

    detail_hwnd = create_control(
        "STATIC",
        "网络连接正常，可正常访问互联网",
        SS_LEFT,
        35,
        163,
        240,
        35,
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
        35,
        263,
        200,
        22,
        size=9,
        weight=FW_SEMIBOLD,
    )

    create_control(
        "STATIC",
        "断网快捷键",
        SS_LEFTNOWORDWRAP,
        35,
        295,
        80,
        22,
        size=9,
    )

    hotkey_hwnd = create_control(
        "STATIC",
        hotkey_display(),
        SS_LEFTNOWORDWRAP,
        125,
        295,
        165,
        22,
        size=10,
        weight=FW_SEMIBOLD,
    )

    hotkey_button = create_control(
        "BUTTON",
        "修改",
        WS_TABSTOP,
        300,
        289,
        64,
        30,
        ID_BTN_HOTKEY,
        size=9,
    )

    create_control(
        "STATIC",
        "点击“修改”后直接按下新的按键，不会弹出额外窗口。",
        SS_LEFT,
        35,
        325,
        325,
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
        35,
        360,
        200,
        22,
        size=9,
        weight=FW_SEMIBOLD,
    )

    adapter_hwnd = create_control(
        "STATIC",
        "读取中…",
        SS_LEFT,
        35,
        387,
        325,
        68,
        size=9,
    )

    # --------------------------------------------------------
    # Permission
    # --------------------------------------------------------

    create_control(
        "STATIC",
        "管理员权限",
        SS_LEFTNOWORDWRAP,
        35,
        468,
        80,
        22,
        size=9,
    )

    admin_hwnd = create_control(
        "STATIC",
        "检测中…",
        SS_LEFTNOWORDWRAP,
        125,
        468,
        180,
        22,
        size=9,
        weight=FW_SEMIBOLD,
    )

    refresh_button = create_control(
        "BUTTON",
        "刷新",
        WS_TABSTOP,
        300,
        505,
        64,
        30,
        ID_BTN_REFRESH,
        size=9,
    )

    create_control(
        "STATIC",
        "Windows 防火墙临时阻断网络流量。\r\n"
        "不关闭 Wi-Fi / Ethernet，不修改 IP、DNS 或路由。",
        SS_LEFT,
        35,
        515,
        260,
        55,
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

    # --------------------------------------------------------
    # Single instance
    # --------------------------------------------------------

    mutex_handle = kernel32.CreateMutexW(
        None,
        False,
        APP_MUTEX,
    )

    if not mutex_handle:

        raise ctypes.WinError(
            ctypes.get_last_error()
        )

    if kernel32.GetLastError() == 183:

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

    # --------------------------------------------------------
    # Admin
    # --------------------------------------------------------

    if not is_admin():

        user32.MessageBoxW(
            None,
            "程序需要管理员权限才能控制 Windows 防火墙。\n"
            "请使用管理员身份运行。",
            APP_NAME,
            MB_OK | MB_ICONERROR,
        )

        kernel32.CloseHandle(
            mutex_handle
        )

        return

    # --------------------------------------------------------
    # Config
    # --------------------------------------------------------

    load_config()

    # --------------------------------------------------------
    # 启动时只“尽量”清理自己的旧规则。
    # 失败不会阻止程序启动。
    # --------------------------------------------------------

    cleanup_firewall_rules()

    # --------------------------------------------------------
    # Window
    # --------------------------------------------------------

    register_window_class()
    create_main_window()

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

    # --------------------------------------------------------
    # 启动键盘监听线程
    # --------------------------------------------------------

    start_keyboard_thread()

    # --------------------------------------------------------
    # Win32 message loop
    # --------------------------------------------------------

    try:

        message_loop()

    finally:

        stop_keyboard_thread()

        cleanup_firewall_rules()
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
