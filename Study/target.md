# 專案目標與開發路線圖

## 最終目標

自行設計飛控板取代 Holybro Pixhawk 6C，裝載於 X500 V2 機架，
運行 PX4 飛控韌體，實現完整自主飛行能力。

```
X500 V2 周邊  →  Nucleo-H743ZI2 驗證  →  自製飛控板  →  裝機飛行
```

---

## 開發策略

將 X500 V2 原接 Pixhawk 6C 的所有周邊，逐一改接到 Nucleo-H743ZI2 開發板驗證。
每個周邊確認 PX4 驅動正常後，才進入下一個。
全部驗通後，依據 Nucleo 上的實測接線畫電路圖、打樣自製板。

---

## 硬體對照

### 晶片差異

| 項目 | Pixhawk 6C | Nucleo-H743ZI2 | 自製板目標 |
|------|-----------|----------------|-----------|
| 晶片 | STM32H743IIK6 | STM32H743ZIT6 | STM32H743IIK6（同 6C）|
| 封裝 | UFBGA176 | LQFP144 | UFBGA176 |
| 差異 | PJ/PK port 可用 | PJ/PK 不可用 | 完整 176 pin |

> Nucleo 驗證階段使用 ZIT6（144 pin），自製板改回 IIK6（176 pin）可完整對齊 6C 腳位。

---

### X500 V2 周邊對應表

| 周邊 | Pixhawk 6C 接口 | 晶片 UART/外設 | Nucleo 腳位 | 狀態 |
|------|----------------|---------------|------------|------|
| SiK Telemetry Radio | TELEM1 | UART7 | PE8(TX) / PE7(RX) / PE10(CTS) / PE9(RTS) | 待做 |
| M9N GPS | GPS1 | UART4 | PD1(TX) / PD0(RX) | 待做 |
| GPS 羅盤 (IST8310) | GPS1 (I2C) | I2C1 | PB8(SCL) / PB9(SDA) | 待做（與 MPU6050 共 bus，位址 0x0E 不衝突）|
| RC 接收器 SBUS | RC IN | USART6 | PG9(RX) 硬體反相 | 待做 |
| ESC × 4 PWM | MAIN OUT | TIM1 CH1-4 | PE9 / PE11 / PA10 / PE14 | 部分設定 |
| PM07 電源模組 | POWER1 | ADC1 | PC0 | 待做 |
| 蜂鳴器 | BUZZER | GPIO + Timer | TBD | 待做 |
| 安全開關 | SAFETY | GPIO | TBD | 待做 |
| MPU6050（暫用） | — | I2C1 外接 | PB8 / PB9 | ✅ 已完成 |

---

## 開發階段

### Phase 1 — 基礎啟動 ✅
- PX4 在 Nucleo-H743ZI2 開機
- USART3 console（ST-Link VCP）
- LED 控制（LD1/LD2/LD3）
- MPU6050 I2C 外接，`sensor_accel` / `sensor_gyro` 資料正常

### Phase 2 — 無線遙測（進行中）
- UART7 設定為 TELEM1
- MAVLink 在 TELEM1 啟動（baud 57600）
- SiK Air Unit 接 PE8/PE7
- QGroundControl 透過 SiK Ground Unit 連線成功
- 自製 GUI 工具改用 pymavlink 接收 ATTITUDE / HIGHRES_IMU

### Phase 3 — GPS
- UART4 接 M9N GPS
- I2C1 接 IST8310 羅盤（與 MPU6050 共 bus）
- QGC 顯示位置、衛星數、羅盤方向

### Phase 4 — RC 遙控
- USART6 接 SBUS 接收器（硬體 UART 反相）
- PX4 識別 RC 輸入，QGC 顯示各通道數值

### Phase 5 — ESC 馬達控制
- TIM1 CH1-4 輸出 PWM（或 DSHOT）
- 四顆 ESC 可接收油門指令
- 手動模式可控制馬達轉速

### Phase 6 — 電源監控
- ADC1 讀取 PM07 電壓/電流輸出
- PX4 顯示電池電量，低電壓警告正常

### Phase 7 — 整合飛行
- 全部周邊在 Nucleo 上整合正常
- PX4 可解鎖（Arm）
- 室內懸停測試（Stabilized 模式）

### Phase 8 — 自製飛控板
- 依據 Nucleo 實測接線繪製電路圖
- 晶片升級為 STM32H743IIK6（對齊 Pixhawk 6C）
- 增加生產板需要的電路（電源冗餘、IMU 升級、DFU 入口等）
- 打樣 PCB，板級移植 PX4

---

## 自製板設計要點（Phase 8 備忘）

| 項目 | 說明 |
|------|------|
| IMU | 建議換 **ICM-42688-P**（SPI 介面，飛控主流，精度優於 MPU6050）|
| 電源 | PM07 → 5V BEC → 板上 LDO（3.3V）；需考慮去耦電容與冗餘設計 |
| DFU | 保留 BOOT0 跳線 + USB DFU，方便韌體燒錄與救磚 |
| 振動隔離 | IMU 安裝位置加軟性防振墊或隔振設計 |
| SBUS 反相 | 外接反相器 IC 或使用 STM32 硬體 UART 反相（節省元件）|
| 電流感測 | PM07 輸出接 ADC，建議加運算放大器保護 |
| CAN | 預留 FDCAN1/2 接口，供後續擴充 |
| 測試點 | 所有 UART / SPI / I2C / 電源 都預留 TP，方便除錯 |

---

## 參考資料

- [Pixhawk 6C 原理圖](https://docs.holybro.com/autopilot/pixhawk-6c/downloads) — 對照腳位設計自製板
- [X500 V2 組裝說明](https://docs.holybro.com/drone-kit/x500-v2) — 機架尺寸與周邊清單
- [PX4 硬體移植指南](https://docs.px4.io/main/en/hardware/porting_guide.html)
- [STM32H743 Reference Manual](https://www.st.com/resource/en/reference_manual/rm0433.pdf)
- `Study/new_pc_setup.md` — 換電腦環境建立
- `Study/devlog.md` — 各階段修改記錄
- `Study/learn.md` — 技術概念筆記
