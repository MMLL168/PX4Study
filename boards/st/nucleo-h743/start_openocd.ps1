# Nucleo-H743 OpenOCD GDB Server Launcher
# 在 Windows 執行此腳本，啟動 GDB Server，然後在 VS Code 按 F5 開始除錯
# 需要已安裝 STM32CubeIDE（自動搜尋路徑）

# 搜尋 openocd.exe
$searchRoots = @("C:\ST\", "C:\Program Files\ST\", "C:\Program Files (x86)\ST\")
$ocd = $null
foreach ($root in $searchRoots) {
    if (Test-Path $root) {
        $ocd = (Get-ChildItem $root -Recurse -Filter "openocd.exe" -ErrorAction SilentlyContinue |
                Select-Object -First 1).FullName
        if ($ocd) { break }
    }
}

if (-not $ocd) {
    Write-Error "找不到 openocd.exe，請確認 STM32CubeIDE 已安裝"
    exit 1
}

# 搜尋 st_scripts（stlink-dap.cfg 所在的上層目錄）
$stlinkCfg = (Get-ChildItem "C:\ST\" -Recurse -Filter "stlink-dap.cfg" -ErrorAction SilentlyContinue |
              Select-Object -First 1).FullName
$st_scripts = Split-Path (Split-Path $stlinkCfg -Parent) -Parent

if (-not (Test-Path $st_scripts)) {
    Write-Error "找不到 st_scripts 目錄"
    exit 1
}

# 防火牆：確保 port 3333 已開放（只需第一次，之後會跳過）
$rule = Get-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -ErrorAction SilentlyContinue
if (-not $rule) {
    Write-Host "新增防火牆規則 port 3333..." -ForegroundColor Yellow
    New-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -Direction Inbound `
        -Protocol TCP -LocalPort 3333 -Action Allow | Out-Null
    Write-Host "防火牆規則已新增" -ForegroundColor Green
}

Write-Host ""
Write-Host "OpenOCD : $ocd" -ForegroundColor Cyan
Write-Host "Scripts : $st_scripts" -ForegroundColor Cyan
Write-Host ""
Write-Host "GDB Server 啟動中，等待 VS Code 連線（port 3333）..." -ForegroundColor Green
Write-Host "保持此視窗開啟，在 VS Code 選 [openocd-win (st_nucleo-h743)] 後按 F5" -ForegroundColor Yellow
Write-Host ""

& $ocd -s $st_scripts -f interface/stlink-dap.cfg -c "set AP_NUM 0" -f target/stm32h7x.cfg -c "reset_config srst_only srst_nogate"
