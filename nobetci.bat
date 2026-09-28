@echo off
chcp 65001 >nul
title Halisaha Nobetci
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

:basla
echo [%date% %time%] Nobetci baslatiliyor...
.venv\Scripts\python -m bot.nobetci
echo [%date% %time%] Nobetci durdu (kod %errorlevel%), 30 sn sonra yeniden baslayacak. Kapatmak icin pencereyi kapat.
timeout /t 30 /nobreak >nul
goto basla
