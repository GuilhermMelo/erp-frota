# Abre o ERP Frota nesta máquina: garante o banco de pé, sobe o backend e abre o navegador.
#
# Não deve ser executado direto — use o atalho "ERP Frota" (ou o ERP Frota.cmd na raiz).

# NÃO usar ErrorActionPreference = "Stop" aqui. O `docker info` escreve avisos inofensivos
# no stderr ("No blkio throttle support"), e o PowerShell 5.1 transforma stderr de programa
# externo em erro fatal — o script morreria com o Docker funcionando perfeitamente.
# Aqui se olha o código de saída, que é o que de fato diz se o comando deu certo.
$ErrorActionPreference = "Continue"

$RAIZ = Split-Path -Parent $PSScriptRoot
$EXE = Join-Path $RAIZ "backend\dist\erp-frota-api\erp-frota-api.exe"
$PORTA = 8010
$URL = "http://127.0.0.1:$PORTA"
$LOG = Join-Path $env:LOCALAPPDATA "ERP Frota\logs\backend.log"

function Escreva($texto) { Write-Host $texto }

function Docker-De-Pe {
    docker info > $null 2> $null
    return $LASTEXITCODE -eq 0
}

function Backend-Responde {
    try {
        $r = Invoke-WebRequest -Uri "$URL/health" -TimeoutSec 2 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

# Já está aberto? Só traz o navegador de volta — abrir o .exe duas vezes daria "porta em uso".
if (Backend-Responde) {
    Escreva "ERP ja esta rodando."
    Start-Process $URL
    exit 0
}

if (-not (Test-Path $EXE)) {
    Escreva "ERRO: o backend nao foi empacotado ainda."
    Escreva "Rode em backend/:  .\.venv\Scripts\python.exe -m PyInstaller erp-frota-api.spec --noconfirm"
    Read-Host "ENTER para fechar"
    exit 1
}

# 1. O banco. O container tem restart:unless-stopped, entao normalmente ja esta de pe --
#    mas se o Docker Desktop acabou de ligar, ele leva alguns segundos.
Escreva "Verificando o banco de dados..."
if (-not (Docker-De-Pe)) {
    Escreva "Docker nao esta rodando. Abrindo o Docker Desktop (demora ~30s na primeira vez)..."
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    foreach ($i in 1..60) {
        Start-Sleep -Seconds 2
        if (Docker-De-Pe) { break }
    }
    if (-not (Docker-De-Pe)) {
        Escreva "ERRO: o Docker nao subiu. Abra o Docker Desktop na mao e tente de novo."
        Read-Host "ENTER para fechar"
        exit 1
    }
}

Push-Location $RAIZ
docker compose up -d | Out-Null
Pop-Location

# 2. O backend. Ele roda as migracoes sozinho no boot e serve a interface na mesma porta.
Escreva "Subindo o sistema..."
Start-Process $EXE -WindowStyle Hidden

foreach ($i in 1..45) {
    if (Backend-Responde) {
        Escreva "Pronto. Abrindo $URL"
        Start-Process $URL
        exit 0
    }
    Start-Sleep -Seconds 1
}

# Sem console, o .exe nao tem onde reclamar. O log e a unica pista.
Escreva ""
Escreva "ERRO: o sistema nao respondeu em 45s."
Escreva "O que aconteceu esta no log: $LOG"
if (Test-Path $LOG) {
    Escreva ""
    Escreva "--- ultimas linhas ---"
    Get-Content $LOG -Tail 20
}
Read-Host "ENTER para fechar"
exit 1
