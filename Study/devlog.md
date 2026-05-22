# PX4 開發與除錯日誌 (DevLog)

此文件用於記錄開發過程中的修改、遇到的問題、處理方式與時間。

---

## [2023-10-25 10:00] SWD 燒錄導致 Bootloader 遺失與還原
- **問題描述**：使用 Pixhawk Debug Adapter (SWD 介面) 進行底層燒錄與除錯時，發現飛控插上 USB 後毫無反應，電腦無法辨識到虛擬 COM Port。
- **原因分析**：SWD 燒錄軟體的預設行為是「全晶片抹除 (Mass Erase)」，這會把位在 Flash 起點 (`0x08000000`) 的 Bootloader 也一併清除。沒有 Bootloader，飛控就失去了 USB DFU 與 Serial 溝通的功能。
- **處理方式**：
  1. **災後還原**：先透過 SWD 介面，將官方編譯好的 Bootloader `.bin` 重新燒錄到 `0x08000000`。完成後拔除 SWD，改插 USB 線，此時電腦便能抓到 COM Port。最後再用一般 `make upload` 或透過 QGC 燒錄 PX4 App 韌體即可。
  2. **未來預防**：在除錯工具 (如 OpenOCD / GDB / STM32CubeProgrammer) 的設定中，將抹除模式改為「**Sector Erase (區塊抹除)**」，這樣就能避開 Bootloader 所在的磁區。

---

## [2023-10-25 11:30] 啟動 Nucleo-H743 + MPU6050 的板級移植 (Board Porting)
- **目標**：為了深入了解 NuttX 與 PX4 驅動架構，改用 ST Nucleo-H743 開發板加上外接 MPU6050 模組，從零開始進行 PX4 板級移植 (Bring-up)。
- **修改與處理方式 (實作規劃)**：
  1. **建立板級資料夾**：在 PX4 原始碼的 `boards/st/` 目錄下建立 `nucleo-h743` 資料夾。
  2. **配置編譯檔**：新增並修改 `board.cmake`, `default.px4board`, `defconfig`, `board_config.h` 等核心檔案，讓 PX4 的 CMake 系統能辨識這塊板子。
  3. **Console 輸出設定**：在 NuttX 的 `defconfig` 中，將 Serial Console 指向 `USART3` (這對應 Nucleo 板上 ST-Link 提供的虛擬 COM 腳位 PD8/PD9)。設定 115200 Baudrate，確保開機能看見 `nsh>` 終端機。
  4. **感測器驅動掛載**：
     - 硬體接線：將 MPU6050 的 SDA/SCL 接到板子的 I2C1 (PB8/PB9)。
     - 軟體指令：在 `nsh>` 終端機下，先用 `i2c dev 1 0x68` 掃描硬體，確認連線後，手動輸入 `mpu6000 start -X -b 1` 啟動驅動，最後用 `listener sensor_accel` 驗證數據是否正常輸出。
