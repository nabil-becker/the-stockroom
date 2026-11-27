# Windows equivalent of stage-features.sh.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
Remove-Item -Recurse -Force .devcontainer/features -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force .devcontainer/features | Out-Null
$n = 0
foreach ($d in Get-ChildItem src -Directory) {
    if (-not (Test-Path (Join-Path $d.FullName 'devcontainer-feature.json'))) {
        Write-Warning "not staged: $($d.FullName) has no devcontainer-feature.json (a leftover directory? remove it)"
        continue
    }
    Copy-Item -Recurse $d.FullName (Join-Path .devcontainer/features $d.Name)
    $n++
}
Write-Output "staged $n Features into .devcontainer/features"
