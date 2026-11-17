@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "%~dp0"
cl /nologo /LD /O2 /EHsc /W3 /DUNICODE /D_UNICODE ogprobe.cpp /link /OUT:ogprobe.dll dwmapi.lib user32.lib gdi32.lib comctl32.lib
if errorlevel 1 exit /b 1
echo BUILD_OK
