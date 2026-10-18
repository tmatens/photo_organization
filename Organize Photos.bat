@echo off
rem Double-click this file to organize photos. It installs Python if it is
rem missing, asks which drives to use, runs a quick test that copies
rem nothing, and then, if you say yes, does the real copy.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Photo Organizer

echo.
echo  ===== Photo Organizer =====
echo  Your original photos are never changed, moved or deleted.
echo.

call :find_python
if not defined PY (
    echo  Python is not installed yet. Installing it now; this takes a few
    echo  minutes. If Windows asks for permission, click Yes.
    echo.
    winget install --exact --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
    call :find_python
)
if not defined PY (
    echo.
    echo  Python could not be installed automatically. Install it from
    echo  https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
    echo  then double-click this file again.
    goto :end
)

echo  Getting the tool ready ^(only slow the first time^)...
%PY% -m pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo  Setup failed. Check the internet connection and try again.
    goto :end
)
rem iPhone HEIC support is optional; the tool says at the end if it was needed.
%PY% -m pip install --disable-pip-version-check --quiet -r requirements-optional.txt >nul 2>&1
echo  Ready.
echo.

echo  Open File Explorer and click "This PC" to see the drive letters.
echo.
:ask_sources
set "SOURCES="
set "ANSWER="
set /p "ANSWER= Letters of the OLD drives, with spaces between (for example: E F G): "
if not defined ANSWER goto :ask_sources
set "ANSWER=!ANSWER::= !"
set "ANSWER=!ANSWER:\= !"
set "ANSWER=!ANSWER:,= !"
call :upper ANSWER
for %%d in (!ANSWER!) do (
    if not exist "%%d:\" (
        echo  There is no drive %%d: plugged in. Try again.
        goto :ask_sources
    )
    set "SOURCES=!SOURCES! --source %%d:\"
)

:ask_output
set "DEST="
set /p "DEST= Letter of the NEW drive to copy to (for example: D): "
if not defined DEST goto :ask_output
set "DEST=!DEST::=!"
set "DEST=!DEST:\=!"
set "DEST=!DEST: =!"
call :upper DEST
if not exist "!DEST!:\" (
    echo  There is no drive !DEST!: plugged in. Try again.
    goto :ask_output
)
set "OUT=!DEST!:\Organized"

echo.
echo  Step 1 of 2: a quick test on 500 files. Nothing is copied.
echo.
%PY% organize_photos.py!SOURCES! --output "!OUT!" --dry-run --sample 500
if errorlevel 1 goto :end
if exist "!OUT!\manifest_dryrun.csv" start "" "!OUT!\manifest_dryrun.csv"

echo.
echo  A spreadsheet of what the tool would do should now be open. Camera
echo  photos should be going into year and month folders, and screenshots
echo  and odds and ends into _review.
echo.
set "GO="
set /p "GO= Type Y and press Enter to copy everything for real (anything else stops): "
if /i not "!GO!"=="Y" (
    echo  Stopped. Nothing was copied.
    goto :end
)

echo.
echo  Step 2 of 2: copying. This can take hours on big drives. Keep this
echo  window open and the computer awake. If it is interrupted, double-click
echo  this file again with the same answers and it continues where it stopped.
echo.
%PY% organize_photos.py!SOURCES! --output "!OUT!"
if exist "!OUT!" start "" "!OUT!"

:end
echo.
pause
exit /b

:upper
rem Drive letters in capitals, so "e" today and "E" next time are the same
rem drive to the manifest and an interrupted run resumes instead of rescanning.
for %%u in (A B C D E F G H I J K L M N O P Q R S T U V W X Y Z) do set "%1=!%1:%%u=%%u!"
exit /b

:find_python
rem Ignores the Microsoft Store placeholder, which is on PATH but cannot
rem run anything.
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3" && exit /b
python --version >nul 2>&1 && set "PY=python" && exit /b
for %%p in ("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe") do (
    if exist "%%~p" "%%~p" -3 --version >nul 2>&1 && set PY="%%~p" -3 && exit /b
)
for /d %%p in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~p\python.exe" set PY="%%~p\python.exe"
)
exit /b
