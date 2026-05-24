#!/usr/bin/env python3
"""
OpenOCD Relay Service - 在 WSL2 Ubuntu 執行（非 Docker 容器）
監聽 TCP 9998，收到連線時自動呼叫 Windows PowerShell 啟動 OpenOCD。

安裝方式：執行 setup_relay.ps1（Windows PowerShell Admin）即可自動安裝。
"""
import socket
import subprocess
import threading
import time
import sys

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
if (-not $ocd) { Write-Error 'openocd.exe not found'; exit 1 }
$stlink = (Get-ChildItem 'C:\ST\' -Recurse -Filter 'stlink-dap.cfg' -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
$scripts = Split-Path (Split-Path $stlink -Parent) -Parent
$rule = Get-NetFirewallRule -DisplayName 'OpenOCD GDB 3333' -ErrorAction SilentlyContinue
if (-not $rule) { New-NetFirewallRule -DisplayName 'OpenOCD GDB 3333' -Direction Inbound -Protocol TCP -LocalPort 3333 -Action Allow | Out-Null }
& $ocd -s $scripts -f interface/stlink-dap.cfg -c 'set AP_NUM 0' -f target/stm32h7x.cfg
"""

_openocd_lock = threading.Lock()
_openocd_running = False


def is_openocd_running():
    try:
        s = socket.create_connection(('127.0.0.1', OPENOCD_PORT), timeout=1)
        s.close()
        return True
    except Exception:
        return False


def launch_openocd():
    global _openocd_running
    with _openocd_lock:
        if is_openocd_running():
            print("[relay] OpenOCD already running, skip launch")
            return
        if _openocd_running:
            print("[relay] Launch already in progress")
            return
        _openocd_running = True

    print("[relay] Launching OpenOCD via powershell.exe ...")
    try:
        subprocess.Popen(
            ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-Command', POWERSHELL_CMD],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("[relay] ERROR: powershell.exe not found. Is this running in WSL2?", file=sys.stderr)
    finally:
        # 等 OpenOCD 起來後重置旗標
        def reset():
            for _ in range(30):
                time.sleep(1)
                if is_openocd_running():
                    break
            global _openocd_running
            _openocd_running = False
        threading.Thread(target=reset, daemon=True).start()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('0.0.0.0', RELAY_PORT))
    except OSError as e:
        print(f"[relay] Cannot bind port {RELAY_PORT}: {e}", file=sys.stderr)
        sys.exit(1)
    server.listen(5)
    print(f"[relay] OpenOCD Relay listening on port {RELAY_PORT} (WSL2)")
    print(f"[relay] Will launch OpenOCD on Windows when Docker container connects")

    while True:
        try:
            conn, addr = server.accept()
            conn.close()
            print(f"[relay] Triggered by {addr}")
            threading.Thread(target=launch_openocd, daemon=True).start()
        except KeyboardInterrupt:
            print("\n[relay] Shutting down")
            break


if __name__ == '__main__':
    main()
