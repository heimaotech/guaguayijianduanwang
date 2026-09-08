@echo off
chcp 65001 >nul
echo ========================================
echo 呱呱一键断网与恢复 - Windows 原生版
echo ========================================
echo.

python -m pip install --upgrade pip
python -m pip install pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name "呱呱一键断网与恢复" main.py

echo.
echo 编译完成：
echo dist\呱呱一键断网与恢复.exe
pause
