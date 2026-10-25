@echo off
setlocal
echo =====================================================================
echo           GHOSTMIND - Create Windows Desktop Shortcut
echo =====================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$shortcutPath = Join-Path $desktop 'GHOSTMIND.lnk';" ^
  "$workingDir = '%~dp0'.TrimEnd('\');" ^
  "$iconPath = Join-Path $workingDir 'app_icon.ico';" ^
  "$pythonw = Join-Path $workingDir 'venv\Scripts\pythonw.exe';" ^
  "$appScript = Join-Path $workingDir 'desktop_app.py';" ^
  "$wsh = New-Object -ComObject WScript.Shell;" ^
  "$shortcut = $wsh.CreateShortcut($shortcutPath);" ^
  "$shortcut.TargetPath = $pythonw;" ^
  "$shortcut.Arguments = \"`\"$appScript`\"\";" ^
  "$shortcut.WorkingDirectory = $workingDir;" ^
  "if (Test-Path $iconPath) { $shortcut.IconLocation = \"$iconPath,0\" };" ^
  "$shortcut.Description = 'GHOSTMIND - Personal AI Operating System';" ^
  "$shortcut.Save();" ^
  "Write-Host 'SUCCESS: GHOSTMIND shortcut created on your Desktop with custom icon!' -ForegroundColor Green;" ^
  "Write-Host 'Location: ' $shortcutPath -ForegroundColor Cyan;"

echo.
echo =====================================================================
echo You can now double-click the 'GHOSTMIND' icon on your Desktop!
echo It will launch the latest v2.0 AI Operating System seamlessly.
echo =====================================================================
pause
