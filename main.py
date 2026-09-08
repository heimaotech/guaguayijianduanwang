import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

# ============================================================
# 呱呱一键断网与恢复
# Windows 原生 Win32 架构
#
# 核心：
#   - Win32 GUI
#   - RegisterHotKey 全局快捷键
#   - Shell_NotifyIcon 系统托盘
#   - Windows Firewall 临时阻断网络
#   - 不禁用 Wi-Fi / Ethernet 网卡
#   - 不修改 IP / DNS / 路由
# ============================================================

APP_NAME = "呱呱一键断网与恢复"
APP_VERSION = "2.0.0"

WIDTH = 400
HEIGHT = 600

VK_HOME = 0x24
HOTKEY_ID = 1001
WM_TRAY = 0x8001
WM_APP_REFRESH = 0x8002
WM_APP_HOTKEY_CAPTURED = 0x8003

RULE_PREFIX = "GuaguaNetToggle"

CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "GuaguaNetToggle"
CONFIG_FILE = CONFIG_DIR / "config.json"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

# ---------- 基础类型 ----------
LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

# ---------- 常量 ----------
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_HOTKEY = 0x0312
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_NCLBUTTONDBLCLK = 0x00A3

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_EX_APPWINDOW = 0x00040000

CW_USEDEFAULT = 0x80000000

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNORMAL = 1

IDI_APPLICATION = 32512
IDC_ARROW = 32512

COLOR_WINDOW = 5

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

ID_TRAY_OPEN = 2001
ID_TRAY_TOGGLE = 2002
ID_TRAY_EXIT = 2003

ID_BTN_TOGGLE = 3001
ID_BTN_HOTKEY = 3002
ID_BTN_REFRESH = 3003

WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001
ES_LEFT = 0x0000
SS_LEFT = 0x00000000

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004

DEFAULT_GUI_FONT = 17
FW_NORMAL = 400
FW_SEMIBOLD = 600

# ---------- Win32 结构 ----------
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
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
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]

# ---------- API 声明 ----------
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DefWindowProcW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
user32.DefWindowProcW.restype = LRESULT

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON

user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HCURSOR

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user32.SetWindowTextW.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.EnableWindow.restype = wintypes.BOOL

user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wintypes.HWND

user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT_PTR, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, ctypes.POINTER(RECT)
]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]

user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT), wintypes.BOOL]

shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# ---------- GDI ----------
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

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

gdi32.CreateFontIndirectW.argtypes = [ctypes.POINTER(LOGFONTW)]
gdi32.CreateFontIndirectW.restype = wintypes.HFONT
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = wintypes.HGDIOBJ

# ---------- 运行状态 ----------
main_hwnd = None
status_hwnd = None
detail_hwnd = None
hotkey_hwnd = None
adapter_hwnd = None
admin_hwnd = None
toggle_btn = None
hotkey_btn = None
refresh_btn = None

tray_added = False
offline = False
busy = False
capture_mode = False
capture_token = 0

hotkey_vk = VK_HOME
hotkey_mod = 0

network_thread = None

# 控件自定义颜色
WHITE = 0x00FFFFFF
BLACK = 0x001D1D1F
GRAY = 0x006E6E73
LIGHT_GRAY = 0x00F5F5F7
BLUE = 0x00FF7A00  # BGR = #007AFF
GREEN = 0x00C75934
RED = 0x003B3BFF

FONT_NAME = "Microsoft YaHei UI"

# ---------- 辅助 ----------
def rgb(r, g, b):
    return (b << 16) | (g << 8) | r

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def ps(command, timeout=20):
    p = subprocess.run(
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
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "PowerShell 执行失败")
    return p.stdout.strip()

def cleanup_rules():
    try:
        ps(
            f"Get-NetFirewallRule -DisplayName '{RULE_PREFIX}_*' "
            f"-ErrorAction SilentlyContinue | "
            f"Remove-NetFirewallRule -ErrorAction SilentlyContinue"
        )
    except Exception:
        pass

