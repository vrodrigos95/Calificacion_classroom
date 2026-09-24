@echo off
setlocal
cd /d "%~dp0"
title Revisor de tareas - instalacion
echo === Revisor de tareas: instalacion ===
echo.

where python >nul 2>nul
if errorlevel 1 goto :sin_python
where npm >nul 2>nul
if errorlevel 1 goto :sin_node

echo [1/4] Instalando las librerias de Python. Tarda unos minutos...
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto :error
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error
python -m pip install --quiet --upgrade pip
pip install -e ".[dev]"
if errorlevel 1 goto :error

echo.
echo [2/4] Preparando el archivo de configuracion backend\.env...
python scripts\crear_env.py
if errorlevel 1 goto :error

echo.
echo [3/4] Creando o actualizando la base de datos...
alembic upgrade head
if errorlevel 1 goto :error

echo.
echo [4/4] Instalando la interfaz web. Tarda unos minutos...
cd /d "%~dp0frontend"
call npm install
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Instalacion terminada.
echo  Si arriba dice "Faltan por llenar", abre backend\.env con el
echo  Bloc de notas y pega tus datos de Google Cloud.
echo  Despues abre la app con doble clic en iniciar.bat
echo ============================================================
pause
exit /b 0

:sin_python
echo No encuentro Python. Instalalo desde https://www.python.org/downloads/
echo y marca la casilla "Add python.exe to PATH". Luego vuelve a abrir este archivo.
pause
exit /b 1

:sin_node
echo No encuentro Node.js. Instala la version LTS desde https://nodejs.org/
echo Luego vuelve a abrir este archivo.
pause
exit /b 1

:error
echo.
echo *** Algo fallo. Toma una captura de esta ventana para revisarlo. ***
pause
exit /b 1
