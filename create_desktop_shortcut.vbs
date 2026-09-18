' Creates a Desktop shortcut to Inox Hydra.
'
' Resolves its own location at run time rather than hardcoding an install path,
' so the shortcut is correct no matter where the user unzipped the product.
'
' Strict Invariants:
' - Zero em-dashes.

Set fso = CreateObject("Scripting.FileSystemObject")
strInstallDir = fso.GetParentFolderName(WScript.ScriptFullName)
strLauncher = fso.BuildPath(strInstallDir, "launch_studio.bat")

If Not fso.FileExists(strLauncher) Then
    WScript.Echo "Could not find launch_studio.bat next to this script." & vbCrLf & _
                 "Expected at: " & strLauncher & vbCrLf & _
                 "Keep create_desktop_shortcut.vbs in the install folder."
    WScript.Quit 1
End If

Set WshShell = CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")
Set oShortcut = WshShell.CreateShortcut(fso.BuildPath(strDesktop, "LinkedIn Studio.lnk"))
oShortcut.TargetPath = strLauncher
oShortcut.WorkingDirectory = strInstallDir
oShortcut.Description = "Inox Hydra (LinkedIn Studio) - Local Creator & Analytics Engine"
oShortcut.WindowStyle = 1
oShortcut.Save

WScript.Echo "Shortcut created on Desktop, pointing at:" & vbCrLf & strLauncher