def block_network():
    global offline
    command = f"""
$old = Get-NetFirewallRule -DisplayName '{RULE_PREFIX}_*' -ErrorAction SilentlyContinue
if ($old) {{ $old | Remove-NetFirewallRule -ErrorAction SilentlyContinue }}
New-NetFirewallRule -DisplayName '{RULE_PREFIX}_Block_Outbound' -Direction Outbound -Action Block -Profile Any -Protocol Any -ErrorAction Stop | Out-Null
New-NetFirewallRule -DisplayName '{RULE_PREFIX}_Block_Inbound' -Direction Inbound -Action Block -Profile Any -Protocol Any -ErrorAction Stop | Out-Null
"""
    ps(command)
    offline = True

def unblock_network():
    global offline
    ps(
        f"Get-NetFirewallRule -DisplayName '{RULE_PREFIX}_*' "
        f"-ErrorAction SilentlyContinue | "
        f"Remove-NetFirewallRule -ErrorAction SilentlyContinue"
    )
    offline = False

def toggle_network():
    global busy
    if busy:
        return
    busy = True
    update_ui()
    try:
        if offline:
            unblock_network()
        else:
            block_network()
    except Exception as e:
        show_error("网络切换失败", str(e))
    finally:
        busy = False
        update_ui()

def toggle_async():
    global network_thread
    if busy:
        return
    network_thread = threading.Thread(target=toggle_network, daemon=True)
    network_thread.start()

def get_adapters_text():
    try:
        output = ps(
            "Get-NetAdapter -Physical | "
            "Select-Object Name, Status | ConvertTo-Json -Compress"
        )
        if not output:
            return "未检测到物理网络适配器"
        data = json.loads(output)
        if not isinstance(data, list):
            data = [data]
        lines = []
        for item in data:
            name = str(item.get("Name", "未知"))
            state = str(item.get("Status", "Unknown"))
            if state.lower() == "up":
                lines.append(f"●  {name}    已连接")
            else:
                lines.append(f"○  {name}    未连接")
        return "\n".join(lines)
    except Exception as e:
        return f"读取网络适配器失败：{e}"

def load_config():
    global hotkey_vk, hotkey_mod
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        vk = int(data.get("hotkey_vk", VK_HOME))
        mod = int(data.get("hotkey_mod", 0))
        if 1 <= vk <= 255:
            hotkey_vk = vk
        else:
            hotkey_vk = VK_HOME
        hotkey_mod = mod & 0x0F
    except Exception:
        hotkey_vk = VK_HOME
        hotkey_mod = 0

def save_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"hotkey_vk": hotkey_vk, "hotkey_mod": hotkey_mod},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(CONFIG_FILE)

SPECIAL = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter",
    0x10: "Shift", 0x11: "Ctrl", 0x12: "Alt",
    0x13: "Pause", 0x14: "Caps Lock", 0x1B: "Esc",
    0x20: "Space", 0x21: "Page Up", 0x22: "Page Down",
    0x23: "End", 0x24: "Home", 0x25: "Left", 0x26: "Up",
    0x27: "Right", 0x28: "Down", 0x2C: "Print Screen",
    0x2D: "Insert", 0x2E: "Delete", 0x5B: "Left Win",
    0x5C: "Right Win", 0x5D: "Menu",
    0x90: "Num Lock", 0x91: "Scroll Lock",
    0xA0: "Left Shift", 0xA1: "Right Shift",
    0xA2: "Left Ctrl", 0xA3: "Right Ctrl",
    0xA4: "Left Alt", 0xA5: "Right Alt",
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -",
    0x6E: "Num .", 0x6F: "Num /",
    0xAD: "Volume Mute", 0xAE: "Volume Down", 0xAF: "Volume Up",
    0xB0: "Media Next", 0xB1: "Media Previous",
    0xB2: "Media Stop", 0xB3: "Media Play/Pause",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-",
    0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[",
    0xDC: "\\", 0xDD: "]", 0xDE: "'",
}

def key_name(vk):
    if vk in SPECIAL:
        return SPECIAL[vk]
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return f"VK {vk}"

def hotkey_display():
    parts = []
    if hotkey_mod & 0x0001:
        parts.append("Alt")
    if hotkey_mod & 0x0002:
        parts.append("Ctrl")
    if hotkey_mod & 0x0004:
        parts.append("Shift")
    if hotkey_mod & 0x0008:
        parts.append("Win")
    parts.append(key_name(hotkey_vk))
    return " + ".join(parts)

