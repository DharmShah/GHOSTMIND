import os
import subprocess

desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
shortcut_path = os.path.join(desktop, 'GHOSTMIND.lnk')
cwd = os.path.abspath(os.path.dirname(__file__))
pythonw = os.path.join(cwd, 'venv', 'Scripts', 'pythonw.exe')
script = os.path.join(cwd, 'desktop_app.py')
icon = os.path.join(cwd, 'app_icon.ico')

vbs_code = f'''Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{pythonw}"
oLink.Arguments = """{script}"""
oLink.WorkingDirectory = "{cwd}"
oLink.IconLocation = "{icon},0"
oLink.Description = "GHOSTMIND - Personal AI Operating System"
oLink.Save
'''

vbs_path = os.path.join(cwd, '_make_shortcut.vbs')
with open(vbs_path, 'w', encoding='utf-8') as f:
    f.write(vbs_code)

try:
    subprocess.run(['cscript', '//nologo', vbs_path], check=True)
    print("SUCCESS: GHOSTMIND shortcut created on Desktop at:", shortcut_path)
finally:
    if os.path.exists(vbs_path):
        os.remove(vbs_path)
