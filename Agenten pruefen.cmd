@echo off
REM Doppelklick: prueft, ob die Agenten-Anzeige noch die Wahrheit sagt.
REM Bewusst .cmd und nicht .vbs wie die beiden Starter daneben - die verstecken
REM ihr Fenster (pythonw, 0). Hier ist das Fenster der ganze Zweck.
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
  echo Python 3.12 nicht gefunden unter:
  echo   %PY%
  echo.
  pause
  exit /b 1
)

"%PY%" agenten-pruefen.py
echo.
pause
