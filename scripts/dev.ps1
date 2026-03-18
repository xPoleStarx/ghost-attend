param(
    [string]$Command = "help"
)

$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { "docker-compose.dev.yml" }
$ComposeArgs = @("compose", "-f", $ComposeFile)

function Show-Usage {
    Write-Host "GhostAttend dev helper"
    Write-Host ""
    Write-Host "Kullanim:"
    Write-Host "  .\scripts\dev.ps1 up"
    Write-Host "  .\scripts\dev.ps1 rebuild"
    Write-Host "  .\scripts\dev.ps1 down"
    Write-Host "  .\scripts\dev.ps1 logs"
    Write-Host "  .\scripts\dev.ps1 ps"
    Write-Host "  .\scripts\dev.ps1 migrate"
    Write-Host "  .\scripts\dev.ps1 test"
    Write-Host "  .\scripts\dev.ps1 reset"
    Write-Host "  .\scripts\dev.ps1 help"
}

switch ($Command) {
    "up" { docker @ComposeArgs up -d }
    "rebuild" { docker @ComposeArgs up -d --build --force-recreate bot worker scheduler }
    "down" { docker @ComposeArgs down }
    "logs" { docker @ComposeArgs logs -f bot worker scheduler }
    "ps" { docker @ComposeArgs ps }
    "migrate" { docker @ComposeArgs run --rm bot alembic upgrade head }
    "test" { docker @ComposeArgs run --rm bot python -m pytest tests/unit tests/integration -v }
    "reset" { docker @ComposeArgs down -v }
    "help" { Show-Usage }
    default {
        Write-Error "Bilinmeyen komut: $Command"
        Show-Usage
        exit 1
    }
}
