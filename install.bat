@echo off
chcp 65001 >nul
echo ========================================
echo   Установка ЖКУ-Центр
echo ========================================
echo.

:: Проверяем, установлен ли Python
where py >nul 2>nul
if %errorlevel% neq 0 (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Python не установлен!
        echo.
        echo Скачайте и установите Python с официального сайта:
        echo https://www.python.org/downloads/
        echo.
        echo ВАЖНО: При установке поставьте галочку "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
)

:: Проверяем версию Python
py --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось определить версию Python
    pause
    exit /b 1
)

echo [1/2] Python найден: 
py --version
echo.

:: Переходим в папку скрипта
cd /d "%~dp0"

echo [2/2] Установка библиотек...
echo.
py -m pip install --upgrade pip
py -m pip install -r requirements.txt

echo.
echo ========================================
echo   Установка завершена!
echo   Теперь запустите запустить.bat
echo ========================================
echo.
pause