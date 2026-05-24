# PX4 實作與除錯學習筆記

---

## 學習準則（此檔的使用規則）

1. **此檔記錄什麼**：觀念說明、架構解析、除錯原理、名詞定義、技術背景。
   簡單說：「為什麼這樣設計」、「這個東西是什麼」都在這裡。
2. **此檔不記錄什麼**：具體的改了哪個檔案、遇到什麼錯誤、怎麼修好的。
   那些屬於「操作日誌」，請記在 `Study/devlog.md`。
3. **新增章節格式**：
   ```
   ## N. 章節標題
   - **概念說明：** ...
   - **原始碼位置：** ...（若適用）
   - **實作方式：** ...
   - **常見坑：** ...（若有踩過）
   ```
4. **編號規則**：章節以流水號遞增；若只是補充某章節，在原章節下加小節即可，不新增頂層章節號。
5. **語言**：全程繁體中文。

---

## 1. PX4 更新與驗證流程
- 如何確認本地 PX4 是否為官方最新版：
  - 比對 `main` 與 `origin/main` commit SHA 與 ahead/behind 數。
  - 若落後，需 `git pull --ff-only` 並同步 submodules。
- 如何驗證更新後可正常運作：
  - 先跑一次 build（如 `make px4_sitl_default`）。
  - 再啟動 SITL（如 `make px4_sitl gz_x500`），確認能進入 shell 並與模擬器連線。

## 2. 板級移植（board port）是什麼？
- 讓 PX4 能在新硬體板（如 NUCLEO-H743）上開機、跑起來、控制周邊。
- 需定義：
  - CPU/時脈/記憶體/啟動腳位/中斷等底層硬體資訊
  - UART/I2C/SPI/CAN、PWM、ADC、LED、按鍵、儲存裝置等 pin/bus 對應
  - 建立該板的編譯與燒錄目標
- 沒有 board port，PX4 不知道怎麼初始化你的板，通常會卡在開機或外設全失效。

## 3. Pixhawk 6C vs NUCLEO-H743 實作建議
- **建議先用 Pixhawk 6C 直接 debug**：
  - PX4 官方支援，編譯、燒錄、感測器、參數都成熟
  - 可以專注在功能驗證與除錯，不會被硬體 bring-up 問題卡住
- NUCLEO-H743 適合：
  - 你要做 PX4 新板移植、驗證自製載板、或練習平台 bring-up
  - 需投入大量時間在移植與硬體 bring-up

## 4. 目前已建立的學習筆記與日誌
- Study/learn.md（本檔案）
- Study/devlog.md（開發與除錯日誌：記錄實作問題與處理方式）

## 5. PX4 核心軟體架構與控制流 (Developer Deep-Dive)

PX4 採用微核心架構，模組間透過 **uORB** (Publish/Subscribe) 通訊。為了即時性，控制迴路多透過 `WorkQueue` 以中斷或計時器驅動（而非傳統 Sleep 迴圈）。

完整的閉迴路控制 (Closed-loop Control Flow) 包含 6 大階段。以下以「多旋翼 (Multicopter)」為例進行深度剖析：

### 1. 感測層 (Sensor Drivers & Aggregation)
- **理論說明：** 讀取硬體 ADC/SPI/I2C 暫存器，將原始電壓或數位訊號轉換為 SI 單位 (m/s², rad/s)，並套用溫度補償、低通濾波 (Low-pass Filter) 與出廠校正參數。
- **原始碼位置：** `src/drivers/` (各別硬體) 及 `src/modules/sensors/` (資料聚合)。
- **實作方式：**
  底層 Driver 在硬體中斷 (Data Ready) 觸發時讀取資料，發布 `sensor_accel` 等 Topic。`sensors` 模組透過 `WorkQueue` 訂閱這些資料，進行頻率對齊與降採樣 (Downsampling)，最終打包發布高頻率的聚合數據。
