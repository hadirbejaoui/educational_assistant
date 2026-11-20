<#
Restauration d'une sauvegarde produite par backup.ps1.

Usage :
    .\scripts\restore.ps1 -Dump .\backups\db_20261121_0300.dump [-Media .\backups\media_20261121_0300.zip]

ATTENTION : --clean supprime puis recrée les objets de la base cible. À utiliser sur
une base de test, ou après avoir vérifié que la sauvegarde est la bonne.
L'extension pgvector doit être installée sur le serveur PostgreSQL cible.
#>
param(
    [Parameter(Mandatory = $true)][string]$Dump,
    [string]$Media = ""
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

$config = @{}
Get-Content (Join-Path $root ".env") | Where-Object { $_ -match "^\s*([A-Z_]+)\s*=\s*(.*)$" } | ForEach-Object {
    $config[$Matches[1]] = $Matches[2].Trim()
}
$dbHost = if ($config["DB_HOST"]) { $config["DB_HOST"] } else { "localhost" }
$dbPort = if ($config["DB_PORT"]) { $config["DB_PORT"] } else { "5432" }

$pgRestore = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_restore.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
if ($null -eq $pgRestore) { throw "pg_restore introuvable." }

$env:PGPASSWORD = $config["DB_PASSWORD"]
try {
    & $pgRestore.FullName --clean --if-exists --no-owner --host=$dbHost --port=$dbPort --username=$($config["DB_USER"]) --dbname=$($config["DB_NAME"]) $Dump
    if ($LASTEXITCODE -ne 0) { throw "pg_restore a échoué (code $LASTEXITCODE)." }
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
Write-Output "Base restaurée depuis $Dump"

if ($Media) {
    Expand-Archive -Path $Media -DestinationPath (Join-Path $root "media") -Force
    Write-Output "Fichiers restaurés depuis $Media"
}
