import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

APP_NAME = "呱呱一键断网与恢复"
RULE_PREFIX = "GuaguaNetToggle"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GuaguaNetToggle"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Windows virtual-key codes used for display/defaults.
VK = {
    "HOME": 0x24,
    "ESC": 0x1B,
    "SPACE": 0x20,
}

SPECIAL_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x10: "Shift",
    0x11: "Ctrl", 0x12: "Alt", 0x13: "Pause", 0x14: "Caps Lock",
    0x1B: "Esc", 0x20: "Space", 0x21: "Page Up", 0x22: "Page Down",
    0x23: "End", 0x24: "Home", 0x25: "Left", 0x26: "Up",
    0x27: "Right", 0x28: "Down", 0x2D: "Insert", 0x2E: "Delete",
    0x5B: "Left Win", 0x5C: "Right Win", 0x5D: "Menu",
    0x90: "Num Lock", 0x91: "Scroll Lock",
    0xA0: "Left Shift", 0xA1: "Right Shift", 0xA2: "Left Ctrl", 0xA3: "Right Ctrl",
    0xA4: "Left Alt", 0xA5: "Right Alt",
    0xAD: "Volume Mute", 0xAE: "Volume Down", 0xAF: "Volume Up",
    0xB0: "Media Next", 0xB1: "Media Previous", 0xB2: "Media Stop", 0xB3: "Media Play/Pause",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'", 0xDF: "OEM8",
}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

offline = False
hotkey_vk = VK["HOME"]

main_window = None
tray_icon = None
hook_thread = None
hook_handle = None
keyboard_proc_ref = None
hook_thread_id = 0
stop_hook_event = threading.Event()
state_lock = threading.Lock()
toggle_busy = False
capture_active = False
capture_callback = None

status_var = None
status_detail_var = None
adapter_var = None
admin_var = None
hotkey_var = None

BG = "#F5F5F7"
CARD = "#FFFFFF"
TEXT = "#1D1D1F"
SECONDARY = "#6E6E73"
BORDER = "#E5E5EA"
GREEN = "#34C759"
RED = "#FF3B30"
BLUE = "#007AFF"

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
WM_USER = 0x0400

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, WPARAM, LPARAM
)


# -------------------- Windows helpers --------------------

def is_admin():
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_ps(command):
    process = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-Command", command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=20,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "PowerShell 执行失败")
    return process.stdout.strip()


def cleanup_rules():
    try:
        run_ps(
            f"Get-NetFirewallRule -DisplayName '{RULE_PREFIX}_*' "
            f"-ErrorAction SilentlyContinue | "
            f"Remove-NetFirewallRule -ErrorAction SilentlyContinue"
        )
    except Exception:
        pass


def block_network():
    global offline
    with state_lock:
        if offline:
            return

    command = f"""
$old = Get-NetFirewallRule -DisplayName '{RULE_PREFIX}_*' -ErrorAction SilentlyContinue
if ($old) {{ $old | Remove-NetFirewallRule -ErrorAction SilentlyContinue }}
New-NetFirewallRule -DisplayName '{RULE_PREFIX}_Block_Outbound' -Direction Outbound -Action Block -Profile Any -Protocol Any -ErrorAction Stop | Out-Null
New-NetFirewallRule -DisplayName '{RULE_PREFIX}_Block_Inbound' -Direction Inbound -Action Block -Profile Any -Protocol Any -ErrorAction Stop | Out-Null
"""
    run_ps(command)
    with state_lock:
        offline = True
    refresh_ui()


