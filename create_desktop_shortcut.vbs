Set WshShell = CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")
Set oShortcut = WshShell.CreateShortcut(strDesktop & "\LinkedIn Studio.lnk")
oShortcut.TargetPath = "c:\Users\remoteadmin\Downloads\Linkedin strategy\launch_studio.bat"
oShortcut.WorkingDirectory = "c:\Users\remoteadmin\Downloads\Linkedin strategy"
oShortcut.Description = "LinkedIn Studio (LocalTaplio) - Executive Creator & Analytics Engine"
oShortcut.WindowStyle = 1
oShortcut.Save
WScript.Echo "Shortcut created on Desktop successfully."
