<#
Sauvegarde de l'assistant pédagogique : base PostgreSQL + fichiers importés.

Usage (PowerShell, depuis la racine du projet) :
    .\scripts\backup.ps1                      # sauvegarde dans .\backups\
    .\scripts\backup.ps1 -Destination D:\sauvegardes -Keep 14

Produit, horodatés :
    db_AAAAMMJJ_HHMM.dump   format personnalisé de pg_dump (compressé, restaurable avec pg_restore)
    media_AAAAMMJJ_HHMM.zip copie des PDF et TXT importés (dossier media\)
Les sauvegardes les plus anciennes au-delà de -Keep sont supprimées.

Le mot de passe est lu dans .env (DB_PASSWORD) et transmis à pg_dump par la
variable PGPASSWORD, le temps de la commande uniquement : il n'apparaît pas
dans la ligne de commande.
#>
param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\backups"),
    [int]$Keep = 7
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

# Lecture de .env (lignes CLE=valeur)
$config = @{}
Get-Content (Join-Path $root ".env") | Where-Object { $_ -match "^\s*([A-Z_]+)\s*=\s*(.*)$" } | ForEach-Object {
    $config[$Matches[1]] = $Matches[2].Trim()
}
$dbHost = if ($config["DB_HOST"]) { $config["DB_HOST"] } else { "localhost" }
$dbPort = if ($config["DB_PORT"]) { $config["DB_PORT"] } else { "5432" }

$pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
if ($null -eq $pgDump) {
    $candidate = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($null -eq $candidate) { throw "pg_dump introuvable : ajoutez le dossier bin de PostgreSQL au PATH." }
    $pgDumpPath = $candidate.FullName
} else {
    $pgDumpPath = $pgDump.Source
}

New-Item -ItemType Directory -Force $Destination | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$dumpFile = Join-Path $Destination "db_$stamp.dump"
$mediaFile = Join-Path $Destination "media_$stamp.zip"

$env:PGPASSWORD = $config["DB_PASSWORD"]
try {
    & $pgDumpPath --format=custom --no-owner --host=$dbHost --port=$dbPort --username=$($config["DB_USER"]) --file=$dumpFile $config["DB_NAME"]
    if ($LASTEXITCODE -ne 0) { throw "pg_dump a échoué (code $LASTEXITCODE)." }
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
Write-Output "Base sauvegardée : $dumpFile"

$media = Join-Path $root "media"
if (Test-Path $media) {
    Compress-Archive -Path (Join-Path $media "*") -DestinationPath $mediaFile -Force
    Write-Output "Fichiers sauvegardés : $mediaFile"
}

# Rotation : on garde les $Keep sauvegardes les plus récentes de chaque type
foreach ($pattern in @("db_*.dump", "media_*.zip")) {
    Get-ChildItem $Destination -Filter $pattern | Sort-Object Name -Descending | Select-Object -Skip $Keep | Remove-Item -Confirm:$false
}
