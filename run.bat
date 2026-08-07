@echo off
REM Obligation monitor runner - for Windows Task Scheduler.
REM Usage:  run.bat daily  |  run.bat exceptions  |  run.bat watchdog
REM Test :  run.bat daily --dry-run

setlocal
cd /d "%~dp0"

set ARGS=%*
if "%ARGS%"=="" set ARGS=daily

set PYTHON=python
if exist ".venv\Scripts\python.exe" set PYTHON=.venv\Scripts\python.exe

echo [%date% %time%] ^> %ARGS% >> run.log
%PYTHON% -m obligation_monitor %ARGS% >> run.log 2>&1
exit /b %ERRORLEVEL%
