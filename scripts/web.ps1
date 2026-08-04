# Sobe o GM Locacoes para acesso pela REDE LOCAL (celular, tablet, outro PC).
#
#   .\scripts\web.ps1
#
# Uma porta so: a propria API serve a interface compilada. Sem Vite, sem CORS, sem
# segundo servidor -- e o mesmo arranjo do app empacotado.
#
# ---------------------------------------------------------------------------
# LEIA ANTES DE USAR COM DADO REAL
#
# 1. E HTTP, nao HTTPS. Senha e token trafegam em TEXTO CLARO no Wi-Fi. Quem
#    estiver na mesma rede e souber capturar pacotes le tudo -- inclusive CPF e
#    CNH dos motoristas. Para uso de verdade fora da sua rede, isto precisa de
#    HTTPS (certificado + proxy reverso) ou de um tunel (Tailscale, WireGuard).
#
# 2. Qualquer aparelho no mesmo Wi-Fi alcanca o sistema. A senha e a unica
#    barreira. Rede de casa: aceitavel para testar. Wi-Fi de cafe, aeroporto ou
#    coworking: NAO use.
#
# 3. O BANCO continua so em localhost, e isto nao muda aqui. O Postgres roda com
#    -A trust (sem senha) porque so o backend desta maquina fala com ele. Expor
#    a porta 5434 na rede seria dar o banco inteiro sem pedir senha.
# ---------------------------------------------------------------------------

param(
    [int]$Porta = 8010,
    [switch]$SemCompilar
)

# stderr de programa externo vira erro fatal no PowerShell 5.1 com Stop -- e o
# alembic e o npm escrevem INFO no stderr. Conferimos codigo de saida.
$ErrorActionPreference = "Continue"

$RAIZ = Split-Path -Parent $PSScriptRoot
$PYTHON = Join-Path $RAIZ "backend\.venv\Scripts\python.exe"
$PG = Join-Path $RAIZ "desktop\vendor\pgsql\bin"

function Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Path $PYTHON)) {
    Write-Host "ERRO: ambiente Python nao encontrado em backend\.venv." -ForegroundColor Red
    exit 1
}

# O banco precisa estar de pe. Ele NAO e exposto: continua so em localhost.
$bancoOk = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $bancoOk) {
    Write-Host "Subindo o banco (so em localhost)..."
    & "$PG\pg_ctl.exe" -D "$env:LOCALAPPDATA\GM Locacoes\pgdata" `
        -l "$env:LOCALAPPDATA\GM Locacoes\pgdata\postgres.log" `
        -o "-p 5434 -c listen_addresses=localhost" -w -t 60 start > $null 2>&1
    $bancoOk = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet -WarningAction SilentlyContinue
    if (-not $bancoOk) {
        Write-Host "ERRO: o banco nao subiu." -ForegroundColor Red
        exit 1
    }
}

# A interface compilada, servida pela propria API. Sem isto a API responde JSON
# e o celular ve uma tela em branco.
$static = Join-Path $RAIZ "backend\static"
if (-not $SemCompilar) {
    Write-Host "Compilando a interface..."
    Push-Location (Join-Path $RAIZ "frontend")
    npm run build
    $falhou = $LASTEXITCODE -ne 0
    Pop-Location
    if ($falhou) { Write-Host "ERRO: a compilacao falhou." -ForegroundColor Red; exit 1 }
    if (Test-Path $static) { Remove-Item $static -Recurse -Force }
    Copy-Item (Join-Path $RAIZ "frontend\dist") $static -Recurse
}
if (-not (Test-Path (Join-Path $static "index.html"))) {
    Write-Host "ERRO: backend\static nao existe. Rode sem -SemCompilar." -ForegroundColor Red
    exit 1
}

# O Windows bloqueia conexao de fora por padrao. Sem esta regra o celular so da
# timeout, sem mensagem nenhuma -- e o erro parece do app.
$nomeRegra = "GM Locacoes (porta $Porta)"
if (-not (Get-NetFirewallRule -DisplayName $nomeRegra -ErrorAction SilentlyContinue)) {
    if (Admin) {
        New-NetFirewallRule -DisplayName $nomeRegra -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $Porta -Profile Private | Out-Null
        Write-Host "Regra de firewall criada (perfil Privado apenas)."
    } else {
        Write-Host ""
        Write-Host "ATENCAO: sem regra de firewall, o celular nao conecta." -ForegroundColor Yellow
        Write-Host "Rode UMA VEZ num PowerShell como Administrador:" -ForegroundColor Yellow
        Write-Host "  New-NetFirewallRule -DisplayName '$nomeRegra' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Porta -Profile Private"
        Write-Host ""
    }
}

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host " GM LOCACOES NA REDE LOCAL" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Nesta maquina : http://localhost:$Porta"
foreach ($ip in $ips) {
    Write-Host "   No celular    : http://${ip}:$Porta" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "   O celular precisa estar no MESMO Wi-Fi."
Write-Host "   E HTTP: a senha trafega em texto claro. Nao use em rede publica." -ForegroundColor Yellow
Write-Host "   O banco continua fechado (so localhost)."
Write-Host ""
Write-Host "   Ctrl+C encerra."
Write-Host ""

# --host 0.0.0.0: aceita conexao de qualquer interface, e o que permite o celular
# chegar. O banco NAO acompanha -- continua preso em localhost.
Push-Location (Join-Path $RAIZ "backend")
$env:CORS_ORIGINS = (($ips | ForEach-Object { "http://${_}:$Porta" }) + "http://localhost:$Porta") -join ","

# ---------------------------------------------------------------------------
# O SEGREDO DE ASSINATURA DO JWT. NAO REMOVA ESTE BLOCO.
#
# O padrao do config.py (`dev-secret-troque-em-producao`) esta escrito no
# codigo-fonte, e este repositorio e PUBLICO. As duas defesas que existem nao
# alcancam este script: o sorteio por instalacao so acontece com o app
# empacotado (paths.IS_FROZEN), e o boot so recusa o segredo padrao fora de
# ENV=dev. Rodando do fonte, com ENV=dev, as duas ficavam desarmadas -- e este
# e justamente o unico script que abre a porta para a REDE.
#
# O estrago nao era "senha em texto claro no Wi-Fi": era pior. Sem precisar de
# senha nenhuma, qualquer aparelho da rede assinava um token de admin com um
# segredo que qualquer um le no GitHub, e baixava CNH, CPF e contrato assinado
# pelo GET /files/{id}/download.
#
# Aqui usamos o segredo sorteado UMA vez por instalacao e guardado em
# %LOCALAPPDATA%\GM Locacoes\secret.key -- o mesmo do app instalado. E ENV=lan
# faz o proprio config.py exigir isso: se estas linhas sumirem, o servidor
# RECUSA subir em vez de subir inseguro.
$env:ENV = "lan"
$env:SECRET_KEY = (& $PYTHON -c "from app.core import paths; print(paths.installation_secret())")
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($env:SECRET_KEY)) {
    Write-Host "ERRO: nao consegui ler a chave de assinatura desta instalacao." -ForegroundColor Red
    Write-Host "Sem ela, qualquer aparelho da rede forjaria um login de administrador." -ForegroundColor Red
    Pop-Location
    exit 1
}
# ---------------------------------------------------------------------------

& $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port $Porta
Pop-Location
