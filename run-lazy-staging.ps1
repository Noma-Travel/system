# Launcher de DEV: liga NOMA_WEB_LAZY_TRIP=on para um run de STAGING e delega
# ao run.ps1. É o override "de sessão" (o único que sobrevive à regeneração do
# env_config.py / env.development — o main.py do backend preserva o os.environ).
#
# Uso (mesmos tokens do run.ps1; env:staging é injetado se você não passar env):
#   .\run-lazy-staging.ps1 noma console backend
#   .\run-lazy-staging.ps1 backend env:staging handler:local
#
# SEGURANÇA: recusa ligar a flag contra produção — a criação lazy de trips não
# deve ser validada em prod antes do e2e de staging.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
# NÃO usar "Stop": run.py escreve o banner/logs no stderr, e sob captura de
# stderr o PowerShell 5.1 embrulha cada linha como NativeCommandError — com
# "Stop" isso mataria o launch antes do generate(). O guard abaixo usa exit
# explícito, então não depende de "Stop".
$ErrorActionPreference = "Continue"

if ($Args -contains 'env:prod') {
    Write-Error "Recusando: NOMA_WEB_LAZY_TRIP nao deve ser ligado com env:prod. Rode o e2e em env:staging."
    exit 1
}

# Default para staging quando nenhum token env: foi passado.
if (-not ($Args | Where-Object { $_ -like 'env:*' })) {
    $Args = @($Args) + 'env:staging'
}

# O fetch do Secrets Manager (noma_env/secrets.py) usa AWS_PROFILE ou cai no
# profile "noma" — que NÃO tem secretsmanager:GetSecretValue em noma/env/staging.
# Forçar joao-noma (que tem acesso) evita o "Missing required vars" + backend exit 1.
if (-not $env:AWS_PROFILE) { $env:AWS_PROFILE = "joao-noma" }

# DOIS flags precisam concordar (senao o historico do chat racha entre a key do
# trip e a key do thread — pior cenario do contrato):
#  - backend:  NOMA_WEB_LAZY_TRIP           (agent_react/handlers)
#  - frontend: NEXT_PUBLIC_NOMA_WEB_LAZY_TRIP (next dev inlina do process.env;
#              o run.py spawna o npm run dev herdando este ambiente)
$env:NOMA_WEB_LAZY_TRIP = "on"
$env:NEXT_PUBLIC_NOMA_WEB_LAZY_TRIP = "on"
Write-Host "[lazy] NOMA_WEB_LAZY_TRIP=on + NEXT_PUBLIC_NOMA_WEB_LAZY_TRIP=on (sessao atual)."
Write-Host "[lazy] Lancando: run.ps1 $($Args -join ' ')"

& (Join-Path $PSScriptRoot 'run.ps1') @Args
