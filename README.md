# 呱呱一键断网与恢复

Windows 原生轻量版。

## 核心架构

- Win32 原生 GUI
- Windows `RegisterHotKey` 全局快捷键
- Windows `Shell_NotifyIcon` 系统托盘
- Windows Firewall 临时阻断网络
- 不禁用 Wi-Fi / Ethernet 网卡
- 不修改 IP、DNS、路由
- 不依赖第三方 Python GUI / 托盘库
- 使用 Microsoft YaHei UI

## 默认快捷键

Home

可以在主界面直接点击“修改”，无需弹出设置窗口。

## 编译

GitHub Actions 会自动编译 Windows EXE。

也可以在 Windows 上执行：

```bat
build_windows.bat
```

输出：

```text
dist\呱呱一键断网与恢复.exe
```

## 注意

程序需要管理员权限，因为 Windows 防火墙规则需要管理员权限。
