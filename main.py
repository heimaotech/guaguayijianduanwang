import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

APP_NAME = "呱呱一键断网与恢复"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GuaguaNetToggle"
CONFIG_FILE = CONFIG_DIR / "config.json"

VK = {
    "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
VK_NAME = {v: k.upper() for k, v in VK.items()}

MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 1001

user32 = ctypes.windll.user32

offline = False
disabled_by_app = []
hotkey_name = "home"
icon = None
main_window = None
status_var = None
adapter_var = None
admin_var = None
hotkey_var = None
recording = False

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def run_ps(command):
    p = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "PowerShell 执行失败")
    return p.stdout.strip()

def get_adapters():
    # 获取物理网卡；不依赖“以太网/Wi-Fi”等语言名称。
    command = (
        "Get-NetAdapter -Physical | "
        "Select-Object Name, InterfaceDescription, Status, ifIndex | "
        "ConvertTo-Json -Compress"
    )
    out = run_ps(command)
    if not out:
        return []
    data = json.loads(out)
    if isinstance(data, dict):
        data = [data]
    return data

def adapter_text():
    try:
        adapters = get_adapters()
        if not adapters:
            return "未检测到物理网络适配器"
        lines = []
        for a in adapters:
            status = str(a.get("Status", "Unknown"))
            mark = "✓" if status.lower() == "up" else "○"
            lines.append(f"{mark} {a.get('Name', '')}    {status}")
        return "\n".join(lines)
    except Exception as e:
        return f"读取网络适配器失败：{e}"

def set_adapter(name, enable):
    cmd = "Enable-NetAdapter" if enable else "Disable-NetAdapter"
    # 使用 -Name 但名称来自系统枚举，不固定中文/英文名称。
    run_ps(f"{cmd} -Name {name!r} -Confirm:$false -ErrorAction Stop")

def go_offline():
    global offline, disabled_by_app
    if offline:
        return
    adapters = get_adapters()
    disabled = []
    for a in adapters:
        if str(a.get("Status", "")).lower() == "up":
            try:
                set_adapter(a["Name"], False)
                disabled.append(a["Name"])
            except Exception:
                pass
    disabled_by_app = disabled
    offline = True
    refresh_ui()

def go_online():
    global offline, disabled_by_app
    if not offline:
        return
    for name in disabled_by_app:
        try:
            set_adapter(name, True)
        except Exception:
            pass
    disabled_by_app = []
    offline = False
    refresh_ui()

def toggle_network():
    try:
        if offline:
            go_online()
        else:
            go_offline()
    except Exception as e:
        messagebox.showerror(APP_NAME, f"切换网络失败：\n{e}")
        refresh_ui()

def load_config():
    global hotkey_name
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        name = str(data.get("hotkey", "home")).lower()
        if name in VK:
            hotkey_name = name
    except Exception:
        hotkey_name = "home"

def save_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps({"hotkey": hotkey_name}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def register_hotkey():
    user32.UnregisterHotKey(None, HOTKEY_ID)
    vk = VK.get(hotkey_name, VK["home"])
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, vk):
        raise RuntimeError(f"{hotkey_name.upper()} 已被其他程序占用。")

def hotkey_loop():
    msg = wt.MSG()
    while True:
        result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if result <= 0:
            break
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            threading.Thread(target=toggle_network, daemon=True).start()

def make_icon():
    img = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, 58, 58), radius=14, fill=(35, 35, 35, 255))
    d.line((18, 32, 46, 32), fill=(255, 255, 255, 255), width=5)
    d.line((32, 18, 32, 46), fill=(255, 255, 255, 255), width=5)
    return img

def refresh_ui():
    def update():
        if status_var:
            status_var.set("网络已断开" if offline else "网络正常")
        if adapter_var:
            adapter_var.set(adapter_text())
        if hotkey_var:
            hotkey_var.set(hotkey_name.upper())
        if admin_var:
            admin_var.set("已获得管理员权限" if is_admin() else "未获得管理员权限")
        if icon:
            icon.title = f"{APP_NAME} — {'已断网' if offline else '网络正常'}"
    if main_window:
        try:
            main_window.after(0, update)
        except Exception:
            pass

