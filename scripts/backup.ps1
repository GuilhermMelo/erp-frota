# Backup do GM Locacoes: o banco E os arquivos, na mesma foto.
#
# POR QUE OS DOIS JUNTOS: o banco guarda só o CAMINHO do arquivo
# ("contracts/CTR000001/contrato.pdf"), nunca os bytes. Um backup só do banco
# restauraria um sistema que aponta para PDFs e fotos de CNH que não existem
# mais -- o dono veria "arquivo nao encontrado" em todo documento.
#
# Uso:
#   .\scripts\backup.ps1              faz o backup
#   .\scripts\backup.ps1 -Verificar   faz o backup e PROVA que ele restaura
#
# O -Verificar restaura a cópia num banco descartável (frota_backup_teste) e o
# derruba em seguida. O banco de trabalho nunca e tocado. Backup que nunca foi
# restaurado nao e backup: e esperanca.
#
# ATENCAO (LGPD): o arquivo gerado contem CPF, CNH e contratos. Ele nasce em
# %LOCALAPPDATA%, fora do repositorio. Nao mova para dentro do projeto e nao
# suba para nuvem publica sem criptografar.

param(
    [switch]$Verificar,
    [int]$Manter = 10
)

$ErrorActionPreference = "Stop"

$RAIZ = Split-Path -Parent $PSScriptRoot
$DADOS = Join-Path $env:LOCALAPPDATA "GM Locacoes"
$DESTINO = Join-Path $DADOS "backups"
$PORTA = 5434
$USUARIO = "frota"
$BANCO = "frota"

# Os binarios: em desenvolvimento vem de desktop\vendor; no app instalado, de resources.
$CANDIDATOS = @(
    (Join-Path $RAIZ "desktop\vendor\pgsql\bin"),
    (Join-Path ${env:ProgramFiles} "GM Locacoes\resources\pgsql\bin"),
    (Join-Path ${env:ProgramFiles} "GM Locações\resources\pgsql\bin")
)
$PG = $null
foreach ($c in $CANDIDATOS) {
    if (Test-Path (Join-Path $c "pg_dump.exe")) { $PG = $c; break }
}
if (-not $PG) {
    Write-Host "ERRO: pg_dump nao encontrado. Procurei em:" -ForegroundColor Red
    $CANDIDATOS | ForEach-Object { Write-Host "  $_" }
    exit 1
}

# O banco precisa estar de pe. Sem isto o pg_dump falha com erro de conexao cru.
$conectou = Test-NetConnection -ComputerName 127.0.0.1 -Port $PORTA -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $conectou) {
    Write-Host "ERRO: o banco nao esta rodando na porta $PORTA." -ForegroundColor Red
    Write-Host "Abra o GM Locacoes, ou suba o banco com:"
    Write-Host "  $PG\pg_ctl.exe -D `"$DADOS\pgdata`" -o `"-p $PORTA`" -w start"
    exit 1
}

New-Item -ItemType Directory -Force $DESTINO | Out-Null
$carimbo = Get-Date -Format "yyyy-MM-dd_HHmm"
$arqBanco = Join-Path $DESTINO "frota_$carimbo.dump"

Write-Host "Copiando o banco..."
# -Fc: formato comprimido do proprio Postgres, restauravel com pg_restore.
& "$PG\pg_dump.exe" -h 127.0.0.1 -p $PORTA -U $USUARIO -d $BANCO -Fc -f $arqBanco
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: o pg_dump falhou (codigo $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
$mbBanco = [math]::Round((Get-Item $arqBanco).Length / 1MB, 2)
Write-Host "  banco    -> $arqBanco  ($mbBanco MB)"

# Os arquivos enviados (fotos de vistoria, CNH, contratos assinados).
$storage = Join-Path $DADOS "storage"
$arqArquivos = Join-Path $DESTINO "storage_$carimbo.zip"
if ((Test-Path $storage) -and (Get-ChildItem $storage -Recurse -File -ErrorAction SilentlyContinue)) {
    Write-Host "Copiando os arquivos..."
    Compress-Archive -Path (Join-Path $storage "*") -DestinationPath $arqArquivos -Force
    $mbArq = [math]::Round((Get-Item $arqArquivos).Length / 1MB, 2)
    Write-Host "  arquivos -> $arqArquivos  ($mbArq MB)"
} else {
    Write-Host "  arquivos -> nada a copiar (storage vazio)"
}

if ($Verificar) {
    # Restaura num banco descartavel. Prova que o arquivo abre e que o schema
    # bate -- e a unica forma de saber que o backup serve para alguma coisa.
    $teste = "frota_backup_teste"
    Write-Host "Verificando a copia (restaurando em $teste)..."
    & "$PG\psql.exe" -h 127.0.0.1 -p $PORTA -U $USUARIO -d postgres -q -c "DROP DATABASE IF EXISTS $teste WITH (FORCE);" | Out-Null
    & "$PG\createdb.exe" -h 127.0.0.1 -p $PORTA -U $USUARIO $teste
    & "$PG\pg_restore.exe" -h 127.0.0.1 -p $PORTA -U $USUARIO -d $teste --no-owner $arqBanco 2>$null | Out-Null

    $consulta = "select (select count(*) from vehicles) || ' veiculos, ' || (select count(*) from drivers) || ' motoristas, ' || (select count(*) from revenues) || ' cobrancas'"
    $resumo = (& "$PG\psql.exe" -h 127.0.0.1 -p $PORTA -U $USUARIO -d $teste -t -A -c $consulta)
    & "$PG\psql.exe" -h 127.0.0.1 -p $PORTA -U $USUARIO -d postgres -q -c "DROP DATABASE IF EXISTS $teste WITH (FORCE);" | Out-Null

    if ($resumo) {
        Write-Host "  OK: a copia restaura e contem $resumo." -ForegroundColor Green
    } else {
        Write-Host "  ERRO: a copia nao restaurou. NAO confie neste backup." -ForegroundColor Red
        exit 1
    }
}

# Rotacao: guarda as N mais recentes de cada tipo. Sem isto a pasta cresce para sempre.
foreach ($padrao in @("frota_*.dump", "storage_*.zip")) {
    Get-ChildItem $DESTINO -Filter $padrao |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Manter |
        ForEach-Object {
            Write-Host "  removendo copia antiga: $($_.Name)"
            Remove-Item $_.FullName -Force
        }
}

Write-Host ""
Write-Host "Pronto. As copias estao em: $DESTINO" -ForegroundColor Green
Write-Host "Leve uma copia para FORA desta maquina (HD externo ou nuvem)." -ForegroundColor Yellow
Write-Host "Backup que mora no mesmo disco do original nao protege contra o disco morrer."
Write-Host ""
Write-Host "Para restaurar (APAGA o banco atual -- so faca sabendo disso):"
Write-Host "  $PG\psql.exe -h 127.0.0.1 -p $PORTA -U $USUARIO -d postgres -c `"DROP DATABASE $BANCO WITH (FORCE);`""
Write-Host "  $PG\createdb.exe -h 127.0.0.1 -p $PORTA -U $USUARIO $BANCO"
Write-Host "  $PG\pg_restore.exe -h 127.0.0.1 -p $PORTA -U $USUARIO -d $BANCO --no-owner <arquivo.dump>"
Write-Host "  e descompacte o storage_*.zip de volta em $DADOS\storage"
