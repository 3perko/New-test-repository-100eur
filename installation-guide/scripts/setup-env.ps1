# Vytvorí súbor .env v koreni repozitára z .env.example a vygeneruje bezpečné tajné hodnoty (Windows PowerShell).
# Nikdy neprepíše existujúci .env (iba s -Force).
#
# Použitie:  powershell -ExecutionPolicy Bypass -File .\installation-guide\scripts\setup-env.ps1 -AdminEmail ja@firma.sk
# Voliteľne: -AdminPassword HESLO -AdminName "Meno" -Port 8000 -BaseUrl URL -AnthropicKey KEY
#            -GoogleId ID -GoogleSecret SECRET -Domain DOMENA -TunnelToken TOKEN -Force
param(
  [string]$AdminEmail = "",
  [string]$AdminPassword = "",
  [string]$AdminName = "Administrátor",
  [string]$Port = "8000",
  [string]$BaseUrl = "",
  [string]$AnthropicKey = "",
  [string]$GoogleId = "",
  [string]$GoogleSecret = "",
  [string]$Domain = "",
  [string]$TunnelToken = "",
  [switch]$Force
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EnvFile = Join-Path $Root ".env"
$Example = Join-Path $Root ".env.example"

if (-not (Test-Path $Example)) { throw "Chýba $Example – spúšťate skript z klonu repozitára?" }
if ((Test-Path $EnvFile) -and -not $Force) { Write-Host "OK: $EnvFile už existuje – nič nemením (na prepísanie -Force)."; exit 0 }

function New-Hex([int]$bytes) {
  $b = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  -join ($b | ForEach-Object { $_.ToString("x2") })
}

if (-not $AdminEmail) { $AdminEmail = Read-Host "E-mail administrátora (prihlasovacie meno)" }
if (-not $AdminEmail) { $AdminEmail = "admin@example.com" }
$Generated = $false
if (-not $AdminPassword) { $AdminPassword = New-Hex 9; $Generated = $true }
if ($AdminPassword.Length -lt 8) { throw "Heslo administrátora musí mať aspoň 8 znakov." }
if (-not $BaseUrl) { $BaseUrl = "http://localhost:" + ($Port -split ":")[-1] }

$Values = @{
  "SECRET_KEY" = (New-Hex 32); "POSTGRES_PASSWORD" = (New-Hex 16); "ADMIN_EMAIL" = $AdminEmail
  "ADMIN_PASSWORD" = $AdminPassword; "ADMIN_NAME" = $AdminName; "APP_PORT" = $Port; "APP_BASE_URL" = $BaseUrl
}
if ($AnthropicKey) { $Values["ANTHROPIC_API_KEY"] = $AnthropicKey }
if ($GoogleId) { $Values["GOOGLE_CLIENT_ID"] = $GoogleId }
if ($GoogleSecret) { $Values["GOOGLE_CLIENT_SECRET"] = $GoogleSecret }
if ($Domain) { $Values["DOMAIN"] = $Domain }
if ($TunnelToken) { $Values["TUNNEL_TOKEN"] = $TunnelToken }
if ($BaseUrl.StartsWith("https://")) { $Values["COOKIE_SECURE"] = "true" }

$out = foreach ($line in Get-Content -Encoding UTF8 $Example) {
  if ($line -match '^([A-Z_]+)=' -and $Values.ContainsKey($Matches[1])) { "$($Matches[1])=$($Values[$Matches[1]])" } else { $line }
}
# UTF-8 bez BOM a s LF, aby súbor čítal Docker Compose rovnako ako na Linuxe
[System.IO.File]::WriteAllText($EnvFile, (($out -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))

Write-Host "OK: vytvorený $EnvFile"
Write-Host "    prihlásenie:  $AdminEmail"
if ($Generated) { Write-Host "    heslo:        $AdminPassword   (vygenerované – zapíšte si ho)" }
Write-Host "    adresa:       $BaseUrl"
Write-Host "Ďalší krok: docker compose up -d --build"