# ---------- 原生控件 ----------
def set_font(hwnd, size=10, weight=FW_NORMAL):
    lf = LOGFONTW()
    lf.lfHeight = -size
    lf.lfWeight = weight
    lf.lfCharSet = 134
    lf.lfQuality = 5
    lf.lfPitchAndFamily = 0
    lf.lfFaceName = FONT_NAME
    hfont = gdi32.CreateFontIndirectW(ctypes.byref(lf))
    if hfont:
        user32.SendMessageW(hwnd, 0x0030, hfont, 1)
    return hfont

def create_control(class_name, text, style, x, y, w, h, control_id=0):
    hwnd = user32.CreateWindowExW(
        0,
        class_name,
        text,
        WS_CHILD | WS_VISIBLE | style,
        x, y, w, h,
        main_hwnd,
        control_id,
        kernel32.GetModuleHandleW(None),
        None,
    )
    set_font(hwnd, 10, FW_NORMAL)
    return hwnd

def set_text(hwnd, text):
    if hwnd:
        user32.SetWindowTextW(hwnd, text)

def show_error(title, text):
    user32.MessageBoxW(main_hwnd, text, title, 0x00000010)

def center_window(hwnd):
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    x = max(0, (sw - WIDTH) // 2)
    y = max(0, (sh - HEIGHT) // 2)
    user32.SetWindowPos(hwnd, 0, x, y, WIDTH, HEIGHT, 0)

# ---------- UI ----------
def update_ui():
    if not main_hwnd:
        return
    if offline:
        set_text(status_hwnd, "已断网")
        set_text(detail_hwnd, "所有网络流量已被临时阻断")
    elif busy:
        set_text(status_hwnd, "切换中…")
        set_text(detail_hwnd, "正在切换网络状态")
    else:
        set_text(status_hwnd, "网络正常")
        set_text(detail_hwnd, "网络连接正常，可正常访问互联网")

    set_text(hotkey_hwnd, hotkey_display())
    set_text(admin_hwnd, "已获得管理员权限" if is_admin() else "未获得管理员权限")
    user32.InvalidateRect(main_hwnd, None, True)

def refresh_adapters():
    def worker():
        text = get_adapters_text()
        if main_hwnd:
            set_text(adapter_hwnd, text)
    threading.Thread(target=worker, daemon=True).start()

def begin_capture():
    global capture_mode, capture_token
    if capture_mode:
        return
    capture_mode = True
    capture_token += 1
    set_text(hotkey_btn, "请按键…")
    set_text(hotkey_hwnd, "请按下新的快捷键")
    user32.SetForegroundWindow(main_hwnd)

def handle_capture(vk, modifiers):
    global capture_mode, hotkey_vk, hotkey_mod
    if not capture_mode:
        return

    if vk == 0x1B:  # Esc
        capture_mode = False
        set_text(hotkey_btn, "修改")
        update_ui()
        return

    # RegisterHotKey 对单键及标准组合键支持最好。
    # 保存用户实际按下的 VK 和修饰键。
    new_mod = modifiers & 0x0F

    # 避免单独使用 Win/Alt/Ctrl/Shift 造成体验问题。
    if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):
        return

    # 先取消旧快捷键
    user32.UnregisterHotKey(main_hwnd, HOTKEY_ID)

    if not user32.RegisterHotKey(
        main_hwnd,
        HOTKEY_ID,
        new_mod,
        vk,
    ):
        # 恢复旧快捷键
        user32.RegisterHotKey(
            main_hwnd,
            HOTKEY_ID,
            hotkey_mod,
            hotkey_vk,
        )
        show_error(
            "快捷键不可用",
            "这个快捷键已被 Windows 或其它程序占用，请换一个。",
        )
        capture_mode = False
        set_text(hotkey_btn, "修改")
        update_ui()
        return

    hotkey_vk = vk
    hotkey_mod = new_mod
    save_config()

    capture_mode = False
    set_text(hotkey_btn, "修改")
    update_ui()

def current_modifiers():
    mod = 0
    if user32.GetAsyncKeyState(0x12) & 0x8000:
        mod |= 0x0001  # MOD_ALT
    if user32.GetAsyncKeyState(0x11) & 0x8000:
        mod |= 0x0002  # MOD_CONTROL
    if user32.GetAsyncKeyState(0x10) & 0x8000:
        mod |= 0x0004  # MOD_SHIFT
    if (
        user32.GetAsyncKeyState(0x5B) & 0x8000
        or user32.GetAsyncKeyState(0x5C) & 0x8000
    ):
        mod |= 0x0008  # MOD_WIN
    return mod

# ---------- 托盘 ----------
def add_tray():
    global tray_added
    data = NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    data.hWnd = main_hwnd
    data.uID = 1
    data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    data.uCallbackMessage = WM_TRAY
    data.hIcon = user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))
    data.szTip = APP_NAME
    tray_added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)))

