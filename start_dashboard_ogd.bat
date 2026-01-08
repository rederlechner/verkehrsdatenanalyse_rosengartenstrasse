@echo off
title Verkehrsdaten Dashboard - Rosengartenbruecke
echo ========================================
echo  Verkehrsdaten Dashboard starten...
echo ========================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo Virtual Environment aktiviert.
) else (
    echo WARNUNG: Virtual Environment nicht gefunden!
    echo Bitte zuerst installieren: python -m venv .venv
    pause
    exit /b 1
)

echo.
echo Starte Streamlit Dashboard...
echo.
echo Falls Port belegt: Beenden Sie andere Streamlit-Instanzen
echo oder aendern Sie den Port mit --server.port=XXXX
echo.
echo Druecken Sie Ctrl+C zum Beenden.
echo.

.venv\Scripts\streamlit.exe run dashboard_ogd.py --server.port=8503

pause