- **Topic 輸入/輸出：**
  - **Out:** `sensor_combined` (包含陀螺儀與加速度計，通常為 250Hz~1kHz), `vehicle_gps_position`, `sensor_baro`。
- **實例：** Pixhawk 6C 內的 ICM-42688-P 產生硬體中斷，Driver 透過 SPI 讀取暫存器，轉換後發布，`sensors` 模組將其與氣壓計封裝成 `sensor_combined` 提供給估測器。

### 2. 估測層 (Estimator - EKF2)
- **理論說明：** 採用 **擴展卡爾曼濾波器 (EKF, Extended Kalman Filter)**。
  - **Predict (預測步):** 利用高頻 IMU 數據（積分）透過運動學方程式預測當前姿態與速度。
  - **Update (更新步/校正):** 利用低頻但絕對精準的 GPS/氣壓計/視覺里程計，計算測量殘差 (Innovation)，乘上卡爾曼增益 (Kalman Gain) 來修正預測結果，並估計 IMU 的零偏 (Bias)。
- **原始碼位置：** `src/modules/ekf2/` (介面包裝) 以及 `src/lib/ecl/` (核心數學演算法庫)。
- **實作方式：** 是一個高度複雜的狀態機。它維護一個 24 維的狀態向量（四元數姿態、速度、位置、陀螺儀 bias、加速度計 bias、地磁等），並處理各種感測器的時間延遲 (Time delay compensation)。
- **Topic 輸入/輸出：**
  - **In:** `sensor_combined`, `vehicle_gps_position`, `sensor_mag`, `vehicle_air_data`。
  - **Out:** `vehicle_attitude` (當前真實姿態), `vehicle_local_position` (NED 座標系位置), `vehicle_global_position` (經緯度)。
- **實例：** 飛機在空中被風吹動。IMU 感受到加速度變化，EKF 立刻預測飛機發生位移。0.2秒後 GPS 數據抵達，證實了位移，EKF 更新其協方差矩陣，發布精確的 `vehicle_local_position`。

### 3. 導航與決策 (Navigator & Commander)
- **理論說明：** 處理高階邏輯。
  - **Commander:** 狀態機 (State Machine)，負責處理解鎖 (Arming)、安全檢查 (Pre-flight checks)、飛行模式切換 (Auto/Manual/RTL)。
  - **Navigator:** 路徑規劃 (Path Planning)。根據當前任務 (Mission)，使用 L1 Navigation 或純幾何運算，計算下一時刻飛機「應該去哪裡」。
- **原始碼位置：** `src/modules/commander/`, `src/modules/navigator/`。
- **實作方式：** 運行在低頻率 (通常 10Hz - 50Hz) 的 `WorkQueue`。Navigator 會讀取存放在 SD 卡的 Mission items，產生軌跡目標。
- **Topic 輸入/輸出：**
  - **In:** `vehicle_local_position`, `rc_channels`, `vehicle_command` (來自 QGC 地面站)。
  - **Out:** `trajectory_setpoint` (期望到達的三維位置 XYZ 與速度 Vx,Vy,Vz)。
- **實例：** 無人機處於 Auto Mission 模式，準備飛向 100 公尺外的航點 (Waypoint 2)。Navigator 計算出巡航速度為 5 m/s，並發布 `trajectory_setpoint`，指示期望向北移動 5m/s。

### 4. 位置控制器 (Position Controller)
- **理論說明：** **串級 PID 控制 (Cascaded PID)**。
  - **外迴路 (P 控制):** 位置誤差 (Position Error) $\to$ 期望速度 (Target Velocity)。
  - **內迴路 (PID 控制):** 速度誤差 (Velocity Error) $\to$ 期望加速度 (Target Acceleration) / 期望推力。
  - **傾角映射:** 根據期望的三軸推力向量，利用三角函數算出無人機需要「傾斜多少角度」才能產生該水平分力。
