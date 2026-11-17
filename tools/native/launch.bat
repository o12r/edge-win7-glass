@echo off
setlocal

for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
set "PYTHONW=%ROOT%\.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo Python environment not found: "%PYTHONW%"
    echo Create the project .venv before launching Edge Win7 Glass.
    exit /b 1
)

start "" "%PYTHONW%" "%~dp0gt_daemon.py" %*