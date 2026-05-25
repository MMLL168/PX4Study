# PX4 開發與除錯日誌 (DevLog)

此文件用於記錄開發過程中的修改、遇到的問題、處理方式與時間。

**記錄規則**：每次修改程式碼、設定檔、板級移植，都必須在此補一筆記錄。
格式：`## [YYYY-MM-DD HH:MM] 標題` + 問題描述、原因分析、處理方式三段。

---

## [2026-05-25 11:00] OpenOCD tcl_port 6666 無法綁定導致退出修復

**問題**：F5 觸發 Relay 後 wait_openocd.sh 20 秒 timeout，OpenOCD 未在 port 3333 就緒。
手動執行 OpenOCD 可見 `Listening on port 3333` 後立即出現
`Error: couldn't bind tcl to socket on port 6666: No error`，OpenOCD 退出。

**原因**：OpenOCD 預設嘗試綁定 TCL port 6666 作為腳本控制介面；
port 6666 被 Windows 某個程式佔用或拒絕，導致 OpenOCD 印出錯誤後自動退出，
port 3333 隨之關閉，wait_openocd.sh 偵測不到。

**處理方式**：
`boards/st/nucleo-h743/relay_server.ps1` 的 OpenOCD 啟動參數中加入
`-c "tcl_port disabled"`，關閉不需要的 TCL 介面。
同步更新 `C:\PX4\relay_server.ps1`（Windows 端 Relay 備份）。

---

## [2026-05-25 11:30] 新電腦 Debug 環境建立記錄

**問題**：換新電腦後需重新建立容器內 GDB 除錯環境。

**處理方式**（每台新電腦需手動執行一次）：
1. 容器內建立 `.so.5` symlink：
   ```bash
   mkdir -p ~/.local/lib ~/.local/bin
   ln -sf /lib/x86_64-linux-gnu/libncurses.so.6 ~/.local/lib/libncurses.so.5
   ln -sf /lib/x86_64-linux-gnu/libtinfo.so.6   ~/.local/lib/libtinfo.so.5
   ```
2. 建立 GDB wrapper（版本偽裝 8.3.1→9.3.1，threading pump，訊號轉發）
   → `~/.local/bin/arm-none-eabi-gdb-wrapper.sh`
3. 建立 nm / objdump wrapper（同目錄）
4. 建立 python symlink：`ln -sf /usr/bin/python3 ~/.local/bin/python`
5. Windows 端：安裝 Relay（`C:\PX4\relay_server.ps1 -Install`）、
   開放防火牆 port 3333
6. VS Code：安裝 Cortex-Debug 1.6.10

詳細步驟見 `Study/new_pc_setup.md`。

---

## [2026-05-25 12:00] GUI 字體放大

**問題**：mpu6050_viewer.py 所有文字偏小，高解析度螢幕不易閱讀。

**原因**：原始字體設定以 size 8～15 為主，缺乏可讀性。

**處理方式**（`tool/mpu6050_viewer.py`）：
全域字體縮放，各級字體對應關係：
- 8 → 14（Yaw 說明）
- 9 → 11（一般文字、標籤、輸入框）
- 9 bold → 11 bold（區塊標題 IMU/LED CONTROL）
- 10 bold → 13 bold（ATTITUDE/ACCEL/GYRO 標題、按鈕）
- 12 → 14（重新整理按鈕）
- 15 bold → 19 bold（Roll/Pitch 數值）

---

## [2026-05-24 04:00] 確認 NSH debug 工具不影響 PX4 正常運作

**問題**：使用 NSH + mpu6050 start/stop + listener 的 debug 流程，
是否會干擾 PX4 正常的飛控運作？

**結論**：
- `listener sensor_accel` 純讀取 uORB topic，完全不影響任何模組。
- `mpu6050 start / stop` 只要 rcS 啟動腳本沒有自動啟動該 driver 就安全；
  若 rcS 有啟動（量產飛控板），手動 stop 會讓 EKF2 失去 IMU 資料。
- Nucleo-H743ZI2 為開發板，rcS 不自動啟動 mpu6050，
  目前 debug 工具與 PX4 主流程完全獨立，互不干擾。
- 量產時改用 TELEM1 + MAVLink，不走 NSH，根本沒有衝突路徑。

**驗證指令**（確認 rcS 有無自動啟動 mpu6050）：
```
cat /etc/init.d/rc.sensors
```

---

## [2026-05-24 03:00] GUI 加輪詢間隔輸入框 + Yaw 說明標註

**問題**：使用者希望 IMU 資料以可調頻率更新（非持續串流），
並詢問為何 GUI 沒有 Yaw 角度顯示。

**原因分析**：
- `listener sensor_accel`（無 -n）是持續串流，無法控制更新頻率。
- `listener sensor_accel -n N` 是讀取 uORB 已緩存訊息後退出，
  driver 剛啟動時 queue 為空故立即返回（這也解釋了之前沒有資料的問題）。
- Yaw 不可從加速度計取得（見 learn.md §11）。

**處理方式** (`tool/mpu6050_viewer.py`)：
1. 加入 `_interval_var`（預設 300 ms），在 IMU CONTROL 區顯示可編輯的更新間隔輸入框。
2. `_start_listener()` 改為每次送 `listener sensor_accel -n 1`（單筆讀取）。
3. `_poll()` 中偵測裸 `nsh>` 後，等待使用者設定的間隔再送下一次，達到輪詢效果。
4. 在右側數值面板底部加上說明文字：`* Yaw 需磁力計，MPU6050 不支援`。
5. 學習概念寫入 `Study/learn.md §11`。

---

## [2026-05-24 02:00] relay_server.ps1 OpenOCD 啟動後立即退出修復

**問題**：F5 後 wait_openocd.sh 顯示「WSL2 Relay 未啟動」並持續等待，
手動執行 OpenOCD 可見 `Error: timed out while waiting for target halted`，
隨後 OpenOCD 自動退出，port 3333 不再 listen。

**原因**：relay_server.ps1 的 `Start-OpenOCD` 在 OpenOCD 啟動參數中加了
`-c "init" -c "reset halt"`。STM32H7 使用 VECTRESET（CPU-only reset），
不觸發 D1/D2/D3 power domain reset，DAP 失去同步後 `reset halt` timeout，
OpenOCD 印出錯誤後退出，port 3333 消失。

**處理方式** (`boards/st/nucleo-h743/relay_server.ps1`)：
移除啟動參數中的 `-c "reset halt"`，只保留 `-c "init"`。
OpenOCD 啟動後停在 `Listening on port 3333 for gdb connections`，
GDB 連線後由 launch.json preLaunchCommands 的
`monitor reset_config srst_only srst_nogate` + `monitor reset halt` 處理正確的 SRST reset。