- **原始碼位置：** `src/modules/mc_pos_control/` 及 `src/lib/PositionControl/`。
- **實作方式：** 當 `vehicle_local_position` 更新時觸發運行 (約 50Hz - 250Hz)。使用 NED (北東地) 座標系運算。
- **Topic 輸入/輸出：**
  - **In:** `vehicle_local_position` (實際), `trajectory_setpoint` (期望)。
  - **Out:** `vehicle_attitude_setpoint` (期望的 Roll, Pitch, Yaw 角度與總推力 Thrust)。
- **實例：** 飛機目前高度 10m，期望高度 20m。Z 軸外迴路 P 控制器計算出需要上升速度 +3 m/s。Z 軸內迴路 PID 發現當前速度 0 m/s，故輸出增加 Z 軸推力 (Thrust = 0.8)；同時計算出需前進 5m/s，所以推算期望 Pitch 角度為 -15度 (機頭朝下)。

### 5. 姿態與角速度控制器 (Attitude & Rate Controller)
- **理論說明：** PX4 穩定飛行的最核心，同樣是 **串級 PID**。
  - **外迴路 (Attitude, P 控制):** 計算期望姿態 (四元數) 與當前姿態的角誤差 $\to$ 輸出「期望角速度 (Target Angular Rate)」。
  - **內迴路 (Rate, PID 控制):** 比較期望角速度與陀螺儀讀數 $\to$ 輸出「期望力矩 (Target Torque)」。
- **原始碼位置：** `src/modules/mc_att_control/` 及 `src/modules/mc_rate_control/`。
- **實作方式：** **極高頻執行**！通常被綁定在 IMU 資料更新的回呼 (Callback) 中，與陀螺儀同步 (250Hz - 1000Hz)，因為稍微的延遲都會導致飛機震顫。四元數運算被大量應用以避免萬向鎖 (Gimbal Lock)。
- **Topic 輸入/輸出：**
  - **In:** `vehicle_attitude` (實際姿態), `vehicle_attitude_setpoint` (期望姿態), `sensor_gyro` (高頻實際角速度)。
  - **Out:** `vehicle_torque_setpoint` (期望力矩: Roll, Pitch, Yaw), `vehicle_thrust_setpoint` (期望推力)。
- **實例：** `vehicle_attitude_setpoint` 要求 Pitch = -15度。當前 Pitch = 0度。外迴路 P 控制器輸出期望 Pitch Rate 為 -45度/秒。內迴路發現當前陀螺儀 Pitch Rate 為 0，因此 PID 中的 P term 和 D term 產生一個強烈的負向力矩指令 (Torque_Y = -0.5)。

### 6. 控制分配與混控 (Control Allocation / Mixer)
- **理論說明：** **幾何矩陣運算 (Geometry Matrix)**。
  抽象的 3 軸力矩與 1 個推力 (Roll, Pitch, Yaw, Z-Thrust)，要如何分配給機架上的 N 顆馬達？
  藉由機架的幾何定義（馬達安裝位置、旋轉方向），建立分配矩陣 (Allocation Matrix) 並求偽逆矩陣 (Pseudo-inverse)，將 Torque/Thrust 轉換為各馬達的推力量。
- **原始碼位置：** `src/modules/control_allocator/` (現代 PX4 架構，取代了舊的 mixer 腳本)。
- **實作方式：** 收到力矩指令後立刻計算，並處理飽和 (Saturation) 問題——例如當某顆馬達需要輸出 110% 才能滿足力矩時，該如何優先保證姿態穩定而犧牲高度控制。
- **Topic 輸入/輸出：**
  - **In:** `vehicle_torque_setpoint`, `vehicle_thrust_setpoint`。
  - **Out:** `actuator_motors` (正規化 0~1 的馬達轉速指令)。
- **實例：** X型四軸無人機收到 (Torque_Y = -0.5) 的低頭指令與 (Thrust = 0.8) 的懸停指令。Control Allocator 計算後，指令前方的兩顆馬達降低轉速 (例如 0.6)，後方的兩顆馬達提高轉速 (例如 1.0)，產生低頭的物理力矩。最終數據由 DShot 或 PWM 驅動程式送往電調 (ESC)。

