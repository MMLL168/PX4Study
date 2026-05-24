# 換電腦移植指南

> 本文記錄在新電腦重新建立 PX4Study 開發環境的完整步驟。
> 所有修復都已 commit 進 repo，**不需要重新 patch 任何程式碼**。

---

## 前置軟體安裝（Windows）

| 軟體 | 用途 | 備註 |
|------|------|------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | DevContainer 執行環境 | 開啟 WSL2 整合 |
| [VS Code](https://code.visualstudio.com/) | 編輯器 | 需安裝 Dev Containers 擴充 |
| [STM32CubeIDE](https://www.st.com/en/development-tools/stm32cubeide.html) | 提供 OpenOCD 和 stlink-dap.cfg | 或 STM32CubeProgrammer |
| [Python 3.x（Windows 原生）](https://www.python.org/) | 跑 GUI 工具 | 安裝時勾選「Add to PATH」 |
| Git | 拉取專案 | Docker Desktop 附帶或另裝 |

---

## Step 1 — 拉取專案

在 PowerShell 或 Git Bash：

```powershell
git clone https://github.com/MMLL168/PX4Study.git
cd PX4Study
```

---

## Step 2 — 開啟 DevContainer

1. 用 VS Code 開啟 `PX4Study` 資料夾
2. 右下角彈出提示 → **「Reopen in Container」**
3. 第一次會拉 Docker image，等待幾分鐘直到終端機出現 `user@...:/workspaces/PX4Study$`

> 若沒有彈出提示：按 `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`

---

## Step 3 — 安裝 Windows Relay（F5 一鍵燒錄自動化）

Relay 讓 F5 按下時自動啟動 Windows 端的 OpenOCD，**只需安裝一次，開機自動執行**。

在 **Windows PowerShell（管理員）** 執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\<你的WSL使用者名稱>\PX4Study\boards\st\nucleo-h743\relay_server.ps1" -Install
```

> 替換 `<你的WSL使用者名稱>` 為實際的 WSL 帳號（例如 `marlonwu`）

**驗證安裝成功**：工作管理員 → 服務 → 找到 `PX4-OpenOCD-Relay`，或執行：

```powershell
Get-ScheduledTask -TaskName "PX4-OpenOCD-Relay"
```

### 如果 Relay 出問題需要重啟

```powershell
# 殺掉舊的（port 9998 被佔用時）
$p = (Get-NetTCPConnection -LocalPort 9998 -ErrorAction SilentlyContinue).OwningProcess
if ($p) { Stop-Process -Id $p -Force }
taskkill /F /IM openocd.exe 2>$null

# 重新啟動
powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\marlonwu\PX4Study\boards\st\nucleo-h743\relay_server.ps1"
```

---

## Step 4 — 防火牆規則（第一次可能需要）

確保 WSL2 能連到 Windows 的 port 3333（OpenOCD GDB server）：

```powershell
New-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -Direction Inbound -Protocol TCP -LocalPort 3333 -Action Allow -ErrorAction SilentlyContinue
```

---

## Step 5 — 安裝 GUI 工具套件（Windows Python）

```powershell
pip install pyserial Pillow
```

執行 GUI：

```powershell
python "\\wsl.localhost\Ubuntu\home\marlonwu\PX4Study\tool\mpu6050_viewer.py"
```

---

## Step 6 — 首次 F5 Build + 燒錄

1. 接上 Nucleo-H743ZI2 USB（ST-Link）
2. 確認 COM 埠出現在裝置管理員
3. 在 VS Code 按 **F5**，選 `openocd-win (st_nucleo-h743)`
4. 自動流程：Build → 等待 OpenOCD → GDB 連線 → 燒錄 → Halt at main

> 首次 build 約 5-10 分鐘（編譯整個 PX4）

---

## 常見問題排查

### F5 顯示「Connection timed out port 3333」

→ Relay 沒有在跑，執行 Step 3 的重啟指令

### F5 顯示「WSL2 Relay 未啟動」並一直等待

→ Relay 跑了但 OpenOCD 沒啟動，手動跑 OpenOCD（不加 reset halt）：

```powershell
$ocd     = (Get-ChildItem "C:\ST\" -Recurse -Filter "openocd.exe" | Select-Object -First 1).FullName
$stlink  = (Get-ChildItem "C:\ST\" -Recurse -Filter "stlink-dap.cfg" | Select-Object -First 1).FullName
$scripts = Split-Path (Split-Path $stlink -Parent) -Parent
& $ocd -s "$scripts" -f interface/stlink-dap.cfg -c "set AP_NUM 0" -c "set CONNECT_UNDER_RESET 1" -c "set ENABLE_LOW_POWER 1" -c "set STOP_WATCHDOG 1" -f target/stm32h7x.cfg -c "init"
```

等出現 `Listening on port 3333 for gdb connections` 後 VS Code 自動繼續。

### `Error erasing flash with vFlashErase packet`

→ 已在 `launch.json` 修好（`monitor reset_config srst_only srst_nogate`），
若再出現先斷電重接 USB 再 F5。

### GUI 連線後 IMU 沒有資料

依序在 NSH 手動確認：

```
i2cdetect -b 1          # 確認 0x68 有出現
mpu6050 start -X -b 1 -a 0x68
mpu6050 status          # 確認 Running
listener sensor_accel   # 確認有資料輸出
```

---

## 不需要重做的事

以下修復都已在 repo 內，clone 後直接生效：

- `tasks.json` 的 PATH（含 ccache、arm-none-eabi-gcc）
- `Makefile` 的 python3 路徑修正
- `launch.json` 的 `monitor reset_config srst_only srst_nogate`
- `relay_server.ps1` 移除 `reset halt`（避免 OpenOCD crash）
- `wait_openocd.sh` 超時後的 `exit 1`
- MPU6050 driver 原始碼
- GUI 工具（`tool/mpu6050_viewer.py`）
