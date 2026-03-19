@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run.ps1" %*
set EXITCODE=%ERRORLEVEL%
exit /b %EXITCODE%