## 6. uORB (Micro Object Request Broker) 機制解析
- **概念：** PX4 的「神經網路」，採用**非同步的發布/訂閱 (Publish/Subscribe)** 模型。
- **運作方式：**
  - **Topic (主題):** 資料的通道，由 `.msg` 檔案定義資料結構。
  - **Publisher (發布者):** 負責產生資料並發布到 Topic 上（例如：感測器驅動發布 `sensor_accel`）。發布者不需要知道有誰在聽。
  - **Subscriber (訂閱者):** 負責從 Topic 讀取資料（例如：EKF2 訂閱 `sensor_accel`）。訂閱者不需要知道資料是誰發的。
- **優點：**
  - **極度解耦：** 模組之間互不依賴，你可以隨時抽換掉某個模組（例如用你自己寫的位置控制器取代系統預設的），只要輸入輸出的 Topic 對得上，系統就能正常運作。
  - **多實例 (Multi-instance)：** 支援同一個 Topic 有多個來源，例如飛機上有三顆 GPS，可以同時發布到 `sensor_gps` 的 instance 0, 1, 2，再由估測器決定要如何融合。

## 7. 硬體除錯與燒錄 (SWD vs Bootloader)

### 記憶體配置與破壞風險
在微控制器 (如 STM32H7) 中，Flash 記憶體分為兩塊：
1. **起點 (如 `0x08000000`)**：存放 **Bootloader**。負責初始化硬體、提供 USB 燒錄介面 (DFU/Serial)。
2. **偏移後位址 (如 `0x08020000`)**：存放 **PX4 應用程式 (APP FW)**。

一般使用 USB (QGroundControl) 升級韌體時，Bootloader 只會覆寫 APP FW 區段，因此很安全。但若使用 **Pixhawk Debug Adapter (SWD 介面)** 進行硬體級別的燒錄或除錯，燒錄軟體預設的 **全晶片抹除 (Mass Erase)** 會將 Bootloader 一併刪除，導致飛控插上 USB 後毫無反應。

### 災後還原流程 (Restoration Flow)
若因為 SWD 燒錄導致 Bootloader 遺失，需依序進行以下還原：
1. **透過 SWD 燒錄 Bootloader**：
   使用 Pixhawk Debug Adapter 與燒錄軟體 (如 STM32CubeProgrammer 或 J-Link)，將編譯好的 Bootloader `.bin` 檔燒入 Flash 起點 (`0x08000000`)。
2. **透過 USB 燒錄 APP FW**：
   拔除 Debug Adapter，重新連接 USB 線。此時電腦應能辨識到飛控的 Bootloader，接著使用 `make <target> upload` 或 QGroundControl 燒錄一般的 PX4 韌體。

*開發技巧：* 許多除錯器允許設定為「**Sector Erase (區塊抹除)**」而非 Mass Erase。若設定正確，只會抹除 APP FW 所在的區塊，這樣使用 SWD 除錯時就能完整保留 Bootloader。

## 8. PX4 Board Porting: Nucleo-H743 + MPU6050 實戰
要在「PX4 的架構下」建立一塊全新的硬體板（Board Porting），我們必須遵守 PX4 的編譯系統（CMake）與板級定義結構。
這能讓你完整摸透 PX4 是如何把 NuttX 底層與上層飛行控制邏輯結合在一起的。

