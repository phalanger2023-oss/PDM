@echo off
cd /d "%~dp0"
set REFAIRE=0
if not exist ".venv\Scripts\python.exe" set REFAIRE=1
if "%REFAIRE%"=="0" (
.venv\Scripts\python.exe -c "import flask, pymupdf, bcrypt" >nul 2>nul
if errorlevel 1 set REFAIRE=1
)
if "%REFAIRE%"=="0" goto lancer

echo Preparation de l'environnement Python - une seule fois...
if exist ".venv" rmdir /s /q ".venv"
py -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 goto pas_python
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto echec_modules

:lancer
start "" http://127.0.0.1:5000
.venv\Scripts\python.exe app.py
pause
exit /b 0

:pas_python
echo Python est introuvable. Installez-le pour tous les utilisateurs.
pause
exit /b 1

:echec_modules
echo Echec de l'installation des modules.
pause
exit /b 1
