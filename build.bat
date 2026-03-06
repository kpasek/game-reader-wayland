@echo off
set APP_NAME=Lektor
set ENTRY_FILE=lektor.py
set BUILD_DIR=build_win
set ICON_FILE=app_icon.ico

echo 🚀 Budowanie aplikacji %APP_NAME% na Windows...

:: 1. Czyszczenie poprzednich buildów (WAŻNE przy błędzie Scons)
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
if exist dist rmdir /s /q dist

:: 2. Sprawdzenie czy istnieje ikona
if not exist %ICON_FILE% (
    echo ⚠️ UWAGA: Nie znaleziono pliku %ICON_FILE%. Używam domyślnej ikony.
    set ICON_FLAG=
) else (
    echo ✅ Znaleziono ikonę: %ICON_FILE%
    set ICON_FLAG=--windows-icon-from-ico=%ICON_FILE%
)

:: 3. Kompilacja Nuitka
:: 3. Kompilacja Nuitka
:: W starszych konfiguracjach używamy --mingw64; od Pythona 3.13 ten parametr
:: nie jest obsługiwany przez Nuitka, więc wykrywamy wersję i warunkowo go
:: pomijamy.
set MINGW_FLAG=--mingw64
set ZIG_FLAG=
for /f "delims=" %%A in ('python -c "import sys;print(sys.version_info.major)"') do set PY_MAJOR=%%A
for /f "delims=" %%A in ('python -c "import sys;print(sys.version_info.minor)"') do set PY_MINOR=%%A
if "%PY_MAJOR%"=="3" (
    rem dla Pythona 3.x sprawdź minor
    if %PY_MINOR% GEQ 13 (
        set MINGW_FLAG=
        set ZIG_FLAG=--zig
    )
) else (
    if %PY_MAJOR% GTR 3 (
        set MINGW_FLAG=
    )
)

python -m nuitka ^
    --standalone ^
    --onefile ^
    %MINGW_FLAG% %ZIG_FLAG% ^
    --follow-imports ^
    --enable-plugin=tk-inter ^
    --windows-console-mode=disable ^
    %ICON_FLAG% ^
    --include-package=thefuzz ^
    --include-package=mss ^
    --include-package=PIL ^
    --include-package=Levenshtein ^
    --output-dir=%BUILD_DIR% ^
    -o %APP_NAME%.exe ^
    "%ENTRY_FILE%"

echo.
if exist "%BUILD_DIR%\%APP_NAME%.exe" (
    echo ✅ SUKCES! Plik znajduje się w: %BUILD_DIR%\%APP_NAME%.exe
) else (
    echo ❌ BŁĄD BUDOWANIA. Sprawdź logi powyżej.
)
pause