### Phase 1: 建立 PX4 Board 資料夾結構
- **目標：** 讓 PX4 的 `make` 系統能認得這塊新板子。
- **作法：**
  - 在 `boards/` 下建立供應商與板子名稱的資料夾：`boards/st/nucleo-h743/`。
  - **必備檔案：**
    1. `board.cmake`：定義 CPU 型號 (STM32H743ZI)、架構、Bootloader 預留空間、以及要編譯的原始碼。
    2. `default.px4board`：設定要將哪些 PX4 模組（如 `sensors`, `ekf2`, `mpu6000`）編譯進這塊板子。
    3. `nuttx-config/default/defconfig`：NuttX 的底層 Kconfig 設定（啟用 UART3、I2C1 等）。
    4. `src/board_config.h`：定義腳位 (Pin Muxing)，例如 I2C1_SCL, I2C1_SDA, USART3_TX 等硬體腳位配置。

### Phase 2: 基礎燒錄、編譯與 UART (NSH 終端機)
- **目標：** 成功編譯出 `.elf`，透過 ST-Link 燒錄，並在電腦上看到 `nsh>`。
- **作法：**
  - 執行編譯指令：`make st_nucleo-h743_default`。
  - 編譯出的檔案會位於 `build/st_nucleo-h743_default/st_nucleo-h743_default.elf`。
  - Nucleo 內建 ST-Link，透過 Micro-USB / Type-C 連接電腦。
  - 使用 OpenOCD 或 STM32CubeProgrammer 透過 SWD 介面將 `.elf` 直接燒錄至 Flash 起點 (`0x08000000`)。
  - ST-Link 內建 Virtual COM Port，硬體連接著 H743 的 USART3 (PD8/PD9)。設定好後，打開 PuTTY (115200 8N1)，開機應能看見 `nsh>` 提示字元。

### Phase 3: 在 PX4 掛載 MPU6050 I2C 驅動
- **目標：** 讓 PX4 的感測器模組能讀到外部 MPU6050 的資料。
- **作法：**
  - 硬體接線：將 MPU6050 接至 Nucleo 上對應的 I2C1 腳位 (如 PB8=SCL, PB9=SDA)，並接上 3.3V 與 GND。
  - 確認 `default.px4board` 中有加入 `CONFIG_DRIVERS_IMU_INVENSENSE_MPU6000=y`（PX4 通常用 MPU6000 驅動來相容 MPU6050）。
  - 進入 NSH 後，使用 I2C 掃描工具確認硬體：`i2c dev 1 0x68`。
  - 手動啟動驅動程式：`mpu6000 start -X -b 1` (-X 代表外部匯流排, -b 1 代表 I2C Bus 1)。
  - 驗證 uORB 輸出：輸入 `listener sensor_accel`，若能看到持續跳動的加速度數據，代表硬體整合成功！

## 10. PX4 I2C 感測器驅動架構（以 MPU6050 為例）

### 為什麼 MPU6000 驅動不能直接用於 MPU6050 I2C？

PX4 原本的 `mpu6000` 驅動（`src/drivers/imu/invensense/mpu6000/`）使用
`BusCLIArguments{false, true}`——第一個參數 `false` = 不支援 I2C，
第二個 `true` = 只支援 SPI。MPU6050 是市面常見的 I2C 版本，必須另寫專屬驅動。

---

### PX4 I2C 驅動的標準類別繼承架構

```
class MPU6050 : public device::I2C,          ← 提供 I2C 低階通訊 (transfer)
                public I2CSPIDriver<MPU6050>  ← 提供模組生命週期管理 (RunImpl, module_start)
```

`device::I2C` 提供的核心方法：
- `transfer(tx_buf, tx_len, rx_buf, rx_len)` — 執行一次 I2C 傳輸

`I2CSPIDriver<T>` 提供的核心方法：
- `RunImpl()` — 週期性執行主邏輯（由 WorkQueue 呼叫）
- `module_start(cli, iterator)` / `module_stop(iterator)` / `module_status(iterator)`

---

### 驅動的五個核心檔案

| 檔案 | 說明 |
|------|------|
| `InvenSense_MPU6050_registers.hpp` | 暫存器位址、bit 定義、SensorData 結構 |
| `MPU6050.hpp` | 類別宣告、私有成員、靜態常數 |
| `MPU6050.cpp` | `RunImpl()` 狀態機邏輯、暫存器讀寫、資料轉換 |
| `mpu6050_main.cpp` | NSH 指令入口（`mpu6050 start/stop/status`）|
| `CMakeLists.txt` + `Kconfig` | 編譯系統整合 |

