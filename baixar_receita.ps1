# Baixa e descompacta os dados abertos de CNPJ (espelho Casa dos Dados) em data/receita/.
#
# Uso:
#   .\baixar_receita.ps1                 # só Estabelecimentos0 (teste rápido)
#   .\baixar_receita.ps1 -Empresas       # + as 10 partes de Empresas (razão social/porte)
#   .\baixar_receita.ps1 -Empresas -Socios   # + Sócios (nome do decisor)
#   .\baixar_receita.ps1 -Mes "2026-06-14"   # escolher outra pasta/mês
param(
    [string]$Mes = "2026-06-14",
    [switch]$Empresas,
    [switch]$Socios,
    [int]$Partes = 1            # quantas partes de Estabelecimentos baixar (0..9)
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # a barra do Invoke-WebRequest deixa o download MUITO lento
$base = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/$Mes"
$dest = Join-Path $PSScriptRoot "data\receita"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# curl.exe (nativo do Windows 11) é bem mais rápido que Invoke-WebRequest
$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source

function Baixar-E-Extrair($arquivo) {
    $url = "$base/$arquivo"
    $zip = Join-Path $dest $arquivo
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Write-Host "Baixando $arquivo ..." -ForegroundColor Cyan
    if ($curl) {
        & $curl -L --fail --retry 3 -o $zip $url     # mostra progresso real e rápido
        if ($LASTEXITCODE -ne 0) { throw "curl falhou ($LASTEXITCODE) em $arquivo" }
    } else {
        Invoke-WebRequest -Uri $url -OutFile $zip
    }
    Write-Host "Descompactando $arquivo ..." -ForegroundColor Cyan
    Expand-Archive -Path $zip -DestinationPath $dest -Force
    Remove-Item $zip -Force      # apaga o .zip, mantém só o CSV extraído
}

# Estabelecimentos (obrigatório)
for ($i = 0; $i -lt [Math]::Max(1, $Partes); $i++) { Baixar-E-Extrair "Estabelecimentos$i.zip" }

# Empresas (recomendado: razão social + porte) — 10 partes
if ($Empresas) { 0..9 | ForEach-Object { Baixar-E-Extrair "Empresas$_.zip" } }

# Socios (opcional: nome do decisor) — 10 partes
if ($Socios)   { 0..9 | ForEach-Object { Baixar-E-Extrair "Socios$_.zip" } }

Write-Host "`nPronto. Arquivos em: $dest" -ForegroundColor Green
Write-Host "Agora rode:  .\run.ps1 rodar --alvo 50" -ForegroundColor Green
