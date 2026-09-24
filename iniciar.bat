@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\activate.bat" goto :sin_instalar
if not exist "backend\.env" goto :sin_instalar

rem Dos ventanas: el servidor (backend) y la interfaz (frontend). No las cierres mientras usas la app.
start "Revisor - servidor (no cerrar)" /D "%~dp0backend" cmd /k "call .venv\Scripts\activate.bat && alembic upgrade head && uvicorn app.main:app --port 8000"
start "Revisor - interfaz (no cerrar)" /D "%~dp0frontend" cmd /k "npm run dev"

echo Abriendo la app en el navegador...
timeout /t 8 /nobreak >nul
start "" "http://localhost:5173"
exit /b 0

:sin_instalar
echo Primero ejecuta instalar.bat (doble clic) y llena backend\.env
pause
exit /b 1