---

### RunImpl() 狀態機設計

```
RESET → (Reset PWR_MGMT_1, sleep 100ms) → WAIT_FOR_RESET
WAIT_FOR_RESET → (等 WHO_AM_I == 0x68) → CONFIGURE
CONFIGURE → (設定 GYRO_CONFIG, ACCEL_CONFIG, DLPF) → READ
READ → (14-byte burst read) → 轉換 + uORB publish → 排程下次 READ
```

- `RESET` → `WAIT_FOR_RESET`：寫入 `PWR_MGMT_1.DEVICE_RESET = 1`，等 100ms
- `WAIT_FOR_RESET` → `CONFIGURE`：讀 `WHO_AM_I`（0x68）確認通訊正常
- `CONFIGURE` → `READ`：設定陀螺儀/加速度計滿量程，CLKSEL=1（PLL）
- `READ` 迴圈：從 0x3B 連續讀 14 byte（ACCEL XYZ + TEMP + GYRO XYZ），
  每次 10 ms（100 Hz）用 `ScheduleDelayed(SAMPLE_INTERVAL_US)` 排程

---

### 資料流：硬體 → uORB

```
I2C 14-byte 原始資料（大端 int16）
    ↓ 合併高低位元組
int16_t accel_x/y/z, gyro_x/y/z
    ↓ 乘以比例因子
float (m/s²)  ACCEL_SCALE = 9.80665 / 16384（±2g 範圍）
float (rad/s) GYRO_SCALE  = π / (180 × 65.5)（±250°/s 範圍）
    ↓ PX4Accelerometer / PX4Gyroscope helper 呼叫
uORB topics: sensor_accel, sensor_gyro
```

---

### `BusInstanceIterator` 與空 SPI bus 的 linker 陷阱

PX4 的 `I2CSPIDriver` 使用 `BusInstanceIterator` 掃描所有可用的匯流排實例。
`BusInstanceIterator` 的實作（`platforms/common/i2c_spi_buses.cpp`）
**無論是否使用 SPI，都會引用全域符號 `px4_spi_buses`**。

這個符號定義在板級的 `src/spi.cpp`。問題在於：
- `libdrivers_board.a`（含 `spi.cpp.obj`）在 linker 命令中先出現
- 當 linker 處理 `spi.cpp` 時，沒有人先要求 `px4_spi_buses`，所以這個物件**不被提取**
- 之後 `libpx4_platform.a` 被處理，`i2c_spi_buses.cpp.obj` 才引用 `px4_spi_buses`
- 此時 linker 已經過了 `libdrivers_board.a`，找不到符號 → **undefined reference**

**解法**：在 `boards/st/nucleo-h743/src/CMakeLists.txt` 加：
```cmake
target_link_options(drivers_board INTERFACE -Wl,--undefined=px4_spi_buses)
```
`-Wl,--undefined=X` 讓 linker 「假裝有人需要 X」，強制從 archive 提取對應物件。

---

### NSH 啟動指令

```
nsh> mpu6050 start -b 1 -a 0x68   # I2C Bus 1, 位址 0x68
nsh> listener sensor_accel 5       # 看加速度計 5 筆
nsh> listener sensor_gyro 5        # 看陀螺儀 5 筆
nsh> mpu6050 status                # 看驅動狀態與 perf counters
nsh> mpu6050 stop                  # 停止驅動
```

---

### 常見坑

1. **WHO_AM_I 不對**：MPU6050 = 0x68，MPU6000 = 0x68，MPU9250 = 0x71。
   若接錯線或位址錯誤，WAIT_FOR_RESET 狀態會一直等，永遠進不了 CONFIGURE。

