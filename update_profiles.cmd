@echo off
setlocal
cd /d "%~dp0"

echo [1/2] Validate Excel and export JSON...
py -3 -B tools\export_profiles.py
if errorlevel 1 goto :failed

echo [2/2] Run regression tests...
py -3 -B -m unittest discover -s tests -v
if errorlevel 1 goto :failed
py -3 -B -m unittest discover -s lib\tests -v
if errorlevel 1 goto :failed

echo.
echo Device profiles updated successfully.
exit /b 0

:failed
echo.
echo Device profile update failed. JSON was not accepted.
exit /b 1
