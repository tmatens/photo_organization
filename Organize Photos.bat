@echo off
rem Double-click this file to organize photos. It installs Python if it is
rem missing, asks where the photos are and where the copy goes (a drive
rem letter or a folder dragged onto the window), runs a quick test that
rem copies nothing, and then, if you say yes, does the real copy.
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

echo  Where are the old photos?
echo  Type a drive letter (like E), or drag a folder from File Explorer
echo  onto this window. Then press Enter. To see drive letters, open File
echo  Explorer and click "This PC".
echo.
set "SOURCES="
set "SHOW="
set "SDRIVES="
set /a COUNT=0
:ask_source
set /a NEXT=COUNT+1
set "ASK= Old photos #!NEXT!: "
if !COUNT! gtr 0 set "ASK= Old photos #!NEXT! (or just press Enter if that's all): "
set "ANSWER="
set /p "ANSWER=!ASK!"
if not defined ANSWER (
    if !COUNT! gtr 0 goto :sources_done
    goto :ask_source
)
call :to_path ANSWER
if not defined RESULT (
    echo    That is not a drive or folder on this computer. Try again.
    goto :ask_source
)
if "!RKIND!"=="drive" if /i "!RDRIVE!:"=="%SystemDrive%" (
    echo.
    echo    !RDRIVE!: is this computer's main drive. Scanning all of it is slow
    echo    and picks up thousands of system pictures ^(icons, program images^).
    echo    It is usually better to drag your Pictures folder here instead.
    set "GO="
    set /p "GO=   Type Y to use all of !RDRIVE!: anyway, or just press Enter to choose again: "
    if /i not "!GO!"=="Y" goto :ask_source
)
if "!RKIND!"=="drive" (
    set "SOURCES=!SOURCES! --source !RESULT!"
    echo    Added: !RESULT!  ^(the whole drive^)
) else (
    set "SOURCES=!SOURCES! --source "!RESULT!""
    echo    Added: !RESULT!
)
set "SHOW=!SHOW!   !RESULT!"
set "SDRIVES=!SDRIVES! !RDRIVE!"
set /a COUNT=NEXT
goto :ask_source
:sources_done

echo.
echo  Where should the organized copy go?
echo  Type a drive letter (like D), or drag a folder onto this window.
echo  A folder called Organized is made inside it.
echo.
:ask_output
set "ANSWER="
set /p "ANSWER= Copy to: "
if not defined ANSWER goto :ask_output
call :to_path ANSWER
if not defined RESULT (
    echo    That is not a drive or folder on this computer. Try again.
    goto :ask_output
)
if "!RKIND!"=="drive" (set "OUT=!RDRIVE!:\Organized") else (set "OUT=!RESULT!\Organized")
set "SAME="
for %%d in (!SDRIVES!) do if /i "%%d"=="!RDRIVE!" set "SAME=1"
if defined SAME (
    echo.
    echo    That is the same drive as some of the old photos. It works, but
    echo    if that drive fails, the photos and the copy are lost together.
    set "GO="
    set /p "GO=   Type Y to copy there anyway, or just press Enter to choose again: "
    if /i not "!GO!"=="Y" goto :ask_output
)
echo    The copy will go into !OUT!

echo.
echo  Old photos:!SHOW!
echo  Copy to:      !OUT!
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

:to_path
rem Turns an answer into a path. A letter, with or without : and \, is the
rem whole drive (RESULT=E:\, RKIND=drive). Anything else is a folder, as
rem typed or dragged in with quotes (RESULT without a trailing \,
rem RKIND=folder). RDRIVE is the drive letter. RESULT is empty when the
rem drive or folder does not exist.
set "RESULT="
set "RDRIVE="
set "RKIND="
set "P=!%1!"
set "P=!P:"=!"
:to_path_front
if not defined P exit /b
if "!P:~0,1!"==" " set "P=!P:~1!" & goto :to_path_front
:to_path_back
if not defined P exit /b
if "!P:~-1!"==" " set "P=!P:~0,-1!" & goto :to_path_back
set "D=!P::=!"
set "D=!D:\=!"
if "!P:~3!"=="" if defined D if "!D:~1!"=="" (
    call :upper D
    if not exist "!D!:\" exit /b
    set "RESULT=!D!:\"
    set "RDRIVE=!D!"
    set "RKIND=drive"
    exit /b
)
if "!P:~-1!"=="\" set "P=!P:~0,-1!"
if not exist "!P!\" exit /b
rem Drive letters in capitals, so "e:\photos" today and "E:\photos" next
rem time are the same folder to the manifest and a rerun resumes.
set "D=!P:~0,1!"
call :upper D
set "RESULT=!D!!P:~1!"
set "RDRIVE=!D!"
set "RKIND=folder"
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