def unblock_network():
    global offline
    command = (
        f"Get-NetFirewallRule -DisplayName '{RULE_PREFIX}_*' "
        f"-ErrorAction SilentlyContinue | "
        f"Remove-NetFirewallRule -ErrorAction SilentlyContinue"
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
            main_window.after(0, lambda e=str(error): show_error("切换网络失败", e))
    finally:
        with state_lock:
            toggle_busy = False
        refresh_ui()


def show_error(title, detail):
    if main_window and main_window.winfo_exists():
        messagebox = __import__("tkinter.messagebox", fromlist=["messagebox"])
        messagebox.showerror(title, detail, parent=main_window)


def get_adapters():
    command = (
        "Get-NetAdapter -Physical | "
        "Select-Object Name, Status | ConvertTo-Json -Compress"
    )
    output = run_ps(command)
    if not output:
        return []
    data = json.loads(output)
    return data if isinstance(data, list) else [data]


def adapter_text():
    try:
        adapters = get_adapters()
        if not adapters:
            return "未检测到物理网络适配器"
        lines = []
        for adapter in adapters:
            name = str(adapter.get("Name", "未知适配器"))
            status = str(adapter.get("Status", "Unknown"))
            mark = "●" if status.lower() == "up" else "○"
            lines.append(f"{mark}  {name}    {status}")
        return "\n".join(lines)
    except Exception as error:
        return f"读取适配器失败：{error}"


# -------------------- Config --------------------

def load_config():
    global hotkey_vk
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        value = int(data.get("hotkey_vk", VK["HOME"]))
        hotkey_vk = value if 1 <= value <= 255 else VK["HOME"]
    except Exception:
        hotkey_vk = VK["HOME"]


def save_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps({"hotkey_vk": hotkey_vk}, indent=2), encoding="utf-8")
    temp.replace(CONFIG_FILE)


def key_name(vk):
    if vk in SPECIAL_NAMES:
        return SPECIAL_NAMES[vk]
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return f"VK {vk}"


# -------------------- Global keyboard hook --------------------

def keyboard_callback(n_code, w_param, l_param):
    global capture_callback

    if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
        try:
            data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = int(data.vkCode)
            callback = capture_callback if capture_active else None
            if callback is not None:
                callback(vk)
            else:
                with state_lock:
                    target = hotkey_vk
                if vk == target:
                    threading.Thread(target=toggle_network, daemon=True).start()
        except Exception:
            pass

    return user32.CallNextHookEx(hook_handle, n_code, w_param, l_param)


def keyboard_hook_loop():
    global hook_handle, keyboard_proc_ref, hook_thread_id
    hook_thread_id = kernel32.GetCurrentThreadId()
    keyboard_proc_ref = LowLevelKeyboardProc(keyboard_callback)
    hook_handle = user32.SetWindowsHookExW(
        WH_KEYBOARD_LL, keyboard_proc_ref, kernel32.GetModuleHandleW(None), 0
    )
    if not hook_handle:
        hook_thread_id = 0
        return

    msg = wt.MSG()
    while not stop_hook_event.is_set():
        result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if result <= 0:
            break

    if hook_handle:
        user32.UnhookWindowsHookEx(hook_handle)
    hook_handle = None
    hook_thread_id = 0


def start_keyboard_hook():
    global hook_thread
    stop_hook_event.clear()
    hook_thread = threading.Thread(target=keyboard_hook_loop, daemon=True)
    hook_thread.start()


def stop_keyboard_hook():
    stop_hook_event.set()
    thread_id = hook_thread_id
    if thread_id:
        try:
            user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        except Exception:
            pass


# -------------------- UI --------------------

def rounded_card(parent, height=None):
    frame = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
    if height:
        frame.configure(height=height)
        frame.pack_propagate(False)
    return frame


def refresh_ui():
    def update_status():
        if not main_window or not main_window.winfo_exists():
            return
        with state_lock:
            current_offline = offline
            current_hotkey = hotkey_vk
            busy = toggle_busy
        if status_var:
            status_var.set("已断网" if current_offline else "网络正常")
        if status_detail_var:
            status_detail_var.set(
                "所有网络流量已被临时阻断" if current_offline else "网络连接正常，可正常访问互联网"
            )
        if hotkey_var:
            hotkey_var.set(key_name(current_hotkey))
        if admin_var:
            admin_var.set("已获得管理员权限" if is_admin() else "未获得管理员权限")
        if tray_icon:
            tray_icon.title = f"{APP_NAME} · {'已断网' if current_offline else '网络正常'}"
        if busy and status_detail_var:
            status_detail_var.set("正在切换网络状态…")

    if main_window:
        try:
            main_window.after(0, update_status)
        except Exception:
            pass


