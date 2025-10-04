@echo off
echo Executando gitupdate...
powershell -ExecutionPolicy Bypass -File "%~dp0gitupdate.ps1"
pause