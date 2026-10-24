@echo off
setlocal
echo Creating Desktop shortcut for GHOSTMIND...

powershell -NoProfile -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$shortcutPath = Join-Path $desktop 'GHOSTMIND.lnk';" ^
  "$targetPath = '%~dp0dist\GHOSTMIND\GHOSTMIND.exe';" ^
  "$iconPath = '%~dp0app_icon.ico';" ^
  "$workingDir = '%~dp0';" ^
  "$wsh = New-Object -ComObject WScript.Shell;" ^
  "$shortcut = $wsh.CreateShortcut($shortcutPath);" ^
  "$shortcut.TargetPath = $targetPath;" ^
  "$shortcut.WorkingDirectory = $workingDir;" ^
  "$shortcut.IconLocation = \"$iconPath,0\";" ^
  "$shortcut.Description = 'GHOSTMIND - Local Offline Desktop Chatbot';" ^
  "$shortcut.Save();" ^
  "Write-Host 'GHOSTMIND shortcut placed on your Windows Desktop!' -ForegroundColor Green"

pause
