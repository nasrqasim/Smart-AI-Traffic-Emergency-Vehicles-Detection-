param([int]$Timesteps = 100000, [int]$EpisodeSeconds = 1800)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$trafficPython = Join-Path $PSScriptRoot 'venv/Scripts/python.exe'
$env:TRAFFIC_USE_LIBSUMO = '1'
& $trafficPython -u train.py --timesteps $Timesteps --episode-seconds $EpisodeSeconds --randomize-routes --out models/dqn_approach_v3.zip --save-freq 5000
