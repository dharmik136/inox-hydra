' Creates a Desktop shortcut to Inox Hydra.
'
' Resolves its own location at run time rather than hardcoding an install path,
' so the shortcut is correct no matter where the user unzipped the product.
'
' Works in both layouts it ships in. The portable ZIP has InoxHydra.bat; a
' source checkout has launch_studio.bat. It looked only for the second, so in
' the ZIP, where it also ships, it stopped with "Could not find
' launch_studio.bat" every time.
'
' Strict Invariants:
' - Zero em-dashes.

Set fso = CreateObject("Scripting.FileSystemObject")
strInstallDir = fso.GetParentFolderName(WScript.ScriptFullName)

strLauncher = ""
For Each strName In Array("InoxHydra.bat", "launch_studio.bat")
    If strLauncher = "" Then
        If fso.FileExists(fso.BuildPath(strInstallDir, strName)) Then
            strLauncher = fso.BuildPath(strInstallDir, strName)
        End If
    End If
Next

If strLauncher = "" Then
    WScript.Echo "Could not find InoxHydra.bat or launch_studio.bat next to this script." & vbCrLf & _
                 "Looked in: " & strInstallDir & vbCrLf & _
                 "Keep create_desktop_shortcut.vbs in the Inox Hydra folder."
    WScript.Quit 1
End If

Set WshShell = CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")
Set oShortcut = WshShell.CreateShortcut(fso.BuildPath(strDesktop, "Inox Hydra.lnk"))
oShortcut.TargetPath = strLauncher
oShortcut.WorkingDirectory = strInstallDir
oShortcut.Description = "Inox Hydra - Local Creator & Analytics Engine"
oShortcut.WindowStyle = 1
strIcon = fso.BuildPath(strInstallDir, "assets\inox_hydra.ico")
If fso.FileExists(strIcon) Then
    oShortcut.IconLocation = strIcon & ",0"
End If
oShortcut.Save

WScript.Echo "Shortcut created on Desktop, pointing at:" & vbCrLf & strLauncher