def refresh_adapters_async():
    def worker():
        text = adapter_text()
        if main_window:
            try:
                main_window.after(0, lambda t=text: adapter_var.set(t) if adapter_var else None)
            except Exception:
                pass
    threading.Thread(target=worker, daemon=True).start()


def set_capture_callback(callback):
    global capture_callback, capture_active
    capture_callback = callback
    capture_active = callback is not None


def capture_key():
    global capture_active
    window = tk.Toplevel(main_window)
    window.title("设置快捷键")
    window.geometry("340x190")
    window.resizable(False, False)
    window.configure(bg=BG)
    window.transient(main_window)
    window.grab_set()

    tk.Label(window, text="设置快捷键", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(pady=(25, 5))
    value = tk.StringVar(value="请按下任意键")
    tk.Label(window, textvariable=value, bg=BG, fg=BLUE, font=("Segoe UI", 13, "bold")).pack(pady=6)
    tk.Label(window, text="支持普通键、功能键、方向键、数字键等", bg=BG, fg=SECONDARY, font=("Segoe UI", 9)).pack()
    tk.Label(window, text="Esc 取消", bg=BG, fg=SECONDARY, font=("Segoe UI", 9)).pack(pady=(8, 0))

    done = {"value": False}

    def finish():
        if not done["value"]:
            done["value"] = True
            set_capture_callback(None)
            try:
                window.grab_release()
            except Exception:
                pass
            window.destroy()

    def on_vk(vk):
        if done["value"]:
            return
        if vk == 0x1B:
            finish()
            return
        value.set(key_name(vk))
        global hotkey_vk
        try:
            old = hotkey_vk
            hotkey_vk = vk
            save_config()
            if hotkey_var:
                hotkey_var.set(key_name(vk))
            done["value"] = True
            set_capture_callback(None)
            window.after(120, lambda: finish())
        except Exception as error:
            hotkey_vk = old
            set_capture_callback(None)
            show_error("保存失败", f"无法保存快捷键：\n{error}")
            finish()

    set_capture_callback(on_vk)
    window.protocol("WM_DELETE_WINDOW", finish)
    window.focus_force()


def toggle_from_ui():
    threading.Thread(target=toggle_network, daemon=True).start()


def show_window():
    if main_window and main_window.winfo_exists():
        main_window.deiconify()
        main_window.lift()
        main_window.focus_force()
        refresh_ui()
        refresh_adapters_async()


def hide_window():
    if main_window and main_window.winfo_exists():
        main_window.withdraw()


def quit_app(icon_obj=None, item=None):
    global capture_callback, capture_active
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
            main_window.after(0, main_window.destroy)
        except Exception:
            pass


def make_icon():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5, 5, 59, 59), radius=15, fill=(29, 29, 31, 255))
    draw.line((20, 32, 44, 32), fill=(255, 255, 255, 255), width=5)
    draw.line((32, 20, 32, 44), fill=(255, 255, 255, 255), width=5)
    return image


def tray_thread():
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem("打开主界面", lambda icon, item: show_window()),
        pystray.MenuItem("切换网络", lambda icon, item: toggle_from_ui()),
        pystray.MenuItem("退出程序", lambda icon, item: quit_app(icon)),
    )
    tray_icon = pystray.Icon(APP_NAME, make_icon(), APP_NAME, menu)
    tray_icon.run()


