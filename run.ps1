$Python = Join-Path -Path $ScriptDir "venv\Scripts\pythonw.exe"

$Script = Join-Path $ScriptDir "nexus_app.py"

& $Python $Script