def remove_tray():
    global tray_added
    if not tray_added:
        return
    data = NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    data.hWnd = main_hwnd
    data.uID = 1
    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
    tray_added = False

def tray_menu():
    menu = user32.CreatePopupMenu()
    user32.AppendMenuW(menu, MF_STRING, ID_TRAY_OPEN, "打开主界面")
    user32.AppendMenuW(menu, MF_STRING, ID_TRAY_TOGGLE, "切换网络")
    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(menu, MF_STRING, ID_TRAY_EXIT, "退出程序")

    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(main_hwnd)

    cmd = user32.TrackPopupMenu(
        menu,
        TPM_RIGHTBUTTON | TPM_RETURNCMD,
        pt.x, pt.y,
        0,
        main_hwnd,
        None,
    )
    user32.DestroyMenu(menu)

    if cmd == ID_TRAY_OPEN:
        show_main()
    elif cmd == ID_TRAY_TOGGLE:
        toggle_async()
    elif cmd == ID_TRAY_EXIT:
        exit_app()

def show_main():
    user32.ShowWindow(main_hwnd, SW_SHOWNORMAL)
    user32.SetForegroundWindow(main_hwnd)
    refresh_adapters()
    update_ui()

# ---------- 窗口 ----------
def paint_window(hwnd):
    # 使用系统背景 + 原生控件，避免第三方 UI 框架。
    pass

def wnd_proc(hwnd, msg, wparam, lparam):
    global main_hwnd

    if msg == WM_COMMAND:
        cid = wparam & 0xFFFF
        if cid == ID_BTN_TOGGLE:
            toggle_async()
        elif cid == ID_BTN_HOTKEY:
            begin_capture()
        elif cid == ID_BTN_REFRESH:
            refresh_adapters()
        return 0

    if msg == WM_HOTKEY:
        if capture_mode:
            return 0
        toggle_async()
        return 0

    if msg == WM_TRAY:
        if lparam in (WM_LBUTTONUP, WM_NCLBUTTONDBLCLK):
            show_main()
        elif lparam == WM_RBUTTONUP:
            tray_menu()
        return 0

    if msg == WM_CLOSE:
        user32.ShowWindow(hwnd, SW_HIDE)
        return 0

    if msg == WM_DESTROY:
        user32.UnregisterHotKey(hwnd, HOTKEY_ID)
        remove_tray()
        cleanup_rules()
        user32.PostQuitMessage(0)
        return 0

    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

