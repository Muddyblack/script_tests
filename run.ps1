$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

$Python = Join-Path $ScriptDir "venv\Scripts\pythonw.exe"

$Script = Join-Path $ScriptDir "nexus_app.py"

& $Python $Script