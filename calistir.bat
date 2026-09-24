@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Kurulum yapiliyor, bir kereye mahsus...
    py -3.12 -m venv .venv || py -m venv .venv
    .venv\Scripts\python -m pip install -q -r requirements.txt
    .venv\Scripts\python -m playwright install chromium
)

rem Parametreyle cagrildiysa (Gorev Zamanlayici gibi) direkt calistir
if not "%~1"=="" (
    .venv\Scripts\python -m bot.main %*
    goto :eof
)

echo.
echo  1) Deneme (tiklamaz, Telegram'a rapor atar)
echo  2) Tek tur bak, bos varsa al
echo  3) 10 dakika boyunca dene (acilis saati)
echo  4) NOBETCI: surekli izler, kaydeder, bos hedef seans gorunce alir (Ctrl+C ile durur)
echo  5) Gozlem analizi (hangi seans kacta acildi / kapildi)
echo.
set /p SECIM=Secim (1-5):

if "%SECIM%"=="1" .venv\Scripts\python -m bot.main --dry-run
if "%SECIM%"=="2" .venv\Scripts\python -m bot.main
if "%SECIM%"=="3" .venv\Scripts\python -m bot.main --sure 10
if "%SECIM%"=="4" .venv\Scripts\python -m bot.nobetci
if "%SECIM%"=="5" .venv\Scripts\python -m bot.analiz

echo.
pause
