param([Parameter(Mandatory=$true)][string]$Config, [string]$OutputDir)
$ErrorActionPreference = 'Stop'
$taskConfigPath = (Resolve-Path -LiteralPath $Config).Path
$taskConfig = Get-Content -LiteralPath $taskConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$taskBase = Split-Path -Parent $taskConfigPath
$taskPython = $taskConfig.runtime.python_monitor
if (-not [IO.Path]::IsPathRooted($taskPython)) { $taskPython = Join-Path $taskBase $taskPython }
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Configured monitor Python is missing; inspect runtime paths.' }
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$taskArgs = @((Join-Path $PSScriptRoot 'scripts\run_guard.py'), '--config', $taskConfigPath)
if ($OutputDir) { $taskArgs += @('--output', $OutputDir) }
& $taskPython @taskArgs
if ($LASTEXITCODE -ne 0) { throw 'Toolkit stopped. Inspect its new logs and output; no synthetic substitution.' }
