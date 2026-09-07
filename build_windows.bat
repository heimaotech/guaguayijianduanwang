@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo   呱呱一键断网与恢复
echo   Windows EXE 编译
echo ==========================================

py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 -m pip install pyinstaller

py -3 -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "呱呱一键断网与恢复" ^
    --uac-admin ^
    main.py

echo.
echo 编译完成：
echo dist\呱呱一键断网与恢复.exe
echo.

pause
