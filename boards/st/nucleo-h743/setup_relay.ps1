# OpenOCD Relay 安裝腳本
# 在 Windows PowerShell（管理員）執行一次即可
# 功能：將 relay 服務安裝到 WSL2 Ubuntu，並設定開機自動啟動

param(
    [string]$WslDistro = "Ubuntu",
    [switch]$Uninstall
)

$relayScript = @'
#!/usr/bin/env python3
import socket, subprocess, threading, time, sys

RELAY_PORT = 9998
OPENOCD_PORT = 3333
POWERSHELL_CMD = r"""
$searchRoots = @('C:\ST\', 'C:\Program Files\ST\', 'C:\Program Files (x86)\ST\')
$ocd = $null
foreach ($root in $searchRoots) {
    if (Test-Path $root) {
        $ocd = (Get-ChildItem $root -Recurse -Filter 'openocd.exe' -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
        if ($ocd) { break }
    }
}
if (-not $ocd) { exit 1 }
$stlink = (Get-ChildItem 'C:\ST\' -Recurse -Filter 'stlink-dap.cfg' -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
$scripts = Split-Path (Split-Path $stlink -Parent) -Parent
$rule = Get-NetFirewallRule -DisplayName 'OpenOCD GDB 3333' -ErrorAction SilentlyContinue
if (-not $rule) { New-NetFirewallRule -DisplayName 'OpenOCD GDB 3333' -Direction Inbound -Protocol TCP -LocalPort 3333 -Action Allow | Out-Null }
& $ocd -s $scripts -f interface/stlink-dap.cfg -c 'set AP_NUM 0' -f target/stm32h7x.cfg
"""
_lock = threading.Lock()
_running = False

def is_ocd():
    try:
        s = socket.create_connection(('127.0.0.1', OPENOCD_PORT), timeout=1)
        s.close(); return True
    except: return False

def launch():
    global _running
    with _lock:
        if is_ocd() or _running: return
        _running = True
    subprocess.Popen(['powershell.exe', '-ExecutionPolicy', 'Bypass', '-Command', POWERSHELL_CMD],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def reset():
        global _running
        for _ in range(30):
            time.sleep(1)
            if is_ocd(): break
        _running = False
    threading.Thread(target=reset, daemon=True).start()

server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try: server.bind(('0.0.0.0', RELAY_PORT))
except OSError as e: print(f"Cannot bind {RELAY_PORT}: {e}"); sys.exit(1)
server.listen(5)
print(f"OpenOCD Relay on port {RELAY_PORT}")
while True:
    try:
        conn, addr = server.accept(); conn.close()
        threading.Thread(target=launch, daemon=True).start()
    except KeyboardInterrupt: break
'@

if ($Uninstall) {
    Write-Host "移除 OpenOCD Relay..." -ForegroundColor Yellow
    wsl -d $WslDistro -- bash -c "pkill -f openocd_relay_min.py; rm -f ~/.openocd_relay_min.py; sed -i '/openocd_relay/d' ~/.bashrc"
    Write-Host "已移除" -ForegroundColor Green
    exit 0
}

Write-Host "安裝 OpenOCD Relay 到 WSL2 ($WslDistro)..." -ForegroundColor Cyan

# 寫入 relay 腳本到 WSL2 home 目錄
$relayScript | wsl -d $WslDistro -- bash -c "cat > ~/.openocd_relay_min.py"

# 加入 .bashrc 自動啟動（避免重複）
$bashrcEntry = 'if ! pgrep -f openocd_relay_min.py > /dev/null 2>&1; then nohup python3 ~/.openocd_relay_min.py > /tmp/openocd_relay.log 2>&1 & fi'
wsl -d $WslDistro -- bash -c "grep -qF 'openocd_relay_min' ~/.bashrc || echo '$bashrcEntry' >> ~/.bashrc"

# 立即啟動
Write-Host "啟動 Relay 服務..." -ForegroundColor Yellow
wsl -d $WslDistro -- bash -c "pkill -f openocd_relay_min.py 2>/dev/null; sleep 1; nohup python3 ~/.openocd_relay_min.py > /tmp/openocd_relay.log 2>&1 &"

Start-Sleep -Seconds 2

# 確認是否啟動
$check = wsl -d $WslDistro -- bash -c "pgrep -f openocd_relay_min.py && echo OK || echo FAIL"
if ($check -match "OK") {
    Write-Host ""
    Write-Host "Relay 安裝完成！" -ForegroundColor Green
    Write-Host "之後只要開啟 WSL2（或重開機後第一次開 WSL2 Terminal），Relay 就會自動在背景執行。" -ForegroundColor Green
    Write-Host "VS Code 按 F5 即可全自動除錯。" -ForegroundColor Green
} else {
    Write-Host "Relay 啟動失敗，請檢查 WSL2 Ubuntu 是否正常" -ForegroundColor Red
}
