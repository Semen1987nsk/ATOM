<#
.SYNOPSIS
    Build PEM bundle: certifi + Russian Trusted Root CA (Минцифры).

.DESCRIPTION
    После санкций 2022 года T-Bank Invest API (invest-public-api.tbank.ru) перешёл
    на TLS-сертификат, подписанный Russian Trusted Root CA от Минцифры. Этой CA нет
    в стандартном Mozilla bundle (certifi). grpcio (BoringSSL stack) не использует
    Windows trust store, поэтому без явного PEM-файла TLS handshake падает с:
        CERTIFICATE_VERIFY_FAILED: self signed certificate in certificate chain

    Этот скрипт собирает один объединённый PEM:
      certifi (Mozilla bundle) + Russian Trusted Root + Russian Trusted Sub.

    Затем установить env-переменную:
        TINKOFF_GRPC_CA_BUNDLE=<output_path>
    (backend/config.py транслирует её в GRPC_DEFAULT_SSL_ROOTS_FILE_PATH до import grpc).

.PARAMETER OutputPath
    Куда писать PEM. Default: backend\.local\combined_ca_bundle.pem (gitignored).

.EXAMPLE
    pwsh scripts\build_grpc_ca_bundle.ps1
    # → backend\.local\combined_ca_bundle.pem (~290 KB, ~70 root CAs + 2 RU)

.NOTES
    Russian CAs скачиваются с https://gu-st.ru — официального сайта Минцифры
    (https://www.gosuslugi.ru/crt). Подписи проверяются Windows X509Certificate2.
#>

[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path $PSScriptRoot "..\backend\.local\combined_ca_bundle.pem")
)

$ErrorActionPreference = "Stop"

$root_url = "https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer"
$sub_url  = "https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer"

$out_dir = Split-Path $OutputPath
New-Item -ItemType Directory -Force -Path $out_dir | Out-Null

Write-Host "[1/3] Locating certifi PEM..."
$certifi_path = python -c "import certifi; print(certifi.where())"
if (-not $certifi_path -or -not (Test-Path $certifi_path)) {
    throw "certifi not installed or path invalid. Run: pip install certifi"
}
Write-Host "      $certifi_path"

Write-Host "[2/3] Downloading Russian Trusted CAs from gu-st.ru..."
$r1 = Invoke-WebRequest -Uri $root_url -UseBasicParsing -TimeoutSec 30
$r2 = Invoke-WebRequest -Uri $sub_url  -UseBasicParsing -TimeoutSec 30

$cert1 = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($r1.Content)
$cert2 = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($r2.Content)
Write-Host "      Root: $($cert1.Subject)  (valid until $($cert1.NotAfter))"
Write-Host "      Sub:  $($cert2.Subject)  (valid until $($cert2.NotAfter))"

$russian_pem = @"
-----BEGIN CERTIFICATE-----
$([Convert]::ToBase64String($cert1.RawData, 'InsertLineBreaks'))
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
$([Convert]::ToBase64String($cert2.RawData, 'InsertLineBreaks'))
-----END CERTIFICATE-----
"@

Write-Host "[3/3] Writing combined bundle..."
$combined = (Get-Content $certifi_path -Raw) + "`n" + $russian_pem
Set-Content -Path $OutputPath -Value $combined -Encoding ASCII

$size_kb = ([System.Math]::Round((Get-Item $OutputPath).Length / 1KB, 1))
Write-Host ""
Write-Host "OK -> $OutputPath ($size_kb KB)"
Write-Host ""
Write-Host "Set env-var before starting backend:"
Write-Host "    `$env:TINKOFF_GRPC_CA_BUNDLE = '$OutputPath'"
Write-Host "OR put in .env.local:"
Write-Host "    TINKOFF_GRPC_CA_BUNDLE=$OutputPath"
