# Geriye dönük uyumluluk — asıl betik: proje kökündeki Run.ps1
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $root "Run.ps1") -InstallOnly @args