def create_window():
    global main_window, status_var, status_detail_var, adapter_var, admin_var, hotkey_var

    main_window = tk.Tk()
    main_window.title(APP_NAME)
    main_window.geometry("400x600")
    main_window.minsize(400, 600)
    main_window.maxsize(400, 600)
    main_window.configure(bg=BG)

    # Windows 高 DPI 下保持清晰且尺寸稳定。
    try:
        main_window.tk.call("tk", "scaling", 1.0)
    except Exception:
        pass

    root = tk.Frame(main_window, bg=BG)
    root.pack(fill="both", expand=True, padx=22, pady=20)

    tk.Label(root, text="呱呱一键断网与恢复", bg=BG, fg=TEXT, font=("Segoe UI", 19, "bold")).pack(anchor="w")
    tk.Label(root, text="快速切换系统网络状态", bg=BG, fg=SECONDARY, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 16))

    status_card = rounded_card(root, 128)
    status_card.pack(fill="x")
    status_var = tk.StringVar()
    status_detail_var = tk.StringVar()
    tk.Label(status_card, text="当前状态", bg=CARD, fg=SECONDARY, font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(16, 1))
    tk.Label(status_card, textvariable=status_var, bg=CARD, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=18)
    tk.Label(status_card, textvariable=status_detail_var, bg=CARD, fg=SECONDARY, font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(1, 0))

    button = tk.Button(
        status_card, text="立即切换", command=toggle_from_ui,
        bg=TEXT, fg="white", activebackground="#3A3A3C", activeforeground="white",
        relief="flat", bd=0, font=("Segoe UI", 10, "bold"), cursor="hand2", padx=16, pady=7,
    )
    button.place(relx=1.0, x=-18, y=17, anchor="ne")

    info_card = rounded_card(root)
    info_card.pack(fill="x", pady=(12, 0))

    admin_var = tk.StringVar()
    tk.Label(info_card, text="权限", bg=CARD, fg=SECONDARY, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(12, 0))
    tk.Label(info_card, textvariable=admin_var, bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(1, 10))

    hotkey_row = tk.Frame(info_card, bg=CARD)
    hotkey_row.pack(fill="x", padx=16, pady=(0, 12))
    tk.Label(hotkey_row, text="快捷键", bg=CARD, fg=SECONDARY, font=("Segoe UI", 9)).pack(side="left")
    hotkey_var = tk.StringVar()
    tk.Label(hotkey_row, textvariable=hotkey_var, bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(24, 0))
    tk.Button(
        hotkey_row, text="修改", command=capture_key,
        bg="#F2F2F7", fg=TEXT, activebackground="#E5E5EA", relief="flat", bd=0,
        font=("Segoe UI", 9), cursor="hand2", padx=12, pady=5,
    ).pack(side="right")

    adapter_card = rounded_card(root, 125)
    adapter_card.pack(fill="x", pady=(12, 0))
    tk.Label(adapter_card, text="物理网络适配器", bg=CARD, fg=SECONDARY, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(12, 4))
    adapter_var = tk.StringVar(value="读取中…")
    tk.Label(adapter_card, textvariable=adapter_var, justify="left", anchor="nw", bg=CARD, fg=TEXT, font=("Segoe UI", 9)).pack(fill="both", expand=True, padx=16, pady=(0, 10))

    foot = tk.Frame(root, bg=BG)
    foot.pack(fill="x", pady=(13, 0))
    tk.Label(
        foot,
        text="断网采用 Windows 防火墙临时规则。\n不关闭 Wi-Fi / Ethernet 网卡，不修改 IP、DNS 或路由。",
        justify="left", bg=BG, fg=SECONDARY, font=("Segoe UI", 8),
    ).pack(side="left")
    tk.Button(
        foot, text="刷新", command=refresh_adapters_async,
        bg=BG, fg=BLUE, activebackground=BG, activeforeground=BLUE,
        relief="flat", bd=0, font=("Segoe UI", 9), cursor="hand2",
    ).pack(side="right", anchor="s")

    # 关闭窗口只隐藏，不结束常驻程序。
    main_window.protocol("WM_DELETE_WINDOW", hide_window)

    refresh_ui()
    refresh_adapters_async()


def main():
    if sys.platform != "win32":
        print("此程序仅支持 Windows。")
        return

    if not is_admin():
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox
        messagebox.showerror(APP_NAME, "程序未获得管理员权限。\n请使用管理员身份运行。")
        root.destroy()
        return

    load_config()
    # 清理本程序历史遗留规则，避免启动后意外保持断网。
    cleanup_rules()

    create_window()
    start_keyboard_hook()

    threading.Thread(target=tray_thread, daemon=True).start()
    main_window.mainloop()


if __name__ == "__main__":
    main()
