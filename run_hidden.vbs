Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
' The .bat sits next to this script, wherever the folder was cloned
batPath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "start_screentime.bat")
WshShell.Run Chr(34) & batPath & Chr(34), 0
Set WshShell = Nothing
Set fso = Nothing