2. **大端轉小端**：I2C 讀回的資料是 Big-Endian，必須手動合併：
   ```cpp
   int16_t raw = (int16_t)((data[0] << 8) | data[1]);
   ```

3. **`DRV_IMU_DEVTYPE_MPU6050` 必須唯一**：
   `src/drivers/drv_sensor.h` 中每個 device type 常數不可重複。
   MPU6050 使用 `0x90`，但此值同時出現在 `DRV_ADC_DEVTYPE_ADS1115`，
   需選用真正空閒的值。

## 11. 姿態角計算原理與 Yaw 的限制

- **概念說明：** Roll 和 Pitch 可從加速度計的重力向量直接計算；
  Yaw 則無法從加速度計取得，原因是物理上的根本限制。

- **Roll / Pitch 計算：**
  ```
  Roll  = atan2(ay, az)
  Pitch = atan2(-ax, sqrt(ay² + az²))
  ```
  重力向量 `(ax, ay, az)` 的分量比值唯一決定了機體相對水平面的傾斜姿態。

- **為什麼沒有 Yaw：**
  Yaw 是繞「重力向量本身」旋轉的角度（即垂直軸旋轉）。
  無論怎麼轉 Yaw，重力向量方向不變，加速度計讀值完全相同。
  因此**加速度計在任何 Yaw 角下讀值一樣**，無法分辨。

- **取得 Yaw 的三種方法：**

  | 方法 | 說明 | 限制 |
  |------|------|------|
  | 磁力計 | 量地磁方向（Heading） | MPU6050 沒有；需 MPU9250 或外接 HMC5883L |
  | 陀螺儀積分 | 積分 Gyro Z 得到相對偏轉角 | 長時間漂移（drift），需週期校正 |
  | 感測器融合 EKF | Accel + Gyro + Mag + GPS 融合 | 需要完整飛控架構（PX4 EKF2） |

- **MPU6050 vs MPU9250：**
  - MPU6050：3 軸加速度計 + 3 軸陀螺儀（共 6 軸），無磁力計
  - MPU9250：MPU6050 基礎上加內建 AK8963 磁力計（共 9 軸），可算絕對 Yaw

- **實作位置：** `tool/mpu6050_viewer.py` 的 `Parser.feed()` 中，
  Roll/Pitch 用 `math.atan2()` 從加速度計即時計算；Yaw 欄位未實作，
  GUI 底部有說明文字 `* Yaw 需磁力計，MPU6050 不支援`。

---

## 9. HRT（High Resolution Timer）機制

- **概念說明：** `hrt_absolute_time()` 是 PX4 全域的微秒時鐘，幾乎所有模組都依賴它。
  它的實作位於 `platforms/nuttx/src/px4/stm/stm32_common/hrt/hrt.c`，
  由一顆專用的硬體計時器提供。
- **關鍵設計：** `hrt.c` 全部程式碼都被 `#ifdef HRT_TIMER` 包住。
  若 `board_config.h` 未定義 `HRT_TIMER`，這個檔案編譯出空物件，
  所有 `hrt_*` 符號都不存在，鏈結時出現大量 `undefined reference`。
- **移植時必須做的事：**
  ```c
  // 在 board_config.h 加入（以 STM32H743 用 TIM8 為例）
  #define HRT_TIMER         8   /* 使用 TIM8 */
  #define HRT_TIMER_CHANNEL 3   /* CC 通道 3 */
  ```
  選定的計時器**不可**同時在 defconfig 以 `CONFIG_STM32H7_TIMx=y` 啟用
  NuttX 的同名驅動，因為 HRT 會直接控制暫存器，兩者會衝突。
- **常見坑：** 把 HRT 計時器與 PWM 輸出計時器搞混。
  PWM 用 `timer_config.cpp` 設定（如 TIM1），HRT 用另一顆獨立的計時器。
  在 Nucleo-H743 上：TIM1 給 PWM，TIM8 給 HRT（與 CubeOrange 相同）。
