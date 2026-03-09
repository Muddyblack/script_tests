Dim fso, shell, scriptFolder, batchPath

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
batchPath = fso.BuildPath(scriptFolder, "schedule.bat")

shell.Run "cmd /c """ & batchPath & """", 0, False

set shell = nothing
set fso = nothing

WScript.Quit