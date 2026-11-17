@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

rem ---------------------------------------------------------------------------
rem  Edge Win7 Glass - uninstaller (per-user, no admin needed)
rem    uninstall.bat           remove program, shortcuts and registry entries
rem                            (settings + logs in %APPDATA% are kept)
rem    uninstall.bat /purge    also delete settings.json and the logs
rem ---------------------------------------------------------------------------

if not defined APPNAME  set "APPNAME=Edge Win7 Glass"
if not defined EXENAME   set "EXENAME=EdgeWin7Glass.exe"
if not defined REGNAME   set "REGNAME=EdgeWin7Glass"
if not defined DEST      set "DEST=%LOCALAPPDATA%\Programs\EdgeWin7Glass"
if not defined CFGDIR    set "CFGDIR=%APPDATA%\edge-win7-glass"
if not defined STARTMENU set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if not defined DESKTOP   set "DESKTOP=%USERPROFILE%\Desktop"
set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
set "UNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\%REGNAME%"

rem 工作目录不能待在要删除的目录里
cd /d "%TEMP%" 2>nul

echo ============================================
echo   %APPNAME%  卸载程序 / uninstaller
echo ============================================
echo.

if not exist "%DEST%" (
    echo [i] 未发现安装目录 %DEST%，继续清理注册表和快捷方式。
)

echo [1/4] 停止正在运行的 %APPNAME% ...
if exist "%DEST%\%EXENAME%" start "" /wait "%DEST%\%EXENAME%" --quit >nul 2>&1
taskkill /IM "%EXENAME%" /F >nul 2>&1
timeout /t 2 >nul

echo [2/4] 删除开机自启、卸载项和快捷方式 ...
reg delete "%RUNKEY%" /v "%REGNAME%" /f >nul 2>&1
reg delete "%UNKEY%" /f >nul 2>&1
reg delete "HKCU\Software\%REGNAME%" /f >nul 2>&1
del /f /q "%STARTMENU%\%APPNAME%.lnk" >nul 2>&1
del /f /q "%DESKTOP%\%APPNAME%.lnk" >nul 2>&1

if /i "%~1"=="/purge" (
    echo [3/4] 删除设置和日志：%CFGDIR%
    rd /s /q "%CFGDIR%" >nul 2>&1
    rd /s /q "%LOCALAPPDATA%\edge-win7-glass" >nul 2>&1
) else (
    echo [3/4] 保留设置和日志：%CFGDIR%
)

echo [4/4] 删除程序目录 %DEST% ...
if exist "%DEST%" (
    rem 从安装目录里启动时，批处理自身被占用 —— 交给 2 秒后的 PowerShell 删
    set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
    if exist "!PS!" (
        start "" /min "!PS!" -NoProfile -Command "Start-Sleep -Seconds 2; Remove-Item -LiteralPath '%DEST%' -Recurse -Force -ErrorAction SilentlyContinue" >nul 2>&1
    ) else (
        start "" /min cmd /c "timeout /t 2 >nul & rd /s /q ""%DEST%""" >nul 2>&1
    )
)

echo.
echo 卸载完成。
if /i not "%~1"=="/purge" echo   设置和日志仍保留在 %CFGDIR%（要一起删就运行 uninstall.bat /purge）
echo   所有被接管的窗口已还原成普通 Windows 11 窗口。
echo.
pause
endlocal
