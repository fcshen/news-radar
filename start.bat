@echo off
chcp 65001 >nul
title news-radar
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem ====================================================================
rem  Pick a REAL python.
rem  ...\AppData\Local\Microsoft\WindowsApps\python.exe is only a
rem  Microsoft Store placeholder: it runs, does nothing, and exits, which
rem  looks exactly like "Program exited abnormally" with no error text.
rem  So we never call bare "python"; we point at real install folders.
rem ====================================================================
set "PY=D:\anaconda\python.exe"
if exist "%PY%" goto :run

set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%PY%" goto :run
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto :run
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PY%" goto :run
set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if exist "%PY%" goto :run

set "PY=C:\Python313\python.exe"
if exist "%PY%" goto :run
set "PY=C:\Python312\python.exe"
if exist "%PY%" goto :run
set "PY=C:\Python311\python.exe"
if exist "%PY%" goto :run
set "PY=C:\Program Files\Python312\python.exe"
if exist "%PY%" goto :run
set "PY=C:\Program Files\Python311\python.exe"
if exist "%PY%" goto :run

echo.
echo   No usable Python found on this computer.
echo.
echo   Install Python 3.10+ from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" during setup.
echo.
pause
exit /b 1

:run
echo   Python: %PY%
echo.

rem first run only: make sure the 4 packages are there
"%PY%" -c "import requests,yaml,feedparser,qrcode" >nul 2>nul
if errorlevel 1 "%PY%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --disable-pip-version-check

"%PY%" app.py %*
set "RC=%errorlevel%"

echo.
echo   ======================================================
echo     Program stopped (exit code %RC%)
echo     If that was not on purpose, the reason is above.
echo     Log file: %~dp0data\_launch.log
echo   ======================================================
echo.
pause
exit /b %RC%
