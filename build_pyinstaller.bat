@echo off
set APP_NAME=Lektor
set ENTRY_FILE=lektor.py
set BUILD_DIR=build_pyinstaller
set ICON_FILE=app_icon.ico

echo 🚀 Budowanie aplikacji %APP_NAME% przy uzyciu PyInstaller...

:: 1. Czyszczenie poprzednich buildów
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
if exist dist rmdir /s /q dist

:: 2. Sprawdzenie czy istnieje ikona
if not exist %ICON_FILE% (
    echo ⚠️ UWAGA: Nie znaleziono pliku %ICON_FILE%. Używam domyślnej ikony.
    set ICON_FLAG=
) else (
    echo ✅ Znaleziono ikonę: %ICON_FILE%
    set ICON_FLAG=--icon="%CD%\%ICON_FILE%"
)

:: 3. Kompilacja PyInstaller
:: --noconsole: wyłącza okno konsoli
:: --onefile: pakuje wszystko do jednego pliku EXE
:: --collect-all customtkinter: upewnia się, że wszystkie zasoby customtkinter są dołączone
python -m PyInstaller ^
  --noconsole ^
  --onefile ^
  %ICON_FLAG% ^
  --name=%APP_NAME% ^
  --workpath=%BUILD_DIR% ^
  --specpath=%BUILD_DIR% ^
  --collect-all=customtkinter ^
  "%CD%\%ENTRY_FILE%"

echo.
if exist "dist\%APP_NAME%.exe" (
    echo ✅ SUKCES! Plik znajduje się w: dist\%APP_NAME%.exe
) else (
    echo ❌ BŁĄD BUDOWANIA. Sprawdź logi powyżej.
)
pause