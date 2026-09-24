@echo off
setlocal
cd /d "%~dp0"
title Revisor de tareas - actualizacion
echo Cierra antes las ventanas "Revisor - servidor" y "Revisor - interfaz" si estan abiertas.
pause

echo [1/4] Descargando la version nueva...
git pull
if errorlevel 1 goto :error

echo [2/4] Librerias de Python...
cd /d "%~dp0backend"
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error
pip install -e ".[dev]"
if errorlevel 1 goto :error
python scripts\crear_env.py

echo [3/4] Base de datos...
alembic upgrade head
if errorlevel 1 goto :error

echo [4/4] Interfaz web...
cd /d "%~dp0frontend"
call npm install
if errorlevel 1 goto :error

echo.
echo Listo. Abre la app con doble clic en iniciar.bat
pause
exit /b 0

:error
echo.
echo *** Algo fallo. Toma una captura de esta ventana para revisarlo. ***
pause
exit /b 1
