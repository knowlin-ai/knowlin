@echo off
rem Knowlin starten (Windows; Python-Paket duckpilot).
rem  - Beim ersten Mal: Python-Umgebung unter %LOCALAPPDATA%\duckpilot anlegen (nicht in OneDrive),
rem    Pakete installieren und eine Verknuepfung auf dem Desktop und im Startmenue anlegen.
rem  - Danach: Knowlin als eigenes Programmfenster starten, ohne Konsole.
rem  - Mit Argumenten (z. B. start.bat --backend robotd) laeuft es wie frueher in der Konsole.
setlocal
cd /d "%~dp0"
set "HERE=%~dp0"
set "VENV=%LOCALAPPDATA%\duckpilot\venv"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 oder neuer fehlt. Installieren von https://www.python.org/downloads/ ^(Haken bei "Add to PATH"^).
  pause
  exit /b 1
)
if not exist "%VENV%\Scripts\python.exe" (
  echo Lege Python-Umgebung an unter %VENV% ...
  py -3 -m venv "%VENV%" || goto :fehler
)
rem Pakete installieren, wenn requirements.txt neu ist oder sich geaendert hat
fc /b requirements.txt "%VENV%\requirements.txt" >nul 2>nul
if errorlevel 1 (
  echo Installiere Pakete ...
  "%VENV%\Scripts\python" -m pip install --upgrade pip >nul
  "%VENV%\Scripts\python" -m pip install -r requirements.txt || goto :fehler
  copy /y requirements.txt "%VENV%\requirements.txt" >nul
)

if not "%~1"=="" (
  "%VENV%\Scripts\python" -m duckpilot %*
  goto :eof
)

call :verknuepfung
start "" "%VENV%\Scripts\pythonw.exe" -m duckpilot --app
goto :eof

:verknuepfung
rem Fehlende Verknuepfungen anlegen. Alte Namen ("duckpilot") benennt Knowlin beim Start selbst um und zieht Symbol,
rem Ziel und Arbeitsordner nach (ausser bei einem Stand unter "Zweige").
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "$ico = '%HERE%knowlin.ico'; if (-not (Test-Path $ico)) { $ico = '%HERE%duckpilot.ico' };" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  foreach ($v in @(@('Knowlin - Microduck.lnk', '-m duckpilot --app --modul duckpilot', 'Knowlin - direkt zur Microduck', '%HERE%duckpilot.ico', 'duckpilot.lnk'), @('Knowlin.lnk', '-m duckpilot --app', 'Knowlin - Startseite mit allen Verkoerperungen', $ico, ''))) {" ^
  "    $l = Join-Path $dir $v[0]; $alt = if ($v[4]) { Join-Path $dir $v[4] } else { '' };" ^
  "    if (-not (Test-Path $l) -and -not ($alt -and (Test-Path $alt))) {" ^
  "      $s = $w.CreateShortcut($l); $s.TargetPath = '%VENV%\Scripts\pythonw.exe'; $s.Arguments = $v[1];" ^
  "      $s.WorkingDirectory = '%HERE%'; $s.IconLocation = $v[3]; $s.Description = $v[2]; $s.Save();" ^
  "      Write-Host ('Verknuepfung angelegt: ' + $l) } } }"
exit /b 0

:fehler
echo Einrichtung fehlgeschlagen - siehe Meldung oben.
pause
exit /b 1
