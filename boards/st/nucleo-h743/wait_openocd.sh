#!/bin/bash
# 等待 Windows 端 OpenOCD 在 port 3333 就緒
# 由 VS Code preLaunchTask 呼叫，不需手動執行

RELAY_HOST="host.docker.internal"   # Windows relay server
RELAY_PORT=9998
OCD_HOST="host.docker.internal"
OCD_PORT=3333

check_ocd() {
    python3 -c "import socket; socket.create_connection(('host.docker.internal', 3333), 1).close()" 2>/dev/null
}

trigger_relay() {
    python3 -c "import socket; socket.create_connection(('host.docker.internal', 9998), 2).close()" 2>/dev/null
}

# 已經在跑了就直接走
if check_ocd; then
    echo "[OK] OpenOCD 已在執行，開始除錯..."
    exit 0
fi

# 嘗試透過 WSL2 Relay 自動啟動
if trigger_relay; then
    echo "[relay] 已觸發 WSL2 Relay，等待 OpenOCD 啟動..."
    for i in $(seq 1 20); do
        sleep 1
        printf "."
        if check_ocd; then
            echo ""
            echo "[OK] OpenOCD 就緒，開始除錯！"
            exit 0
        fi
    done
    echo ""
    echo "[!] Relay 已觸發但 OpenOCD 未在 20 秒內就緒，請檢查 Windows 端錯誤"
    exit 1
else
    # Relay 沒在跑，顯示手動指示
    echo "============================================================"
    echo "  WSL2 Relay 未啟動。請選擇以下其中一種方式："
    echo ""
    echo "  【首次安裝 Relay（設定開機自動啟動）】Windows PowerShell（管理員）："
    echo "    Set-ExecutionPolicy -Scope Process Bypass"
    echo "    & 'boards\\st\\nucleo-h743\\relay_server.ps1' -Install"
    echo ""
    echo "  【手動啟動 OpenOCD（不裝 Relay）】Windows PowerShell："
    echo "    & 'boards\\st\\nucleo-h743\\start_openocd.ps1'"
    echo ""
    echo "  等待連線中（每 2 秒偵測）..."
    echo "============================================================"
    while ! check_ocd; do
        sleep 2
        printf "."
    done
    echo ""
    echo "[OK] OpenOCD 就緒，開始除錯！"
fi