---

## [2026-05-24 01:00] listener 指令風暴修復（nsh> echo 誤判）

**問題**：START IMU 後 log 出現數十行 `listener sensor_accel -n 500`
快速重複，每個 listener 都立即返回，姿態資料永遠為 0。

**原因**：`_poll()` 用 `'nsh>' in ln` 偵測 listener 結束，但 NSH echo 行
（如 `nsh> > listener sensor_accel -n 500`）也含 `nsh>`，造成每次送出 listener
後板子的 echo 馬上又觸發下一次送出，形成「指令風暴」。
大量 listener 指令讓 NSH 把前一個 listener 中斷，永遠收不到任何感測器資料。

**處理方式** (`tool/mpu6050_viewer.py`)：
1. 偵測條件改為 `ln.strip() == 'nsh>'`，只匹配裸 prompt（無後續字元的行）。
2. `_start_listener()` 加入 1.5 秒冷卻（`time.monotonic()` 比較），
   即使偵測到 nsh> 也不會在短時間內重複發送。
3. 頂層加 `import time`，`__init__` 加 `_last_listener_t = 0.0` 初始化。

---

## [2026-05-24 00:00] mpu6050 "Already running" + listener 無資料 修復

**問題**：點 START IMU 時 log 出現 `WARN [SPI_I2C] Already running on bus 1` 以及
`ERROR: no instance started (no device on bus?)`，`listener sensor_accel -n 100000`
立即返回，地平線無任何姿態更新。

**原因**：前一次 `mpu6050 start` 的 instance 未停止即再次呼叫，
PX4 driver 拒絕啟動第二個 instance，listener 拿不到資料就逾時退出。
另外 `-n 100000` 會讓 listener 佔用 shell 極長時間，重啟後的 prompt 偵測也沒做。

**處理方式** (`tool/mpu6050_viewer.py`)：
1. `_start_imu()` 改為先送 `mpu6050 stop`，等 400 ms 後呼叫 `_imu_start2()`。
2. `_imu_start2()` 送 `mpu6050 start -X -b 1 -a 0x68`，等 1000 ms 後呼叫 `_start_listener()`。
3. `_start_listener()` 改用 `-n 500`（500 筆後 listener 自動退出回 NSH）。
4. `_poll()` 每次解析每行時偵測 `nsh>`：若 IMU 開啟且 listener 剛剛跑完
   (`_listener_up=True`)，就將 `_listener_up` 歸零並排程 200 ms 後重啟 listener，
   達到持續串流效果。
5. `_stop_imu()` 先送 Ctrl+C 再送 `mpu6050 stop`，同時清除 `_listener_up` 旗標。

---

## [2026-05-23 19:00] F5 全自動流程修復（build PATH / Python / Relay 安裝）

> **換電腦必讀**：此節記錄讓 F5「一鍵 build + 燒錄」完全自動化的所有修復與安裝步驟。

### 問題描述
按 F5 後依序出現三個錯誤：
1. `ccache: error: Could not find compiler "arm-none-eabi-gcc" in PATH`
2. `/bin/sh: /usr/bin/python: not found`
3. `Failed to launch GDB: host.docker.internal:3333: Connection timed out`

### 原因分析
1. tasks.json `nucleo-h743: build` 的 PATH 覆蓋了系統 PATH，遺漏 `/usr/lib/ccache` 和 `/opt/gcc/bin`
2. cmake 在 `build.ninja` 與 `CMakeCache.txt` 把 Python 路徑寫死為 `/usr/bin/python`（容器只有 `python3`）
3. Windows 端 OpenOCD 未啟動；Relay 也未安裝，`wait_openocd.sh` 20 秒超時後沒有回傳 `exit 1`，VS Code 誤以為成功而繼續

另外，`led_chaser.cpp` 使用了舊版 CRTP `ModuleBase<T>` 語法，但此版本 PX4 已改為非 template 的 Descriptor 模式。

### 修復一：tasks.json build task PATH
`.vscode/tasks.json` 的 `nucleo-h743: build` 加入缺少的路徑：
```json
"PATH": "/usr/lib/ccache:/opt/gcc/bin:/home/user/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
```

### 修復二：build 目錄的 Python 路徑（一次性）
每次 cmake configure 後執行（build 目錄存在時才需要）：
```bash
sed -i 's|PYTHON_EXECUTABLE:FILEPATH=/usr/bin/python$|PYTHON_EXECUTABLE:FILEPATH=/usr/bin/python3|' \
    build/st_nucleo-h743_default/CMakeCache.txt
sed -i 's|/usr/bin/python |/usr/bin/python3 |g' \
    build/st_nucleo-h743_default/build.ninja
```
> 若 build 目錄不存在（新電腦首次 cmake），系統會找 `~/.local/bin/python`（已有 symlink），不需手動修改。

### 修復三：wait_openocd.sh 超時 exit code
`boards/st/nucleo-h743/wait_openocd.sh` Relay 20 秒超時後加上 `exit 1`，
避免 VS Code 誤判成功後繼續啟動 GDB。

### 修復四：led_chaser.cpp 改用新版 ModuleBase API
PX4 此版本將 `ModuleBase<T>`（CRTP template）改為非 template，
使用 `Descriptor` 物件傳遞函式指標。新寫法：
```cpp
class LedChaser : public ModuleBase, public px4::ScheduledWorkItem {
public:
    static Descriptor desc;   // 每個模組宣告靜態 Descriptor
    ...
};
ModuleBase::Descriptor LedChaser::desc{task_spawn, custom_command, print_usage};

int led_chaser_main(int argc, char *argv[]) {
    return ModuleBase::main(LedChaser::desc, argc, argv);
}
// exit_and_cleanup 改為 exit_and_cleanup(desc)
```

---

### 【換電腦必做】Windows Relay 安裝（F5 完全自動化）

Relay 讓 F5 按下時自動啟動 Windows 端的 OpenOCD，無需手動操作。

**在 Windows PowerShell（管理員）貼上整段執行**：

```powershell
Set-ExecutionPolicy -Scope Process Bypass

New-Item -ItemType Directory -Force -Path "C:\PX4" | Out-Null

@'
# OpenOCD Relay Server
param([switch]$Install, [switch]$Uninstall)
$scriptPath = $MyInvocation.MyCommand.Path
$taskName   = "PX4-OpenOCD-Relay"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已移除" -ForegroundColor Yellow; exit 0
}
if ($Install) {
    $action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
    Write-Host "已設定開機自動啟動" -ForegroundColor Green
    Start-Process powershell.exe -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`"" -WindowStyle Hidden
    Write-Host "Relay 已在背景啟動" -ForegroundColor Green; exit 0
}

