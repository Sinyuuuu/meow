$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到專案虛擬環境：$python"
}

$secureKey = Read-Host "輸入與 ESP32 secrets.h 相同的測試裝置金鑰" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw "裝置金鑰不可空白"
    }
    $env:MEOW_DEVICE_KEY = $plainKey
    if ([string]::IsNullOrWhiteSpace($env:MEOW_DEVICE_UID)) {
        $env:MEOW_DEVICE_UID = "ESP32-SIM-A01"
    }
    Set-Location -LiteralPath $projectRoot
    & $python "scripts\start_esp32_isolated_server.py" --host "0.0.0.0" --port 8765
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:MEOW_DEVICE_KEY -ErrorAction SilentlyContinue
    $plainKey = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}