def change_hotkey():
    global recording
    if recording:
        return
    recording = True
    messagebox.showinfo(APP_NAME, "请按下你希望使用的快捷键。\n例如：Home、F4、F8 等。\n按 Esc 取消。")
    result = {"name": None}

    win = tk.Toplevel(main_window)
    win.title("设置快捷键")
    win.geometry("330x130")
    win.resizable(False, False)
    ttk.Label(win, text="请按下新的快捷键", font=("Segoe UI", 13)).pack(pady=(24, 10))
    value = tk.StringVar(value="等待按键…")
    ttk.Label(win, textvariable=value).pack()

    def key(event):
        nonlocal result
        if event.keysym == "Escape":
            win.destroy()
            return
        key_name = event.keysym.lower()
        if key_name in VK:
            result["name"] = key_name
            value.set(key_name.upper())
            win.after(250, win.destroy)
        else:
            value.set("暂不支持此按键，请使用 Home / End / Insert / Delete / F1-F12")

    win.bind("<KeyPress>", key)
    win.focus_force()

    def closed():
        global recording
        recording = False
        if result["name"]:
            global hotkey_name
            old = hotkey_name
            hotkey_name = result["name"]
            try:
                register_hotkey()
                save_config()
            except Exception as e:
                hotkey_name = old
                register_hotkey()
                messagebox.showerror(APP_NAME, str(e))
            refresh_ui()
        recording = False

    win.protocol("WM_DELETE_WINDOW", win.destroy)
    def poll_close():
        if not win.winfo_exists():
            closed()
        else:
            main_window.after(100, poll_close)
    main_window.after(100, poll_close)

def show_window():
    main_window.deiconify()
    main_window.lift()
    main_window.focus_force()
    refresh_ui()

def quit_app(icon_obj, item):
    try:
        if offline:
            go_online()
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        icon_obj.stop()
        if main_window:
            main_window.destroy()

def tray_thread():
    global icon
    menu = pystray.Menu(
        pystray.MenuItem("打开设置", lambda i, item: show_window()),
        pystray.MenuItem(
            "切换网络",
            lambda i, item: threading.Thread(target=toggle_network, daemon=True).start()
        ),
        pystray.MenuItem("退出", quit_app),
    )
    icon = pystray.Icon(APP_NAME, make_icon(), APP_NAME, menu)
    icon.run()

def create_window():
    global main_window, status_var, adapter_var, admin_var, hotkey_var
    main_window = tk.Tk()
    main_window.title(APP_NAME)
    main_window.geometry("560x470")
    main_window.resizable(False, False)

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except Exception:
        pass

    outer = ttk.Frame(main_window, padding=28)
    outer.pack(fill="both", expand=True)

    ttk.Label(outer, text=APP_NAME, font=("Segoe UI", 19, "bold")).pack(anchor="w")
    ttk.Label(outer, text="Windows 一键断网与恢复工具", font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 22))

    status_var = tk.StringVar()
    ttk.Label(outer, text="当前状态", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Label(outer, textvariable=status_var, font=("Segoe UI", 15)).pack(anchor="w", pady=(3, 16))

    admin_var = tk.StringVar()
    ttk.Label(outer, text="权限状态", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Label(outer, textvariable=admin_var).pack(anchor="w", pady=(3, 16))

    ttk.Label(outer, text="当前物理网络适配器", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    adapter_var = tk.StringVar()
    adapter_box = ttk.Label(
        outer, textvariable=adapter_var, relief="solid", padding=12,
        font=("Consolas", 10)
    )
    adapter_box.pack(fill="x", pady=(6, 18))

    row = ttk.Frame(outer)
    row.pack(fill="x")
    ttk.Label(row, text="一键切换快捷键", font=("Segoe UI", 10, "bold")).pack(side="left")
    hotkey_var = tk.StringVar()
    ttk.Label(row, textvariable=hotkey_var, font=("Segoe UI", 12, "bold")).pack(side="left", padx=18)
    ttk.Button(row, text="修改快捷键", command=change_hotkey).pack(side="right")

    ttk.Separator(outer).pack(fill="x", pady=22)
    ttk.Label(
        outer,
        text="程序关闭时会自动恢复本程序此前禁用的网络适配器。\n程序将最小化到系统托盘，并持续监听全局快捷键。",
        font=("Segoe UI", 9)
    ).pack(anchor="w")

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(20, 0))
    ttk.Button(buttons, text="立即切换网络", command=lambda: threading.Thread(target=toggle_network, daemon=True).start()).pack(side="left")
    ttk.Button(buttons, text="刷新适配器", command=refresh_ui).pack(side="right")

    def minimize():
        main_window.withdraw()

    main_window.protocol("WM_DELETE_WINDOW", minimize)
    refresh_ui()
    return main_window

def main():
    if not is_admin():
        # EXE manifest 会要求管理员；开发环境直接提示。
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, "本程序必须以管理员身份运行。")
        root.destroy()
        return

    load_config()
    try:
        register_hotkey()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, str(e))
        root.destroy()
        return

    create_window()
    threading.Thread(target=hotkey_loop, daemon=True).start()
    threading.Thread(target=tray_thread, daemon=True).start()
    main_window.mainloop()

if __name__ == "__main__":
    main()
