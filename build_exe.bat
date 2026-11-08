@echo off
chcp 65001 >nul
REM ==== Tạo VietHoaGame.exe — cần Python 3.10+ (python.org, tích "Add python.exe to PATH") ====
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Chua cai Python. Tai tai https://www.python.org/downloads/ va tich "Add python.exe to PATH".
  pause
  exit /b 1
)
python -m pip install --upgrade pip
python -m pip install pyinstaller anthropic
python -m PyInstaller --noconfirm --onefile --windowed --name VietHoaGame ^
  --add-data "vntrans\assets;vntrans\assets" ^
  --collect-submodules anthropic --copy-metadata anthropic ^
  vntrans_app.py
if errorlevel 1 (
  echo LOI khi build.
  pause
  exit /b 1
)
echo.
echo ===== XONG: dist\VietHoaGame.exe =====
explorer dist
pause
