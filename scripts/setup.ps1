if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env created from .env.example"
} else {
    Write-Host ".env already exists"
}

Write-Host "Next step: open .env and set TELEGRAM_BOT_TOKEN plus your LLM key."
