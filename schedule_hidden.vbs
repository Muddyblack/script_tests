Dim fso, shell, scriptFolder, batchPath

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)

pythonExe = scriptFolder & "\venv\Scripts\pythonw.exe"
pythonScript = scriptFolder & "\nexus_app.py"

shell.Run """" & pythonExe & """ """ & pythonScript & """", 0, False

set shell = nothing
set fso = nothing

WScript.Quit