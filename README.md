# 呱呱一键断网与恢复

Windows 一键断网与恢复工具。

## 功能

- 默认 Home 全局快捷键
- Home：断开当前正在使用的物理网络适配器
- 再按 Home：恢复本程序之前关闭的适配器
- 自动识别 Wi-Fi / Ethernet，不依赖系统语言和网卡名称
- 不主动处理 VPN、Hyper-V、VMware 等虚拟网卡
- 系统托盘常驻
- 设置窗口可修改快捷键
- 显示管理员权限状态
- 显示当前物理网络适配器
- 程序退出时自动恢复网络
- Windows UAC 管理员权限

## GitHub 自动编译

仓库已经包含 GitHub Actions：

`.github/workflows/build-windows.yml`

上传到 GitHub 后：

1. 打开仓库
2. 进入 `Actions`
3. 选择 `Build Windows EXE`
4. 点击 `Run workflow`
5. 等待 Windows 编译完成
6. 在运行结果的 Artifacts 下载 EXE

也可以创建 `v1.0.0` 之类的 Git tag，工作流会自动构建。

## 本地编译

Windows 上安装 Python 3 后，运行：

```bat
build.bat
```

输出：

```text
dist\呱呱一键断网与恢复.exe
```

EXE 会要求 Windows 管理员权限。

## 注意

程序依赖 Windows PowerShell 的 NetAdapter 模块。

全局快捷键可能受到其他软件、游戏反作弊、企业安全策略等限制，因此无法承诺在所有特殊环境下绝对可用。