def create_main_window():
    global main_hwnd
    global status_hwnd, detail_hwnd, hotkey_hwnd, adapter_hwnd, admin_hwnd
    global toggle_btn, hotkey_btn, refresh_btn

    instance = kernel32.GetModuleHandleW(None)
    class_name = "GuaguaNativeNetworkToggle"

    proc = WNDPROC(wnd_proc)

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.style = 0
    wc.lpfnWndProc = proc
    wc.hInstance = instance
    wc.hIcon = user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))
    wc.hCursor = user32.LoadCursorW(None, ctypes.cast(IDC_ARROW, wintypes.LPCWSTR))
    wc.hbrBackground = ctypes.cast((COLOR_WINDOW + 1), wintypes.HBRUSH)
    wc.lpszClassName = class_name
    wc.hIconSm = wc.hIcon

    if not user32.RegisterClassExW(ctypes.byref(wc)):
        err = ctypes.get_last_error()
        if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
            raise ctypes.WinError(err)

    # 纯 Win32 标准窗口。
    style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX
    exstyle = WS_EX_APPWINDOW

    main_hwnd = user32.CreateWindowExW(
        exstyle,
        class_name,
        APP_NAME,
        style,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        WIDTH,
        HEIGHT,
        None,
        None,
        instance,
        None,
    )

    if not main_hwnd:
        raise ctypes.WinError(ctypes.get_last_error())

    center_window(main_hwnd)

    # 标题
    title = create_control(
        "STATIC",
        APP_NAME,
        SS_LEFT,
        24, 22, 330, 28
    )
    set_font(title, 16, FW_SEMIBOLD)

    subtitle = create_control(
        "STATIC",
        "快速切换系统网络状态",
        SS_LEFT,
        24, 51, 330, 22
    )
    set_font(subtitle, 9, FW_NORMAL)

    # 状态
    create_control(
        "STATIC",
        "当前状态",
        SS_LEFT,
        24, 91, 120, 20
    )

    status_hwnd = create_control(
        "STATIC",
        "网络正常",
        SS_LEFT,
        24, 112, 230, 32
    )
    set_font(status_hwnd, 18, FW_SEMIBOLD)

    detail_hwnd = create_control(
        "STATIC",
        "网络连接正常，可正常访问互联网",
        SS_LEFT,
        24, 145, 300, 22
    )
    set_font(detail_hwnd, 9, FW_NORMAL)

    toggle_btn = create_control(
        "BUTTON",
        "立即切换",
        BS_DEFPUSHBUTTON | WS_TABSTOP,
        276, 104, 92, 36,
        ID_BTN_TOGGLE
    )
    set_font(toggle_btn, 9, FW_SEMIBOLD)

    # 分割线
    create_control(
        "STATIC",
        "设置",
        SS_LEFT,
        24, 195, 330, 22
    )

    create_control(
        "STATIC",
        "快捷键",
        SS_LEFT,
        24, 225, 80, 24
    )

    hotkey_hwnd = create_control(
        "STATIC",
        hotkey_display(),
        SS_LEFT,
        115, 225, 150, 24
    )
    set_font(hotkey_hwnd, 10, FW_SEMIBOLD)

    hotkey_btn = create_control(
        "BUTTON",
        "修改",
        WS_TABSTOP,
        300, 219, 68, 30,
        ID_BTN_HOTKEY
    )
    set_font(hotkey_btn, 9, FW_NORMAL)

    # 网络适配器
    create_control(
        "STATIC",
        "物理网络适配器",
        SS_LEFT,
        24, 274, 300, 22
    )

    adapter_hwnd = create_control(
        "STATIC",
        "读取中…",
        SS_LEFT,
        24, 300, 340, 90
    )
    set_font(adapter_hwnd, 9, FW_NORMAL)

    # 权限
    create_control(
        "STATIC",
        "权限",
        SS_LEFT,
        24, 407, 80, 22
    )

    admin_hwnd = create_control(
        "STATIC",
        "检测中…",
        SS_LEFT,
        115, 407, 220, 22
    )
    set_font(admin_hwnd, 9, FW_SEMIBOLD)

    refresh_btn = create_control(
        "BUTTON",
        "刷新",
        WS_TABSTOP,
        300, 440, 68, 30,
        ID_BTN_REFRESH
    )
    set_font(refresh_btn, 9, FW_NORMAL)

    # 底部说明
    foot = create_control(
        "STATIC",
        "断网采用 Windows 防火墙临时规则。\n"
        "不关闭 Wi-Fi / Ethernet 网卡，不修改 IP、DNS 或路由。",
        SS_LEFT,
        24, 485, 345, 55
    )
    set_font(foot, 8, FW_NORMAL)

    # 确保回调对象存活
    create_main_window._proc = proc

