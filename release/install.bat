@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem ---------------------------------------------------------------------------
rem  Edge Win7 Glass - one-click per-user installer (no admin needed)
rem  Put this file next to EdgeWin7Glass.exe and double-click.
rem    install.bat                install + start with Windows + launch
rem    install.bat /noautostart   install without the "start with Windows" entry
rem ---------------------------------------------------------------------------

set "APPNAME=Edge Win7 Glass"
set "EXENAME=EdgeWin7Glass.exe"
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\Programs\EdgeWin7Glass"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "DESKTOP=%USERPROFILE%\Desktop"
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
set "UNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\EdgeWin7Glass"

if not exist "%SRC%%EXENAME%" (
    echo [错误] 找不到 %EXENAME%
    echo        请把 install.bat 和 %EXENAME% 放在同一个文件夹里再运行。
    pause & exit /b 1
)

echo ============================================
echo   %APPNAME%  安裝程序 / installer
echo ============================================
echo.

echo [1/5] 停止正在运行的旧版本...
if exist "%DEST%\%EXENAME%" start "" /wait "%DEST%\%EXENAME%" --quit >nul 2>&1
taskkill /IM "%EXENAME%" /F >nul 2>&1
timeout /t 1 >nul

echo [2/5] 复制文件到 %DEST%
if not exist "%DEST%" mkdir "%DEST%" >nul 2>&1
copy /y "%SRC%%EXENAME%" "%DEST%\%EXENAME%" >nul || (echo [错误] 复制失败 & pause & exit /b 1)
if exist "%SRC%uninstall.bat" (
    copy /y "%SRC%uninstall.bat" "%DEST%\Uninstall.bat" >nul
) else (
    echo [警告] 缺少 uninstall.bat，卸载项将无法使用（可手动删除 %DEST%）
)
if exist "%SRC%README.txt" copy /y "%SRC%README.txt" "%DEST%\README.txt" >nul
if exist "%SRC%settings.md" copy /y "%SRC%settings.md" "%DEST%\settings.md" >nul

echo [3/5] 创建快捷方式...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$w=New-Object -ComObject WScript.Shell;" ^
 "foreach($p in @('%STARTMENU%\%APPNAME%.lnk','%DESKTOP%\%APPNAME%.lnk')){" ^
 "  $s=$w.CreateShortcut($p); $s.TargetPath='%DEST%\%EXENAME%'; $s.WorkingDirectory='%DEST%';" ^
 "  $s.IconLocation='%DEST%\%EXENAME%,0'; $s.Description='Win7 Aero glass title bar for Chromium'; $s.Save() }" >nul
if errorlevel 1 echo       (快捷方式创建失败，可手动拖拽 %DEST%\%EXENAME%)

echo [4/5] 注册卸载信息...
reg add "%UNKEY%" /v DisplayName    /t REG_SZ /d "%APPNAME%" /f >nul
reg add "%UNKEY%" /v DisplayVersion /t REG_SZ /d "1.1.1" /f >nul
reg add "%UNKEY%" /v Publisher      /t REG_SZ /d "Edge Win7 Glass" /f >nul
reg add "%UNKEY%" /v DisplayIcon    /t REG_SZ /d "%DEST%\%EXENAME%" /f >nul
reg add "%UNKEY%" /v InstallLocation /t REG_SZ /d "%DEST%" /f >nul
reg add "%UNKEY%" /v UninstallString /t REG_SZ /d "\"%DEST%\Uninstall.bat\"" /f >nul
reg add "%UNKEY%" /v NoModify /t REG_DWORD /d 1 /f >nul
reg add "%UNKEY%" /v NoRepair /t REG_DWORD /d 1 /f >nul
reg add "HKCU\Software\EdgeWin7Glass" /v InstallDir /t REG_SZ /d "%DEST%" /f >nul

if /i "%~1"=="/noautostart" (
  echo       开机自启：未启用（可随时在托盘菜单里打开）
) else (
  reg add "%RUNKEY%" /v EdgeWin7Glass /t REG_SZ /d "\"%DEST%\%EXENAME%\"" /f >nul
  echo       开机自启：已启用
)

echo [5/5] 启动 %APPNAME% ...
start "" "%DEST%\%EXENAME%"
timeout /t 2 >nul

echo.
echo 安装完成。托盘里会出现蓝色玻璃图标：
echo   左键 打开设置页  http://127.0.0.1:8721/
echo   右键 设置页 / 暂停接管 / 开机自启 / 退出
echo.
echo 卸载：设置 -^> 应用 -^> 已安装的应用 -^> %APPNAME%
echo       或运行 "%DEST%\Uninstall.bat"
echo.
pause
endlocal
