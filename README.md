# 呱呱一键断网与恢复

Windows 托盘工具：通过 Windows 防火墙临时阻断系统网络流量，实现一键断网 / 恢复。

## 特性
- 400 × 600 主界面，简洁的 Apple 风格信息卡片布局
- 关闭窗口后隐藏到系统托盘，程序继续后台运行
- 默认快捷键 Home，可在界面中重新设置快捷键
- 使用 Windows 低级键盘钩子监听全局按键
- Wi-Fi / Ethernet 网卡保持连接，不禁用网卡
- 不修改 IP、DNS、路由
- 退出程序时清理本程序创建的防火墙规则
- GitHub Actions 自动编译 Windows EXE

## 本地编译
Windows 上运行 `build_windows.bat`。

## GitHub Actions
推送 `v*` 标签，或在 Actions 中手动运行工作流，即可生成 EXE artifact。

## 权限
程序需要管理员权限，因为 Windows 防火墙规则需要管理员权限。PyInstaller 构建时使用 `--uac-admin`。
