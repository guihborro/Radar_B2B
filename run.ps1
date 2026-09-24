# Atalho para rodar a CLI do Outreach sem depender do PATH.
# Uso:  .\run.ps1 preview --n 3
#       .\run.ps1 rodar --alvo 50
#       .\run.ps1 auditar
#       .\run.ps1 html --n 1
#       .\run.ps1 status
param([Parameter(ValueFromRemainingArguments = $true)] $Args)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

# acha o python.exe real (ignora o stub da Microsoft Store)
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) {
    $py = (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
           Select-Object -First 1).FullName
}
if (-not $py -or -not (Test-Path $py)) {
    Write-Error "Python nao encontrado. Instale com: winget install Python.Python.3.12"
    exit 1
}

Set-Location $PSScriptRoot
& $py -m finintegra.cli @Args
exit $LASTEXITCODE