function Find-OpenOCD {
    foreach ($root in @("C:\ST\","C:\Program Files\ST\","C:\Program Files (x86)\ST\")) {
        if (Test-Path $root) {
            $f = (Get-ChildItem $root -Recurse -Filter "openocd.exe" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
            if ($f) { return $f }
        }
    }; return $null
}
function Is-OpenOCDRunning {
    try { $tcp=[System.Net.Sockets.TcpClient]::new(); $tcp.Connect("127.0.0.1",3333); $tcp.Close(); return $true } catch { return $false }
}
function Start-OpenOCD {
    if (Is-OpenOCDRunning) { return }
    $ocd = Find-OpenOCD; if (-not $ocd) { return }
    $stlink = (Get-ChildItem "C:\ST\" -Recurse -Filter "stlink-dap.cfg" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
    $scripts = Split-Path (Split-Path $stlink -Parent) -Parent
    $rule = Get-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -ErrorAction SilentlyContinue
    if (-not $rule) { New-NetFirewallRule -DisplayName "OpenOCD GDB 3333" -Direction Inbound -Protocol TCP -LocalPort 3333 -Action Allow | Out-Null }
    Start-Process -FilePath $ocd -ArgumentList "-s `"$scripts`" -f interface/stlink-dap.cfg -c `"set AP_NUM 0`" -f target/stm32h7x.cfg -c `"reset_config srst_only srst_nogate`"" -WindowStyle Minimized
}

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, 9998)
$listener.Start()
while ($true) {
    try { $client=$listener.AcceptTcpClient(); $client.Close(); Start-OpenOCD } catch { break }
}
$listener.Stop()
'@ | Set-Content "C:\PX4\relay_server.ps1" -Encoding UTF8

& "C:\PX4\relay_server.ps1" -Install
```

**驗證**：
```powershell
netstat -ano | findstr 9998
# 應看到 LISTENING
```

安裝後 F5 完整自動流程：
```
F5
 ├─ 1. make st_nucleo-h743_default（自動 build）
 ├─ 2. wait_openocd.sh 偵測 port 3333 → 觸發 Relay(9998) → 自動啟動 OpenOCD
 ├─ 3. GDB 連線 host.docker.internal:3333
 ├─ 4. 燒錄韌體
 └─ 5. 停在 __start（手動設斷點）或直接按 F5 繼續執行
```

---

## [2026-05-23 06:00] SWD 燒錄導致 Bootloader 遺失與還原
- **問題描述**：使用 Pixhawk Debug Adapter (SWD 介面) 進行底層燒錄與除錯時，發現飛控插上 USB 後毫無反應，電腦無法辨識到虛擬 COM Port。
- **原因分析**：SWD 燒錄軟體的預設行為是「全晶片抹除 (Mass Erase)」，這會把位在 Flash 起點 (`0x08000000`) 的 Bootloader 也一併清除。沒有 Bootloader，飛控就失去了 USB DFU 與 Serial 溝通的功能。
- **處理方式**：
  1. **災後還原**：先透過 SWD 介面，將官方編譯好的 Bootloader `.bin` 重新燒錄到 `0x08000000`。完成後拔除 SWD，改插 USB 線，此時電腦便能抓到 COM Port。最後再用一般 `make upload` 或透過 QGC 燒錄 PX4 App 韌體即可。
  2. **未來預防**：在除錯工具 (如 OpenOCD / GDB / STM32CubeProgrammer) 的設定中，將抹除模式改為「**Sector Erase (區塊抹除)**」，這樣就能避開 Bootloader 所在的磁區。

---

## [2026-05-23 建立] Nucleo-H743 Phase 1：USART3 虛擬 COM 通訊板級移植

- **目的**：從零建立 `boards/st/nucleo-h743/` 板級支援套件 (BSP)，目標是讓 STM32H743ZI 開機後透過 USART3 (ST-Link VCP) 輸出 NSH Shell，實現 PC ↔ 開發板的雙向串列通訊。此為後續接 MPU6050 讀取姿態 (Phase 2) 的基礎。

- **硬體關鍵資訊 (Nucleo-H743ZI2)**：
  - CPU：STM32H743ZI @ 480 MHz（HSE 8 MHz 晶振）
  - VCP 腳位：USART3 TX=PD8 (AF7), RX=PD9 (AF7) → ST-Link → PC COM Port
  - LED：LD1 (綠, PB0) / LD2 (黃, PE1)，**主動高電位**（與一般 PX4 板主動低相反）
  - I2C1：PB8 (SCL) / PB9 (SDA) → 預留給 Phase 2 MPU6050

- **處理方式**：
  建立以下檔案結構（所有檔案皆已新增至 `boards/st/nucleo-h743/`）：

  ```
  boards/st/nucleo-h743/
  ├── default.px4board          # PX4 模組選擇（最小集）
  ├── nuttx-config/
  │   ├── Kconfig
  │   ├── include/board.h       # PLL/時脈設定 + USART3/I2C1 腳位定義
  │   ├── include/board_dma_map.h
  │   ├── nsh/defconfig         # NuttX Kconfig：USART3 為 console, 115200 baud
  │   └── scripts/script.ld     # 連結腳本：Flash 從 0x08000000 開始（無 bootloader）
  └── src/
      ├── CMakeLists.txt
      ├── board_config.h        # GPIO 定義（LED 主動高）
      ├── i2c.cpp               # I2C1 外部匯流排（Phase 2 用）
      ├── init.c                # 板級初始化：GPIO/LED/DMA
      ├── led.c                 # 主動高電位 LED 驅動
      ├── spi.cpp               # 空的 SPI 設定（Phase 1 不用）
      └── timer_config.cpp      # TIM1 CH1/CH2 on PE9/PE11
  ```

- **關鍵設計決策**：
  1. **Flash 起點 0x08000000**：Nucleo 透過 ST-Link 直接燒錄，不走 USB DFU Bootloader，故連結腳本 Flash Origin 設為 `0x08000000`（matek/h743 是 `0x08020000`）。
  2. **LED 主動高**：Nucleo LD1/LD2 接法與 Pixhawk 系列相反，`led.c` 改為 `stm32_gpiowrite(pin, state)` 而非 `!state`。
  3. **defconfig 只啟用 USART3**：移除 UART4/7/8、USART1/2/6，移除 SDMMC / USB CDC，避免腳位衝突並縮短首次編譯時間。

- **驗證步驟（上板測試流程）**：
  1. 在 PX4 容器內執行：`make st_nucleo-h743_default`
  2. 用 STM32CubeProgrammer 或 OpenOCD 透過 SWD 燒錄 `.elf` 到 `0x08000000`
  3. 保持 USB 線連接（ST-Link VCP），開啟 PuTTY / minicom：115200 8N1
  4. 預期看到 `nsh>` 提示字元
  5. 輸入 `ver all` 確認板子型號，輸入 `uorb status` 確認 uORB 執行中

---

## [2026-05-23 08:30] 修正 HRT_TIMER 未定義導致鏈結失敗

- **問題描述**：
  `make st_nucleo-h743_default` 在鏈結階段（step 401/403）失敗，
  大量 `undefined reference to 'hrt_absolute_time'`、`hrt_cancel`、
  `latency_buckets`、`latency_counters` 等符號。
- **原因分析**：
  `platforms/nuttx/src/px4/stm/stm32_common/hrt/hrt.c` 的全部程式碼
  都被 `#ifdef HRT_TIMER` 包住。`board_config.h` 沒有定義此巨集，
  導致 `libarch_hrt.a` 編譯出空物件，所有 HRT 符號不存在。
  另發現 defconfig 中 `CONFIG_STM32H7_TIM2=y` 是多餘的（timer_config.cpp
  只用 TIM1 做 PWM），一併移除。
- **處理方式**：
  1. `boards/st/nucleo-h743/src/board_config.h` 新增：
     ```c
     #define HRT_TIMER         8   /* TIM8，與 CubeOrange (STM32H743) 相同 */
     #define HRT_TIMER_CHANNEL 3
     ```
  2. `boards/st/nucleo-h743/nuttx-config/nsh/defconfig` 移除 `CONFIG_STM32H7_TIM2=y`。
  3. `boards/st/nucleo-h743/firmware.prototype` 新增（缺少此檔導致 .px4 打包失敗）。
- **結果**：
  `st_nucleo-h743_default.elf`（7.3 MB）與 `st_nucleo-h743_default.bin`（220 KB）
  成功產生，Flash 使用率 10.74%（225 KB / 2 MB）。

---

## [2026-05-23 09:00] 新增學習準則與 devlog 記錄規則

- **問題描述**：沒有明確規範哪些內容要寫入 `learn.md`，哪些要寫入 `devlog.md`。
- **原因分析**：無規範容易導致兩個檔案重複或漏記。
- **處理方式**：
  1. `CLAUDE.md` 新增兩條準則：學習筆記寫 `Study/learn.md`、每次修改記 `Study/devlog.md`。
  2. `Study/learn.md` 開頭新增「學習準則」章節（說明此檔的使用規則與格式）。
  3. `Study/learn.md` 新增 §9 HRT 機制解析。
  4. `Study/devlog.md` 開頭補上記錄規則說明。

---

## [2026-05-23 11:00–16:00] VS Code 單步除錯完整設定（F5 全自動燒錄+停在起點）

> **換電腦必讀**：此筆記錄所有步驟，依序照做即可還原完整除錯環境。

### 背景與問題

PX4 DevContainer 在 Docker（WSL2 內）運行，USB 被三層隔離：
```
STM32H743 ← ST-Link V3 (USB) ← Windows ← WSL2 ← Docker 容器
```
- `usbipd` 無法 attach ST-Link V3（複合裝置，不相容）
- 容器內的 OpenOCD 無法存取 USB

**解法架構**：
```
[Docker GDB] --TCP:3333--> [Windows OpenOCD] --SWD--> [STM32H743]
             host.docker.internal = 192.168.65.254
```

遇到的額外障礙及解法一覧：

| 問題 | 原因 | 解法 |
|------|------|------|
| GDB 無法啟動 | 容器缺 `libncurses.so.5` / `libtinfo.so.5` | 建立 symlink 指向 `.so.6` |
| Cortex-Debug 拒絕啟動 | GDB 8.3.1 < 要求的 9，1.12.1 和 1.6.10 都有此限制 | Python wrapper 偽裝版本號 `8.3.1→9.3.1` |
| nm/objdump 找不到 | Cortex-Debug 從 gdbPath 推導名稱，wrapper 命名須一致 | 另建 nm/objdump wrapper |
| vFlashErase 失敗 | `monitor reset halt` 逾時，CPU 未停止即嘗試抹除 Flash | OpenOCD 改用硬體 NRST：`reset_config srst_only srst_nogate` |
| Stop 按鈕無效 | Python wrapper 未轉發 SIGTERM/SIGINT 給 GDB | wrapper 加 signal forwarding |
| 停在錯誤的 main | `runToMain` 找到 `ModuleBase::main`（C++ 成員函式）| 改用 `runToEntryPoint: "__start"` |
| stlink.cfg 遞迴錯誤 | 新版 stm32h7x.cfg 與 HLA transport 衝突 | 改用 `stlink-dap.cfg`（DAP transport）|
| AP_NUM 未定義 | ST 版 stm32h7x.cfg 需要此變數 | 加 `-c "set AP_NUM 0"` |

---

### 【換電腦必做】容器內一次性設定

在 **VS Code 容器終端機**執行（每台電腦只需做一次，重建容器也要重做）：

```bash
# Step 1：補齊缺少的動態函式庫
mkdir -p ~/.local/lib ~/.local/bin
ln -s /lib/x86_64-linux-gnu/libncurses.so.6 ~/.local/lib/libncurses.so.5
ln -s /lib/x86_64-linux-gnu/libtinfo.so.6   ~/.local/lib/libtinfo.so.5

# Step 2：GDB wrapper（版本偽裝 + 函式庫路徑 + 訊號轉發）
cat > ~/.local/bin/arm-none-eabi-gdb-wrapper.sh << 'WRAPPER'
#!/usr/bin/env python3
import os, sys, subprocess, signal

env = os.environ.copy()
env['LD_LIBRARY_PATH'] = os.path.expanduser('~/.local/lib') + ':' + env.get('LD_LIBRARY_PATH', '')

proc = subprocess.Popen(
    ['/opt/gcc/bin/arm-none-eabi-gdb'] + sys.argv[1:],
    stdin=sys.stdin, stdout=subprocess.PIPE, stderr=sys.stderr,
    env=env, bufsize=0
)

def fwd(sig, _):
    try: proc.send_signal(sig)
    except: pass

signal.signal(signal.SIGTERM, fwd)
signal.signal(signal.SIGINT,  fwd)

while True:
    chunk = proc.stdout.read(4096)
    if not chunk:
        break
    sys.stdout.buffer.write(chunk.replace(b'8.3.1', b'9.3.1'))
    sys.stdout.buffer.flush()

sys.exit(proc.wait())
WRAPPER
chmod +x ~/.local/bin/arm-none-eabi-gdb-wrapper.sh

# Step 3：nm / objdump wrapper
cat > ~/.local/bin/arm-none-eabi-nm-wrapper.sh << 'EOF'
#!/bin/bash
exec /opt/gcc/bin/arm-none-eabi-nm "$@"
EOF
cat > ~/.local/bin/arm-none-eabi-objdump-wrapper.sh << 'EOF'
#!/bin/bash
exec /opt/gcc/bin/arm-none-eabi-objdump "$@"
EOF
chmod +x ~/.local/bin/arm-none-eabi-nm-wrapper.sh \
         ~/.local/bin/arm-none-eabi-objdump-wrapper.sh

# 驗證
LD_LIBRARY_PATH="$HOME/.local/lib" /opt/gcc/bin/arm-none-eabi-gdb --version
# 應顯示：GNU gdb ... 8.3.1... （版本偽裝在 wrapper 內處理）
```

---

### 【換電腦必做】VS Code 擴充套件設定

**降級 Cortex-Debug 至 1.6.10**（Cortex-Debug 1.12.1 和更新版都有 GDB >= 9 的硬性限制）：
1. VS Code Extensions（Ctrl+Shift+X）→ 搜尋 Cortex-Debug
2. 點進去 → 齒輪圖示 ⚙️ → **下載特定版本的 VSIX...**
3. 選 **1.6.10** → 下載到容器 `/home/user/`
4. Extensions → `...` → **從 VSIX 安裝** → 選剛才的 `.vsix` 檔
5. Reload VS Code

---

### 【換電腦必做】Windows 端 Relay 安裝

讓 F5 自動啟動 OpenOCD（不需手動在 Windows 開視窗）。

在 **Windows PowerShell（管理員）** 執行一次：
```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "\\wsl.localhost\Ubuntu\workspaces\PX4Study\boards\st\nucleo-h743\relay_server.ps1" -Install
```
- 安裝後 Relay 會在 Windows 登入時自動背景執行
- Relay 監聽 TCP 9998；收到容器觸發後自動啟動 OpenOCD（port 3333）
- 若要手動驗證：`netstat -ano | findstr 9998` 應看到 LISTENING

---

### 完整除錯流程（設定好後每次這樣用）

```
F5
 ├─ preLaunchTask: wait_openocd.sh
 │   ├─ 偵測 host.docker.internal:3333 是否已開
 │   ├─ 若未開：觸發 host.docker.internal:9998（Windows Relay）
 │   └─ Relay 自動啟動 OpenOCD，等待就緒
 ├─ GDB wrapper 啟動，連上 host.docker.internal:3333
 ├─ monitor reset halt → CPU 停住（halted due to breakpoint）
 ├─ target-download → 燒錄 PX4 韌體（~225 KB）
 ├─ monitor reset halt（再次確保從頭開始）
 └─ 停在 __start()（stm32_start.c:188）← 等同傳統 main() 第一行
```

操作方式：
- **F10**：單步（不進入函式）
- **F11**：進入函式
- **F5**：繼續執行到下一個斷點
- **紅色正方形**：停止偵錯

---

### 已確認路徑（此台電腦）

| 項目 | 路徑 |
|------|------|
| OpenOCD | `C:\ST\STM32CubeIDE_1.19.0\...\tools\bin\openocd.exe` |
| ST Scripts | `C:\ST\STM32CubeIDE_1.19.0\...\com.st.stm32cube.ide.mcu.debug.openocd_2.3.100.202501240831\resources\openocd\st_scripts` |
| host.docker.internal | `192.168.65.254`（Docker Desktop gateway） |
| GDB wrapper | `~/.local/bin/arm-none-eabi-gdb-wrapper.sh` |

### 關鍵設定檔位置

| 檔案 | 用途 |
|------|------|
| `.vscode/launch.json` | Cortex-Debug 設定，含 gdbPath/gdbTarget（已移除 runToEntryPoint，手動設斷點）|
| `.vscode/tasks.json` | `nucleo-h743: wait-openocd` task |
| `boards/st/nucleo-h743/wait_openocd.sh` | 偵測/觸發 OpenOCD |
| `boards/st/nucleo-h743/relay_server.ps1` | Windows Relay（Task Scheduler 自動啟動）|
| `boards/st/nucleo-h743/start_openocd.ps1` | 手動啟動 OpenOCD（備用）|

---

## [2026-05-23 18:30] F5 自動 Build：tasks.json 加入 build 前置依賴

- **問題描述**：每次 F5 偵錯前必須手動執行 `make st_nucleo-h743_default`，容易忘記，導致燒的是舊韌體。
- **原因分析**：`nucleo-h743: wait-openocd` task 沒有依賴 build task，F5 直接跳到等待 OpenOCD 再燒錄。
- **處理方式**：
  在 `.vscode/tasks.json` 的 `nucleo-h743: wait-openocd` task 加入：
  ```json
  "dependsOn": ["nucleo-h743: build"],
  "dependsOrder": "sequence",
  ```
  F5 新流程：
  1. `nucleo-h743: build` → `make st_nucleo-h743_default`（自動編譯）
  2. `nucleo-h743: wait-openocd` → 等 OpenOCD TCP:3333 就緒
  3. GDB 連線 → 燒錄 → 開始偵錯

---

## [2026-05-23 07:30] 啟動 Nucleo-H743 + MPU6050 的板級移植 (Board Porting)
- **目標**：為了深入了解 NuttX 與 PX4 驅動架構，改用 ST Nucleo-H743 開發板加上外接 MPU6050 模組，從零開始進行 PX4 板級移植 (Bring-up)。
- **修改與處理方式 (實作規劃)**：
  1. **建立板級資料夾**：在 PX4 原始碼的 `boards/st/` 目錄下建立 `nucleo-h743` 資料夾。
  2. **配置編譯檔**：新增並修改 `board.cmake`, `default.px4board`, `defconfig`, `board_config.h` 等核心檔案，讓 PX4 的 CMake 系統能辨識這塊板子。
  3. **Console 輸出設定**：在 NuttX 的 `defconfig` 中，將 Serial Console 指向 `USART3` (這對應 Nucleo 板上 ST-Link 提供的虛擬 COM 腳位 PD8/PD9)。設定 115200 Baudrate，確保開機能看見 `nsh>` 終端機。
  4. **感測器驅動掛載**：
     - 硬體接線：將 MPU6050 的 SDA/SCL 接到板子的 I2C1 (PB8/PB9)。
     - 軟體指令：在 `nsh>` 終端機下，先用 `i2c dev 1 0x68` 掃描硬體，確認連線後，手動輸入 `mpu6000 start -X -b 1` 啟動驅動，最後用 `listener sensor_accel` 驗證數據是否正常輸出。

---

## [2026-05-23 17:00] 新增 LD3 紅燈 + led_chaser 跑馬燈模組

### 問題描述
Phase 1 板級移植只定義了 LD1（綠）和 LD2（黃），Nucleo-H743ZI2 上的 LD3（紅，PB14）
未被納入 GPIO 初始化清單，無法在程式碼中控制。
另外需要一個可從 NSH 下指令的跑馬燈工具，用於確認開發板三顆 LED 均正常運作。

### 原因分析
- `board_config.h` 缺少 `GPIO_LED_RED` 和 `BOARD_LED_RED` 定義
- `led.c` 的 `g_ledmap[]` 只有兩個元素，索引 2 存取會越界
- `init.c` 原有 blocking for-loop 跑馬燈不符合 PX4 架構（佔用 boot 流程）

### 處理方式

**1. `boards/st/nucleo-h743/src/board_config.h`**：
新增 LD3 GPIO 定義及 PX4_GPIO_INIT_LIST 第三個元素：
```c
#define GPIO_LED_RED  /* PB14 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTB|GPIO_PIN14)
#define BOARD_LED_RED  2
#define PX4_GPIO_INIT_LIST { GPIO_LED_GREEN, GPIO_LED_YELLOW, GPIO_LED_RED, }
```

**2. `boards/st/nucleo-h743/src/led.c`**：
`g_ledmap[]` 新增第三項 `GPIO_LED_RED`（index 2）。

**3. `boards/st/nucleo-h743/src/init.c`**：
移除開機時的 blocking for-loop 跑馬燈，改為只點亮綠燈：
```c
drv_led_start();
led_on(BOARD_LED_GREEN);
```

**4. `boards/st/nucleo-h743/src/led_chaser.cpp`**（新增）：
以 PX4 正規模組架構實作（`ModuleBase<T>` + `ScheduledWorkItem`），
跑在 work queue（lp_default），不佔用獨立 task stack：
```
led_chaser start   → LD1(綠)→LD2(黃)→LD3(紅) 每 300ms 循環
led_chaser stop    → 停止，恢復綠燈常亮
led_chaser status  → 顯示執行狀態
```

**5. `boards/st/nucleo-h743/src/CMakeLists.txt`**：
新增 `px4_add_module()` 區塊，將 led_chaser 編譯為可由 NSH 呼叫的模組。

### 使用方式（燒錄後）

在 PuTTY（COM6, 115200）連上 NSH 後執行：
```
nsh> led_chaser start    # 開始跑馬燈
nsh> led_chaser stop     # 停止（恢復綠燈）
nsh> led_chaser status   # 查詢狀態
```

---

## [2026-05-23 17:30] 修正 GDB wrapper（read 改為 threaded pump，解決 Stop 鍵卡住）

### 問題描述
偵錯時按下 Stop（紅色正方形）無反應，GDB 程序持續佔用，只能從外部 kill。

### 原因分析
GDB wrapper 使用 `proc.stdout.read(4096)` 單執行緒讀取，當 GDB 等待訊號時
`read()` 阻塞，`SIGTERM`/`SIGINT` 未能及時傳入 GDB 子程序。

### 處理方式
將 stdout pump 改為 daemon thread（`threading.Thread`），主執行緒專責
`proc.wait()` 和訊號轉發：
```python
def pump():
    while True:
        chunk = proc.stdout.read(256)
        if not chunk: break
        sys.stdout.buffer.write(chunk.replace(b'8.3.1', b'9.3.1'))
        sys.stdout.buffer.flush()
t = threading.Thread(target=pump, daemon=True)
t.start()
proc.wait()
t.join(timeout=2)
```
換電腦後需重新建立 `~/.local/bin/arm-none-eabi-gdb-wrapper.sh`（見上方「容器內一次性設定」）。

---

## [2026-05-23 13:00] 新增 MPU6050 I2C 驅動（從零建立 PX4 標準驅動架構）

### 問題描述
MPU6050 是 I2C-only 的 IMU，但 PX4 原本的 `mpu6000` 驅動只支援 SPI
（`BusCLIArguments{false, true}`），無法直接使用。需要從零依照 PX4 架構建立新驅動。

### 建立的檔案清單

```
src/drivers/imu/invensense/mpu6050/
├── InvenSense_MPU6050_registers.hpp   # 暫存器定義、bit 常數、SensorData 結構
├── MPU6050.hpp                         # 類別宣告（device::I2C + I2CSPIDriver<T>）
├── MPU6050.cpp                         # RunImpl() 狀態機、資料讀取與轉換
├── mpu6050_main.cpp                    # NSH 指令入口
├── CMakeLists.txt                      # px4_add_module 定義
└── Kconfig                             # menuconfig 選項
```

同時修改的現有檔案：
- `src/drivers/drv_sensor.h`：新增 `DRV_IMU_DEVTYPE_MPU6050 0x90`
- `boards/st/nucleo-h743/default.px4board`：
  改為 `CONFIG_DRIVERS_IMU_INVENSENSE_MPU6050=y`

### 遭遇的建置問題與修復

**問題一：`VIRTUAL_ENV=/usr` 導致 Python 路徑錯誤**

- 原因：Docker 容器設定 `VIRTUAL_ENV=/usr`，頂層 `Makefile` 因此設定
  `PYTHON_EXECUTABLE=/usr/bin/python`（此路徑不存在），
  並以 `-DPYTHON_EXECUTABLE=` 傳給 cmake，覆蓋了 cmake 自動偵測的 `/usr/bin/python3`。
  每次 cmake reconfigure（例如修改 `default.px4board`）都會觸發此問題。
- 修復：`Makefile` 第 168 行改為 `PYTHON_EXECUTABLE ?= $(VIRTUAL_ENV)/bin/python3`

**問題二：`undefined reference to 'px4_spi_buses'`（linker 順序問題）**

- 原因：`platforms/common/i2c_spi_buses.cpp`（在 `libpx4_platform.a`）
  無論有無使用 SPI 都會引用 `px4_spi_buses`。
  此符號定義在 `boards/st/nucleo-h743/src/spi.cpp`（`libdrivers_board.a`）。
  但 linker 在處理 `libdrivers_board.a` 時，沒有人先要求 `px4_spi_buses`，
  所以 `spi.cpp.obj` 未被提取。之後 `libpx4_platform.a` 需要該符號時，
  `libdrivers_board.a` 已經過了，找不到 → undefined reference。
- 修復：`boards/st/nucleo-h743/src/CMakeLists.txt` 新增：
  ```cmake
  target_link_options(drivers_board INTERFACE -Wl,--undefined=px4_spi_buses)
  ```
  `-Wl,--undefined=X` 強制 linker 預設「有人需要 X」，
  使 `spi.cpp.obj` 在遇到 `libdrivers_board.a` 時就被提取進最終 ELF。

### 結果
`st_nucleo-h743_default.elf` 與 `.bin` 成功產生，Flash 使用約 237 KB（11.31%）。
MPU6050 驅動已編入韌體。

### 上板驗證（2026-05-23）

NSH 正確啟動指令（須加 `-X` 指定外部 I2C bus）：
```
nsh> mpu6050 start -X -b 1 -a 0x68
mpu6050 #0 on I2C bus 1 (external) address 0x68
```

資料確認：
```
nsh> listener sensor_accel 5
    device_id: 9463817 (Type: 0x90, I2C:1 (0x68))
    x: -7.05571  y: 5.89333  z: -3.09451   # 合力 ≈ 9.7 m/s² ≈ g（板子斜放）
    temperature: 25.49°C
    error_count: 0

nsh> listener sensor_gyro 5
    x: -0.047  y: 0.051  z: 0.039 rad/s    # 靜置接近 0
    error_count: 0

nsh> mpu6050 status
    Running on I2C Bus 1, Address 0x68
    read: 3360 events, 1581us avg           # 100 Hz 取樣，無通訊錯誤
    comm_err: 0 / bad_reg: 0
```

**整條鏈路完全驗證：I2C 接線 → 暫存器讀寫 → 單位換算 → uORB 發布，全部正常。**

### 注意：`-X` 旗標不可省略
`i2c.cpp` 將 I2C1 定義為 `initI2CBusExternal(1)`，
所以啟動指令必須用 `-X`（外部 I2C）而不是 `-I`（內部）或單獨 `-b 1`。
省略 bus type 旗標會得到 `ERROR [SPI_I2C] need to specify a bus type`。

---

## [2026-05-23 13:30] 修復 F5 燒錄失敗：Error erasing flash with vFlashErase packet

### 問題描述
按 F5 後 GDB 連上 OpenOCD，但燒錄時出錯：
```
[stm32h7x.cm7] Only resetting the Cortex-M core, use a reset-init event handler
to reset any peripherals or configure hardware srst support.
timed out while waiting for target halted
TARGET: stm32h7x.cm7 - Not halted
Error erasing flash with vFlashErase packet (from target-download)
```
每次 F5 穩定重現，兩次 `monitor reset halt`（一次來自 `preLaunchCommands`，
一次來自 Cortex-Debug 內部）都失敗，CPU 未 halt，flash erase 無法進行。

### 原因分析

**根本原因：OpenOCD 的 STM32H7 變數必須在載入 `stm32h7x.cfg` 之前設定**

`stm32h7x.cfg` 在被 `-f` 載入時會讀取以下 Tcl 變數：
- `CONNECT_UNDER_RESET`：若設為 1，cfg 自動執行 `reset_config srst_only srst_nogate`，
  並在 `init` 時用 NRST 保持 CPU 在 reset 狀態下建立 SWD 連線，確保 halt 成功
- `ENABLE_LOW_POWER`：允許從低功耗模式喚醒後再 halt
- `STOP_WATCHDOG`：凍結 IWDG/WWDG 計時器，防止 watchdog 在 reset-halt 間隙觸發

之前的 `relay_server.ps1` 把 `reset_config srst_only srst_nogate` 放在
stm32h7x.cfg **之後**，cfg 內部的 CONNECT_UNDER_RESET 機制沒有被觸發。
PX4 韌體跑起來後啟用了 watchdog，每次 SYSRESETREQ 後 watchdog 緊接著重置，
OpenOCD 來不及插入 halt → timeout → "Not halted"。

Cortex-Debug 在 `preLaunchCommands` 執行完後，內部還會再送一次 `monitor reset halt`，
所以每次有兩次 reset 嘗試，兩次都失敗。

### 處理方式

**修改 `C:\PX4\relay_server.ps1` 的 OpenOCD 啟動參數（順序很重要）：**

```powershell
# 舊（錯誤）
-f interface/stlink-dap.cfg
-c "set AP_NUM 0"
-f target/stm32h7x.cfg
-c "reset_config srst_only srst_nogate"   ← 太晚，cfg 已讀完
-c "adapter srst delay 100"
-c "init"
-c "reset halt"

# 新（正確）
-f interface/stlink-dap.cfg
-c "set AP_NUM 0"
-c "set CONNECT_UNDER_RESET 1"    ← 必須在 stm32h7x.cfg 之前
-c "set ENABLE_LOW_POWER 1"       ← 同上
-c "set STOP_WATCHDOG 1"          ← 同上
-f target/stm32h7x.cfg            ← cfg 讀到上述變數後自動設定 srst_only srst_nogate
-c "init"
-c "reset halt"
```

**relay_server.ps1 的更新方式（因 Docker 無法直接存取 Windows 路徑）：**
在 Windows PowerShell（管理員）貼上整段 heredoc 重建 `C:\PX4\relay_server.ps1` 再 `-Install`。

**同步更新 `launch.json` 的 preLaunchCommands（輔助保障）：**
```json
"preLaunchCommands": [
    "set mem inaccessible-by-default off",
    "set print pretty",
    "monitor reset halt"
]
```

### 結果
F5 燒錄成功，CPU 在 GDB 連線時已處於 halt 狀態（`0x00000000 in ?? ()`），
後續兩次 `monitor reset halt` 均正常，`target-download` 完成，韌體成功燒入。

### 換電腦注意事項
`relay_server.ps1` 存在 `C:\PX4\relay_server.ps1`（Windows 端），
不在 Git repo 的 Docker 路徑中。換電腦需重新貼上 PowerShell heredoc 安裝。
`boards/st/nucleo-h743/relay_server.ps1`（repo 內）是備份版本，內容保持同步。

---

## [2026-05-23 18:00] 移除 runToEntryPoint，解決 Failed to read memory 錯誤

### 問題描述
`launch.json` 設定 `"runToEntryPoint": "__start"` 後，燒錄成功，但 GDB 顯示：
```
Failed to read memory at 0xfffffffe
Failed to read memory at 0xffffffffe
```
偵錯 session 無法正常啟動。

### 原因分析
`0xFFFFFFFE` 是 ARM Cortex-M 的 **EXC_RETURN** 魔術值（從中斷返回用），
不是真正的記憶體位址。GDB 8.3.1（未修補版本）在處理 `runToEntryPoint` 時
會嘗試讀取這個值所指的記憶體，因而失敗。

### 處理方式
從 `launch.json` 的 `openocd-win (st_nucleo-h743)` 設定中
**移除** `"runToEntryPoint"` 欄位。

偵錯時若需停在起點，在 GDB 連上後手動於 Debug Console 輸入：
```
break __start
monitor reset halt
continue
```
或在 `__start`（`stm32_start.c:188`）行號設定中斷點後再按 F5。

---

## [2026-05-23 21:00] 建立 MPU6050 姿態視覺化 GUI 工具

### 問題描述
MPU6050 感測器已驗證可正常讀取（100Hz，|g|≈9.7 m/s²），但資料只能在 NSH 終端機以文字呈現，無法直觀判斷姿態。

### 原因分析
需要一個獨立工具，能：
1. 從 USB VCOM（NSH）接收 PX4 `listener sensor_accel/gyro` 輸出
2. 以視覺化方式即時顯示 roll / pitch 姿態
3. 保留可互動的 NSH 指令輸入能力

### 處理方式
建立 `tool/mpu6050_viewer.py`（Python 3 + tkinter + pyserial + Pillow）：

**UART 連線面板：**
- 下拉選單列出所有 COM port，格式 `COM3  [Silicon Labs CP210x USB to UART Bridge]`（port 名稱 + 裝置描述）
- 鮑率選擇（9600 ~ 921600），預設 57600
- ⟳ 重新整理按鈕 / Connect|Disconnect 按鈕
- 狀態指示（紅色斷線 / 綠色已連線 + port 名稱）

**人工地平線（FPV 視角）：**
- 圓形顯示區，使用 PIL 進行像素級繪製（含 circular clip mask）
- 天空（藍）/ 地面（棕）依 roll/pitch 旋轉平移
- 白色地平線、pitch 刻度線（±10°/±20°/±30°）
- 滾轉弧形刻度（每 10°）+ 金色滾轉指針三角形
- 固定的金色飛機符號（雙翼 + 中心點）
- 加速度計姿態計算：
  - Roll  = atan2(ay, az)
  - Pitch = atan2(-ax, √(ay²+az²))

**姿態數值面板：**
- Roll / Pitch（度，±.1f）
- 加速度計 X/Y/Z（m/s²，±.4f）
- 陀螺儀 X/Y/Z（rad/s，±.4f）

**訊息記錄區：**
- 深色背景、等寬字型，自動捲動至最新行
- Copy 按鈕（複製全部內容到剪貼簿）/ Clear 按鈕
- 行數超過 3000 行自動裁切，避免記憶體無限成長

**NSH 指令輸入：**
- 文字輸入框 + Send 按鈕（Enter 也可送出）
- 送出格式：`cmd\r\n`

**資料解析 (`Parser` class)：**
- 支援 inline 格式：`sensor_accel: x:-7.05, y:5.89, z:-3.09`
- 支援 verbose listener 格式（多行 x:/y:/z:）
- 20 Hz UI 更新（`after(50, poll)`）

**使用說明（Windows）：**
```
pip install pyserial Pillow
python tool\mpu6050_viewer.py
```
連線後在輸入框輸入：
```
listener sensor_accel -n 1000
```
地平線即開始即時更新。

---

## [2026-05-23 22:00] F5 燒錄失敗：`monitor reset halt` 逾時 → 加 `reset_config srst_only`

> **這個問題會反覆出現**，每次 relay_server.ps1 重裝或 OpenOCD 重啟後都可能復發。
> 本節是永久修復，已寫入 `launch.json`，不需再改 Windows 端設定。

### 問題描述
按 F5 後 GDB 連上（PC=0x00000000，晶片已暫停），但隨即出現：
```
[stm32h7x.cm7] Only resetting the Cortex-M core, ...
timed out while waiting for target halted
TARGET: stm32h7x.cm7 - Not halted
Error erasing flash with vFlashErase packet
```

### 原因分析
`monitor reset halt` 預設使用 **VECTRESET**（僅重置 Cortex-M7 核心），不重置 D1/D2/D3 電源域與周邊。重置後 bus 仍有殘留狀態，DAP 無法在逾時內完成 halt。

根本原因：`CONNECT_UNDER_RESET 1` 的 Tcl 變數需在 `-f target/stm32h7x.cfg` **載入前**設定，若 OpenOCD 以舊參數啟動（relay_server.ps1 未正確安裝），此變數不生效，reset_config 也不會設為 `srst_only`。

同樣現象但不同嚴重度：
- 前次（更嚴重）：`Fail reading CTRL/STAT register` + `DP initialisation failed` → IWDG 重置導致 DAP 斷線
- 本次（較輕）：`timed out while waiting for target halted` → DAP 可存取但 halt 等待逾時

### 處理方式（已永久修復於 `launch.json`）

在 `.vscode/launch.json` 的 `openocd-win (st_nucleo-h743)` → `preLaunchCommands` 中，
於 `monitor reset halt` **之前**加入：
```json
"monitor reset_config srst_only srst_nogate"
```

完整 `preLaunchCommands`：
```json
"preLaunchCommands": [
    "set mem inaccessible-by-default off",
    "set print pretty",
    "monitor reset_config srst_only srst_nogate",
    "monitor reset halt"
]
```

`srst_only` = 之後所有 reset 都用 NRST（硬體腳，完整 system reset）
`srst_nogate` = reset 期間不關閉 SWD clock，DAP 仍可存取

此修法**不依賴** relay_server.ps1 是否正確，每次 GDB 連線時直接從 GDB 側設定 OpenOCD 的 reset 模式。

### 備忘：relay_server.ps1 的正確參數（Windows 端）

若需重裝 `C:\PX4\relay_server.ps1`，OpenOCD 的啟動參數必須是：
```
-f interface/stlink-dap.cfg
-c "set AP_NUM 0"
-c "set CONNECT_UNDER_RESET 1"   ← 必須在 target 前
-c "set ENABLE_LOW_POWER 1"      ← 必須在 target 前
-c "set STOP_WATCHDOG 1"         ← 必須在 target 前
-f target/stm32h7x.cfg
-c "init"
-c "reset halt"
```
三個 `set` 指令必須在 `-f target/stm32h7x.cfg` **之前**，因為 stm32h7x.cfg 在載入時就讀取這些 Tcl 變數。
