param([int]$Port = 5000, [ValidateSet('actuated','dqn','fixed_time')][string]$Controller = 'dqn')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$trafficPython = Join-Path $PSScriptRoot 'venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $trafficPython)) {
    throw 'Project venv is missing. Create it and install requirements.txt first.'
}
$trafficModel = 'models/dqn_approach_v3.zip'
if (Test-Path -LiteralPath 'models/dqn_approach_best.zip') { $trafficModel = 'models/dqn_approach_best.zip' }
Write-Host "Traffic simulation: http://127.0.0.1:$Port"
& $trafficPython dashboard/app.py --port $Port --controller $Controller --model $trafficModel
