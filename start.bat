@echo off
rem Double-click launcher for Hush Brain (Windows).
cd /d "%~dp0"
where uv >nul 2>nul
if %errorlevel%==0 (
    uv run hush serve
) else (
    python -m pip install -e . >nul
    python -m hush_brain.cli serve
)
pause