def register_hotkey():
    user32.UnregisterHotKey(main_hwnd, HOTKEY_ID)
    ok = user32.RegisterHotKey(
        main_hwnd,
        HOTKEY_ID,
        hotkey_mod,
        hotkey_vk,
    )
    if not ok:
        # 如果保存的快捷键不可用，退回 Home。
        hotkey_vk_local = VK_HOME
        ok = user32.RegisterHotKey(
            main_hwnd,
            HOTKEY_ID,
            0,
            hotkey_vk_local,
        )
        if ok:
            globals()["hotkey_vk"] = hotkey_vk_local
            globals()["hotkey_mod"] = 0
            save_config()
        else:
            show_error(
                "快捷键注册失败",
                "默认 Home 也无法注册，请检查是否有其它程序占用。",
            )

def keyboard_capture_loop():
    """
    快捷键修改使用一个非常轻量的临时线程，
    但正常运行阶段完全不监听键盘。

    只在用户点击“修改”后启动。
    """
    # 此函数保留接口位置；实际 capture 使用 Windows GetAsyncKeyState
    # + 短轮询，避免低级键盘 Hook。
    pass

def run_capture_watcher():
    global capture_mode
    last = set()

    while capture_mode:
        pressed = set()
        for vk in list(range(1, 256)):
            try:
                if user32.GetAsyncKeyState(vk) & 0x8000:
                    pressed.add(vk)
            except Exception:
                pass

        newly = pressed - last
        if newly:
            # 优先选择非修饰键
            candidates = [
                v for v in newly
                if v not in (0x10, 0x11, 0x12, 0x5B, 0x5C)
            ]
            if candidates:
                vk = candidates[0]
                mods = current_modifiers()
                user32.PostMessageW(
                    main_hwnd,
                    WM_APP_HOTKEY_CAPTURED,
                    vk,
                    mods,
                )
                return

        last = pressed
        ctypes.windll.kernel32.Sleep(15)

def begin_capture():
    global capture_mode
    if capture_mode:
        return
    capture_mode = True
    set_text(hotkey_btn, "请按键…")
    set_text(hotkey_hwnd, "请按下新的快捷键")
    threading.Thread(target=run_capture_watcher, daemon=True).start()

# ---------- 重写窗口过程以接收捕获 ----------
_original_wnd_proc = wnd_proc

def wnd_proc(hwnd, msg, wparam, lparam):
    global main_hwnd, capture_mode, hotkey_vk, hotkey_mod

    if msg == WM_APP_HOTKEY_CAPTURED:
        if capture_mode:
            handle_capture(int(wparam), int(lparam))
        return 0

    if msg == WM_COMMAND:
        cid = wparam & 0xFFFF
        if cid == ID_BTN_TOGGLE:
            toggle_async()
        elif cid == ID_BTN_HOTKEY:
            begin_capture()
        elif cid == ID_BTN_REFRESH:
            refresh_adapters()
        return 0

    if msg == WM_HOTKEY:
        if not capture_mode:
            toggle_async()
        return 0

    if msg == WM_TRAY:
        if lparam in (WM_LBUTTONUP, WM_NCLBUTTONDBLCLK):
            show_main()
        elif lparam == WM_RBUTTONUP:
            tray_menu()
        return 0

    if msg == WM_CLOSE:
        user32.ShowWindow(hwnd, SW_HIDE)
        return 0

    if msg == WM_DESTROY:
        user32.UnregisterHotKey(hwnd, HOTKEY_ID)
        remove_tray()
        cleanup_rules()
        user32.PostQuitMessage(0)
        return 0

    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

def main():
    if os.name != "nt":
        print("此程序仅支持 Windows。")
        return

    if not is_admin():
        ctypes.windll.user32.MessageBoxW(
            None,
            "程序需要管理员权限才能控制 Windows 防火墙。\n"
            "请使用管理员身份运行。",
            APP_NAME,
            0x00000010,
        )
        return

    load_config()
    cleanup_rules()

    create_main_window()
    register_hotkey()
    add_tray()

    # 启动时显示一次；关闭后隐藏到托盘。
    user32.ShowWindow(main_hwnd, SW_SHOWNORMAL)
    user32.UpdateWindow(main_hwnd)

    update_ui()
    refresh_adapters()

    msg = MSG()
    while True:
        result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if result <= 0:
            break
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

if __name__ == "__main__":
    main()
