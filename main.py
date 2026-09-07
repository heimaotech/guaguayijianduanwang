import ctypes
import ctypes.wintypes as wintypes
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

import pystray
from PIL import Image, ImageDraw


# ============================================================
# 基本配置
# ============================================================

APP_NAME = "呱呱一键断网与恢复"
APP_VERSION = "1.0.0"

RULE_PREFIX = "GuaguaNetToggle"

CONFIG_DIR = (
    Path(os.environ.get("APPDATA", str(Path.home())))
    / "GuaguaNetToggle"
)

CONFIG_FILE = CONFIG_DIR / "config.json"

WINDOW_WIDTH = 400
WINDOW_HEIGHT = 600


# ============================================================
# Windows API
# ============================================================

if sys.platform == "win32":

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    # --------------------------------------------------------
    # 常量
    # --------------------------------------------------------

    WH_KEYBOARD_LL = 13

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101

    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105

    WM_QUIT = 0x0012

    PM_REMOVE = 0x0001

    # --------------------------------------------------------
    # ctypes 类型
    # --------------------------------------------------------

    ULONG_PTR = ctypes.c_size_t
    LRESULT = ctypes.c_ssize_t

    # --------------------------------------------------------
    # KBDLLHOOKSTRUCT
    # --------------------------------------------------------

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    # --------------------------------------------------------
    # Windows API 函数声明
    # --------------------------------------------------------

    user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.HINSTANCE,
        wintypes.DWORD,
    ]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK

    user32.CallNextHookEx.argtypes = [
        wintypes.HHOOK,
        ctypes.c_int,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.CallNextHookEx.restype = LRESULT

    user32.UnhookWindowsHookEx.argtypes = [
        wintypes.HHOOK,
    ]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL

    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int

    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL

    user32.GetKeyNameTextW.argtypes = [
        wintypes.LONG,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetKeyNameTextW.restype = ctypes.c_int

    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    kernel32.GetModuleHandleW.argtypes = [
        wintypes.LPCWSTR,
    ]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    shell32.IsUserAnAdmin.argtypes = []
    shell32.IsUserAnAdmin.restype = wintypes.BOOL

else:
    user32 = None
    kernel32 = None
    shell32 = None


# ============================================================
# 全局状态
# ============================================================

offline = False

# 默认 Home
hotkey_vk = 0x24

main_window = None
tray_icon = None

hook_thread = None
hook_handle = None
keyboard_proc_ref = None
hook_thread_id = 0

stop_hook_event = threading.Event()

state_lock = threading.RLock()

toggle_busy = False

capture_active = False
capture_callback = None

capture_lock = threading.RLock()


# ============================================================
# UI 状态变量
# ============================================================

status_var = None
status_detail_var = None
adapter_var = None
admin_var = None
hotkey_var = None


# ============================================================
# Apple / Windows 风格 UI
# ============================================================

BG = "#F5F5F7"
CARD = "#FFFFFF"

TEXT = "#1D1D1F"
SECONDARY = "#6E6E73"

BORDER = "#E5E5EA"

BLUE = "#007AFF"
GREEN = "#34C759"
RED = "#FF3B30"

BUTTON_BG = "#1D1D1F"
BUTTON_ACTIVE = "#3A3A3C"

LIGHT_BUTTON = "#F2F2F7"
LIGHT_BUTTON_ACTIVE = "#E5E5EA"

FONT = "Microsoft YaHei UI"


# ============================================================
# 快捷键名称
# ============================================================

SPECIAL_NAMES = {
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",

    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",

    0x13: "Pause",
    0x14: "Caps Lock",

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

    0x6A: "Num *",
    0x6B: "Num +",
    0x6D: "Num -",
    0x6E: "Num .",
    0x6F: "Num /",

    0x90: "Num Lock",
    0x91: "Scroll Lock",

    0xA0: "Left Shift",
    0xA1: "Right Shift",

    0xA2: "Left Ctrl",
    0xA3: "Right Ctrl",

    0xA4: "Left Alt",
    0xA5: "Right Alt",

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
    0xDF: "OEM8",
}


# ============================================================
# Windows 基础函数
# ============================================================

def is_admin():
    if sys.platform != "win32":
        return False

    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_ps(command):
    """
    执行 PowerShell。
    所有网络相关操作均通过这里执行。
    """

    if sys.platform != "win32":
        raise RuntimeError("此程序仅支持 Windows。")

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
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=20,
    )

    if process.returncode != 0:
        error = process.stderr.strip()

        if not error:
            error = "PowerShell 执行失败。"

        raise RuntimeError(error)

    return process.stdout.strip()


# ============================================================
# 防火墙网络控制
# ============================================================

def cleanup_rules():
    """
    删除本程序创建的防火墙规则。

    注意：
    只删除 GuaguaNetToggle 开头的规则，
    不碰系统其它防火墙规则。
    """

    try:
        command = (
            f"Get-NetFirewallRule "
            f"-DisplayName '{RULE_PREFIX}_*' "
            f"-ErrorAction SilentlyContinue | "
            f"Remove-NetFirewallRule "
            f"-ErrorAction SilentlyContinue"
        )

        run_ps(command)

    except Exception:
        pass


def block_network():
    global offline

    with state_lock:
        if offline:
            return

    command = f"""
$old = Get-NetFirewallRule `
    -DisplayName '{RULE_PREFIX}_*' `
    -ErrorAction SilentlyContinue

if ($old) {{
    $old | Remove-NetFirewallRule `
        -ErrorAction SilentlyContinue
}}

New-NetFirewallRule `
    -DisplayName '{RULE_PREFIX}_Block_Outbound' `
    -Direction Outbound `
    -Action Block `
    -Profile Any `
    -Protocol Any `
    -ErrorAction Stop | Out-Null

New-NetFirewallRule `
    -DisplayName '{RULE_PREFIX}_Block_Inbound' `
    -Direction Inbound `
    -Action Block `
    -Profile Any `
    -Protocol Any `
    -ErrorAction Stop | Out-Null
"""

    run_ps(command)

    with state_lock:
        offline = True

    refresh_ui()


def unblock_network():
    global offline

    command = (
        f"Get-NetFirewallRule "
        f"-DisplayName '{RULE_PREFIX}_*' "
        f"-ErrorAction SilentlyContinue | "
        f"Remove-NetFirewallRule "
        f"-ErrorAction SilentlyContinue"
    )

    run_ps(command)

    with state_lock:
        offline = False

    refresh_ui()


def toggle_network():
    global toggle_busy

    with state_lock:

        if toggle_busy:
            return

        toggle_busy = True
        current_offline = offline

    try:

        if current_offline:
            unblock_network()
        else:
            block_network()

    except Exception as error:

        if main_window:

            try:
                main_window.after(
                    0,
                    lambda e=str(error): show_error(
                        "切换网络失败",
                        e,
                    ),
                )
            except Exception:
                pass

    finally:

        with state_lock:
            toggle_busy = False

        refresh_ui()


def toggle_from_ui():
    """
    UI / 托盘调用网络切换。
    网络操作放到后台线程，避免卡住界面。
    """

    thread = threading.Thread(
        target=toggle_network,
        daemon=True,
    )

    thread.start()


# ============================================================
# 网络适配器
# ============================================================

def get_adapters():

    command = (
        "Get-NetAdapter -Physical | "
        "Select-Object Name, Status | "
        "ConvertTo-Json -Compress"
    )

    output = run_ps(command)

    if not output:
        return []

    data = json.loads(output)

    if isinstance(data, list):
        return data

    return [data]


def adapter_text():

    try:

        adapters = get_adapters()

        if not adapters:
            return "未检测到物理网络适配器"

        lines = []

        for adapter in adapters:

            name = str(
                adapter.get(
                    "Name",
                    "未知适配器",
                )
            )

            status = str(
                adapter.get(
                    "Status",
                    "Unknown",
                )
            )

            if status.lower() == "up":
                mark = "●"
                state = "已连接"
            else:
                mark = "○"
                state = "未连接"

            lines.append(
                f"{mark}  {name}    {state}"
            )

        return "\n".join(lines)

    except Exception as error:

        return f"读取适配器失败：{error}"


# ============================================================
# 配置
# ============================================================

def load_config():

    global hotkey_vk

    try:

        data = json.loads(
            CONFIG_FILE.read_text(
                encoding="utf-8"
            )
        )

        value = int(
            data.get(
                "hotkey_vk",
                0x24,
            )
        )

        if 1 <= value <= 255:
            hotkey_vk = value
        else:
            hotkey_vk = 0x24

    except Exception:

        hotkey_vk = 0x24


def save_config():

    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = CONFIG_FILE.with_suffix(
        ".tmp"
    )

    content = {
        "hotkey_vk": int(hotkey_vk)
    }

    temp_file.write_text(
        json.dumps(
            content,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_file.replace(CONFIG_FILE)


# ============================================================
# 快捷键名称
# ============================================================

def key_name(vk):

    vk = int(vk)

    if vk in SPECIAL_NAMES:
        return SPECIAL_NAMES[vk]

    # 数字
    if 0x30 <= vk <= 0x39:
        return chr(vk)

    # A-Z
    if 0x41 <= vk <= 0x5A:
        return chr(vk)

    # 小键盘数字
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"

    # F1-F24
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"

    return f"VK {vk}"


# ============================================================
# 全局键盘 Hook
# ============================================================

def keyboard_callback(
    n_code,
    w_param,
    l_param,
):
    """
    Windows Low-Level Keyboard Hook 回调。

    这里只负责：
    1. 获取 VK Code
    2. 判断当前是否正在设置快捷键
    3. 判断是否命中当前快捷键

    实际网络操作放到独立线程。
    """

    global capture_callback

    try:

        if (
            n_code >= 0
            and w_param in (
                WM_KEYDOWN,
                WM_SYSKEYDOWN,
            )
        ):

            data = ctypes.cast(
                l_param,
                ctypes.POINTER(
                    KBDLLHOOKSTRUCT
                ),
            ).contents

            vk = int(data.vkCode)

            # ------------------------------------------------
            # 快捷键设置模式
            # ------------------------------------------------

            with capture_lock:

                callback = (
                    capture_callback
                    if capture_active
                    else None
                )

            if callback is not None:

                try:
                    callback(vk)
                except Exception:
                    pass

            # ------------------------------------------------
            # 正常快捷键模式
            # ------------------------------------------------

            else:

                with state_lock:
                    target = hotkey_vk

                if (
                    vk == target
                    and not capture_active
                ):

                    threading.Thread(
                        target=toggle_network,
                        daemon=True,
                    ).start()

    except Exception:
        pass

    return user32.CallNextHookEx(
        hook_handle,
        n_code,
        w_param,
        l_param,
    )


def keyboard_hook_loop():

    global hook_handle
    global keyboard_proc_ref
    global hook_thread_id

    hook_thread_id = (
        kernel32.GetCurrentThreadId()
    )

    # 必须保持 Python 回调对象引用，
    # 否则 Windows 仍然持有函数地址，
    # Python 对象却可能被垃圾回收。
    keyboard_proc_ref = (
        LowLevelKeyboardProc(
            keyboard_callback
        )
    )

    # 对 WH_KEYBOARD_LL：
    # 线程 ID = 0，使用当前进程模块句柄。
    module_handle = (
        kernel32.GetModuleHandleW(None)
    )

    hook_handle = user32.SetWindowsHookExW(
        WH_KEYBOARD_LL,
        ctypes.cast(
            keyboard_proc_ref,
            ctypes.c_void_p,
        ),
        module_handle,
        0,
    )

    if not hook_handle:

        hook_thread_id = 0
        keyboard_proc_ref = None

        return

    # --------------------------------------------------------
    # 强制创建消息队列
    # --------------------------------------------------------

    msg = wintypes.MSG()

    # PeekMessage 会确保这个线程拥有消息队列。
    user32.PeekMessageW(
        ctypes.byref(msg),
        None,
        0,
        0,
        PM_REMOVE,
    )

    # --------------------------------------------------------
    # 消息循环
    # --------------------------------------------------------

    while not stop_hook_event.is_set():

        result = user32.GetMessageW(
            ctypes.byref(msg),
            None,
            0,
            0,
        )

        if result <= 0:
            break

    # --------------------------------------------------------
    # 卸载 Hook
    # --------------------------------------------------------

    if hook_handle:

        try:
            user32.UnhookWindowsHookEx(
                hook_handle
            )
        except Exception:
            pass

    hook_handle = None
    hook_thread_id = 0
    keyboard_proc_ref = None


def start_keyboard_hook():

    global hook_thread

    stop_hook_event.clear()

    hook_thread = threading.Thread(
        target=keyboard_hook_loop,
        name="GuaguaKeyboardHook",
        daemon=True,
    )

    hook_thread.start()

    # 给 Hook 线程一点时间完成初始化
    # 不阻塞主 UI。
    for _ in range(20):

        if hook_handle:
            break

        if (
            hook_thread
            and not hook_thread.is_alive()
        ):
            break

        stop_hook_event.wait(0.01)


def stop_keyboard_hook():

    stop_hook_event.set()

    thread_id = hook_thread_id

    if thread_id:

        try:

            user32.PostThreadMessageW(
                thread_id,
                WM_QUIT,
                0,
                0,
            )

        except Exception:
            pass


# ============================================================
# 快捷键捕获
# ============================================================

def set_capture_callback(callback):

    global capture_callback
    global capture_active

    with capture_lock:

        capture_callback = callback
        capture_active = (
            callback is not None
        )


def capture_key():

    if not main_window:
        return

    window = tk.Toplevel(
        main_window
    )

    window.title("设置快捷键")

    window.geometry(
        "360x210"
    )

    window.resizable(
        False,
        False,
    )

    window.configure(
        bg=BG
    )

    window.transient(
        main_window
    )

    window.grab_set()

    # --------------------------------------------------------
    # 标题
    # --------------------------------------------------------

    tk.Label(
        window,
        text="设置快捷键",
        bg=BG,
        fg=TEXT,
        font=(
            FONT,
            16,
            "bold",
        ),
    ).pack(
        pady=(25, 6)
    )

    value = tk.StringVar(
        value="请按下任意键"
    )

    tk.Label(
        window,
        textvariable=value,
        bg=BG,
        fg=BLUE,
        font=(
            FONT,
            14,
            "bold",
        ),
    ).pack(
        pady=4
    )

    tk.Label(
        window,
        text="支持普通键、功能键、方向键、数字键等",
        bg=BG,
        fg=SECONDARY,
        font=(
            FONT,
            9,
        ),
    ).pack(
        pady=(4, 0)
    )

    tk.Label(
        window,
        text="按 Esc 取消",
        bg=BG,
        fg=SECONDARY,
        font=(
            FONT,
            9,
        ),
    ).pack(
        pady=(8, 0)
    )

    finished = {
        "value": False
    }

    def finish():

        if finished["value"]:
            return

        finished["value"] = True

        set_capture_callback(
            None
        )

        try:
            window.grab_release()
        except Exception:
            pass

        try:
            window.destroy()
        except Exception:
            pass

    def on_vk(vk):

        if finished["value"]:
            return

        vk = int(vk)

        # Esc = 取消
        if vk == 0x1B:

            finish()
            return

        display_name = key_name(vk)

        value.set(
            display_name
        )

        global hotkey_vk

        with state_lock:
            old_vk = hotkey_vk
            hotkey_vk = vk

        try:

            save_config()

            if hotkey_var:

                hotkey_var.set(
                    display_name
                )

            # 先解除捕获模式
            set_capture_callback(
                None
            )

            # 延迟关闭窗口，
            # 避免本次按键继续影响 UI。
            window.after(
                150,
                finish,
            )

        except Exception as error:

            with state_lock:
                hotkey_vk = old_vk

            set_capture_callback(
                None
            )

            show_error(
                "保存失败",
                f"无法保存快捷键：\n{error}",
            )

            finish()

    set_capture_callback(
        on_vk
    )

    window.protocol(
        "WM_DELETE_WINDOW",
        finish,
    )

    window.focus_force()


# ============================================================
# UI 辅助
# ============================================================

def rounded_card(
    parent,
    height=None,
):

    frame = tk.Frame(
        parent,
        bg=CARD,
        highlightthickness=1,
        highlightbackground=BORDER,
    )

    if height is not None:

        frame.configure(
            height=height
        )

        frame.pack_propagate(
            False
        )

    return frame


def show_error(
    title,
    detail,
):

    if (
        main_window
        and main_window.winfo_exists()
    ):

        try:

            messagebox.showerror(
                title,
                detail,
                parent=main_window,
            )

        except Exception:
            pass


def refresh_ui():

    def update():

        if (
            not main_window
            or not main_window.winfo_exists()
        ):
            return

        with state_lock:

            current_offline = offline
            current_hotkey = hotkey_vk
            busy = toggle_busy

        # 状态
        if status_var:

            status_var.set(
                "已断网"
                if current_offline
                else "网络正常"
            )

        if status_detail_var:

            if busy:

                status_detail_var.set(
                    "正在切换网络状态…"
                )

            elif current_offline:

                status_detail_var.set(
                    "所有网络流量已被临时阻断"
                )

            else:

                status_detail_var.set(
                    "网络连接正常，可正常访问互联网"
                )

        # 快捷键
        if hotkey_var:

            hotkey_var.set(
                key_name(
                    current_hotkey
                )
            )

        # 管理员
        if admin_var:

            admin_var.set(
                "已获得管理员权限"
                if is_admin()
                else "未获得管理员权限"
            )

        # 托盘标题
        if tray_icon:

            try:

                tray_icon.title = (
                    f"{APP_NAME} · "
                    f"{'已断网' if current_offline else '网络正常'}"
                )

            except Exception:
                pass

    if main_window:

        try:

            main_window.after(
                0,
                update,
            )

        except Exception:
            pass


def refresh_adapters_async():

    def worker():

        text = adapter_text()

        if main_window:

            try:

                main_window.after(
                    0,
                    lambda t=text: (
                        adapter_var.set(t)
                        if adapter_var
                        else None
                    ),
                )

            except Exception:
                pass

    threading.Thread(
        target=worker,
        daemon=True,
    ).start()


# ============================================================
# 托盘
# ============================================================

def make_icon():

    image = Image.new(
        "RGBA",
        (64, 64),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        image
    )

    # 黑色圆角方块
    draw.rounded_rectangle(
        (5, 5, 59, 59),
        radius=15,
        fill=(29, 29, 31, 255),
    )

    # 白色网络切换符号
    draw.line(
        (20, 32, 44, 32),
        fill=(255, 255, 255, 255),
        width=5,
    )

    draw.line(
        (32, 20, 32, 44),
        fill=(255, 255, 255, 255),
        width=5,
    )

    return image


def show_window():

    if (
        main_window
        and main_window.winfo_exists()
    ):

        main_window.deiconify()
        main_window.lift()
        main_window.focus_force()

        refresh_ui()
        refresh_adapters_async()


def hide_window():

    if (
        main_window
        and main_window.winfo_exists()
    ):

        main_window.withdraw()


def quit_app(
    icon_obj=None,
    item=None,
):

    global capture_callback
    global capture_active

    with capture_lock:

        capture_callback = None
        capture_active = False

    stop_keyboard_hook()

    cleanup_rules()

    if icon_obj:

        try:
            icon_obj.stop()
        except Exception:
            pass

    if main_window:

        try:

            main_window.after(
                0,
                main_window.destroy,
            )

        except Exception:
            pass


def tray_thread():

    global tray_icon

    menu = pystray.Menu(

        pystray.MenuItem(
            "打开主界面",
            lambda icon, item:
                show_window(),
        ),

        pystray.MenuItem(
            "切换网络",
            lambda icon, item:
                toggle_from_ui(),
        ),

        pystray.Menu.SEPARATOR,

        pystray.MenuItem(
            "退出程序",
            lambda icon, item:
                quit_app(icon),
        ),
    )

    tray_icon = pystray.Icon(
        APP_NAME,
        make_icon(),
        APP_NAME,
        menu,
    )

    tray_icon.run()


# ============================================================
# 主界面
# ============================================================

def create_window():

    global main_window

    global status_var
    global status_detail_var
    global adapter_var
    global admin_var
    global hotkey_var

    main_window = tk.Tk()

    # --------------------------------------------------------
    # 400 × 600
    # --------------------------------------------------------

    main_window.title(
        APP_NAME
    )

    main_window.geometry(
        f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}"
    )

    main_window.resizable(
        False,
        False,
    )

    main_window.configure(
        bg=BG
    )

    # Windows 高 DPI 下保持较稳定的视觉比例
    try:

        main_window.tk.call(
            "tk",
            "scaling",
            1.0,
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # 主容器
    # --------------------------------------------------------

    root = tk.Frame(
        main_window,
        bg=BG,
    )

    root.pack(
        fill="both",
        expand=True,
        padx=22,
        pady=20,
    )

    # --------------------------------------------------------
    # 标题
    # --------------------------------------------------------

    tk.Label(
        root,
        text="呱呱一键断网与恢复",
        bg=BG,
        fg=TEXT,
        font=(
            FONT,
            18,
            "bold",
        ),
    ).pack(
        anchor="w"
    )

    tk.Label(
        root,
        text="快速切换系统网络状态",
        bg=BG,
        fg=SECONDARY,
        font=(
            FONT,
            9,
        ),
    ).pack(
        anchor="w",
        pady=(2, 15),
    )

    # ========================================================
    # 当前状态
    # ========================================================

    status_card = rounded_card(
        root,
        128,
    )

    status_card.pack(
        fill="x"
    )

    status_var = tk.StringVar(
        value="网络正常"
    )

    status_detail_var = tk.StringVar(
        value="网络连接正常，可正常访问互联网"
    )

    tk.Label(
        status_card,
        text="当前状态",
        bg=CARD,
        fg=SECONDARY,
        font=(
            FONT,
            9,
        ),
    ).pack(
        anchor="w",
        padx=18,
        pady=(15, 0),
    )

    tk.Label(
        status_card,
        textvariable=status_var,
        bg=CARD,
        fg=TEXT,
        font=(
            FONT,
            21,
            "bold",
        ),
    ).pack(
        anchor="w",
        padx=18,
        pady=(0, 0),
    )

    tk.Label(
        status_card,
        textvariable=status_detail_var,
        bg=CARD,
        fg=SECONDARY,
        font=(
            FONT,
            8,
        ),
    ).pack(
        anchor="w",
        padx=18,
        pady=(0, 0),
    )

    tk.Button(
        status_card,
        text="立即切换",
        command=toggle_from_ui,
        bg=BUTTON_BG,
        fg="white",
        activebackground=BUTTON_ACTIVE,
        activeforeground="white",
        relief="flat",
        bd=0,
        font=(
            FONT,
            9,
            "bold",
        ),
        cursor="hand2",
        padx=14,
        pady=6,
    ).place(
        relx=1.0,
        x=-17,
        y=17,
        anchor="ne",
    )

    # ========================================================
    # 信息卡
    # ========================================================

    info_card = rounded_card(
        root
    )

    info_card.pack(
        fill="x",
        pady=(12, 0),
    )

    # --------------------------------------------------------
    # 管理员权限
    # --------------------------------------------------------

    tk.Label(
        info_card,
        text="权限",
        bg=CARD,
        fg=SECONDARY,
        font=(
            FONT,
            8,
        ),
    ).pack(
        anchor="w",
        padx=16,
        pady=(11, 0),
    )

    admin_var = tk.StringVar(
        value="检测中…"
    )

    tk.Label(
        info_card,
        textvariable=admin_var,
        bg=CARD,
        fg=TEXT,
        font=(
            FONT,
            9,
            "bold",
        ),
    ).pack(
        anchor="w",
        padx=16,
        pady=(1, 9),
    )

    # --------------------------------------------------------
    # 快捷键
    # --------------------------------------------------------

    hotkey_row = tk.Frame(
        info_card,
        bg=CARD,
    )

    hotkey_row.pack(
        fill="x",
        padx=16,
        pady=(0, 11),
    )

    tk.Label(
        hotkey_row,
        text="快捷键",
        bg=CARD,
        fg=SECONDARY,
        font=(
            FONT,
            8,
        ),
    ).pack(
        side="left"
    )

    hotkey_var = tk.StringVar(
        value=key_name(
            hotkey_vk
        )
    )

    tk.Label(
        hotkey_row,
        textvariable=hotkey_var,
        bg=CARD,
        fg=TEXT,
        font=(
            FONT,
            9,
            "bold",
        ),
    ).pack(
        side="left",
        padx=(24, 0),
    )

    tk.Button(
        hotkey_row,
        text="修改",
        command=capture_key,
        bg=LIGHT_BUTTON,
        fg=TEXT,
        activebackground=LIGHT_BUTTON_ACTIVE,
        activeforeground=TEXT,
        relief="flat",
        bd=0,
        font=(
            FONT,
            8,
        ),
        cursor="hand2",
        padx=11,
        pady=4,
    ).pack(
        side="right"
    )

    # ========================================================
    # 网络适配器
    # ========================================================

    adapter_card = rounded_card(
        root,
        125,
    )

    adapter_card.pack(
        fill="x",
        pady=(12, 0),
    )

    tk.Label(
        adapter_card,
        text="物理网络适配器",
        bg=CARD,
        fg=SECONDARY,
        font=(
            FONT,
            8,
        ),
    ).pack(
        anchor="w",
        padx=16,
        pady=(11, 3),
    )

    adapter_var = tk.StringVar(
        value="读取中…"
    )

    tk.Label(
        adapter_card,
        textvariable=adapter_var,
        justify="left",
        anchor="nw",
        bg=CARD,
        fg=TEXT,
        font=(
            FONT,
            8,
        ),
    ).pack(
        fill="both",
        expand=True,
        padx=16,
        pady=(0, 8),
    )

    # ========================================================
    # 底部说明
    # ========================================================

    foot = tk.Frame(
        root,
        bg=BG,
    )

    foot.pack(
        fill="x",
        pady=(12, 0),
    )

    tk.Label(
        foot,
        text=(
            "断网采用 Windows 防火墙临时规则。\n"
            "不关闭 Wi-Fi / Ethernet 网卡，不修改 IP、DNS 或路由。"
        ),
        justify="left",
        bg=BG,
        fg=SECONDARY,
        font=(
            FONT,
            7,
        ),
    ).pack(
        side="left"
    )

    tk.Button(
        foot,
        text="刷新",
        command=refresh_adapters_async,
        bg=BG,
        fg=BLUE,
        activebackground=BG,
        activeforeground=BLUE,
        relief="flat",
        bd=0,
        font=(
            FONT,
            8,
        ),
        cursor="hand2",
    ).pack(
        side="right",
        anchor="s",
    )

    # --------------------------------------------------------
    # 关闭窗口 = 隐藏到托盘
    # --------------------------------------------------------

    main_window.protocol(
        "WM_DELETE_WINDOW",
        hide_window,
    )

    refresh_ui()
    refresh_adapters_async()


# ============================================================
# 主程序
# ============================================================

def main():

    if sys.platform != "win32":

        print(
            "此程序仅支持 Windows。"
        )

        return

    # --------------------------------------------------------
    # 管理员权限
    # --------------------------------------------------------

    if not is_admin():

        root = tk.Tk()

        root.withdraw()

        messagebox.showerror(
            APP_NAME,
            (
                "程序未获得管理员权限。\n\n"
                "请使用管理员身份运行。"
            ),
        )

        root.destroy()

        return

    # --------------------------------------------------------
    # 配置
    # --------------------------------------------------------

    load_config()

    # --------------------------------------------------------
    # 清理历史防火墙规则
    # --------------------------------------------------------

    cleanup_rules()

    # --------------------------------------------------------
    # 创建 UI
    # --------------------------------------------------------

    create_window()

    # --------------------------------------------------------
    # 启动全局键盘 Hook
    # --------------------------------------------------------

    start_keyboard_hook()

    # --------------------------------------------------------
    # 启动托盘
    # --------------------------------------------------------

    threading.Thread(
        target=tray_thread,
        name="GuaguaTray",
        daemon=True,
    ).start()

    # --------------------------------------------------------
    # 主 UI
    # --------------------------------------------------------

    main_window.mainloop()

    # --------------------------------------------------------
    # UI 退出后的清理
    # --------------------------------------------------------

    stop_keyboard_hook()

    cleanup_rules()


if __name__ == "__main__":
    main()
