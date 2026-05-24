/****************************************************************************
 * MPU6050 暫存器定義
 * InvenSense MPU6050 — 6 軸 IMU（三軸加速度計 + 三軸陀螺儀），I2C 介面
 *
 * 學習重點：
 *   - PX4 驅動把所有硬體定義（位址、暫存器、bit mask）集中在此檔案
 *   - 使用 namespace + enum class 避免命名衝突
 *   - struct + static_assert 確保 burst read buffer 大小正確
 ****************************************************************************/
#pragma once

#include <cstdint>

namespace InvenSense_MPU6050 {

// I2C 位址
// AD0 腳位接 GND → 0x68（預設）
// AD0 腳位接 VCC → 0x69
static constexpr uint8_t I2C_ADDRESS_DEFAULT = 0x68;
static constexpr uint8_t I2C_ADDRESS_ALT     = 0x69;

// WHO_AM_I 暫存器回傳值（MPU6050 固定為 0x68）
static constexpr uint8_t WHOAMI = 0x68;

// 暫存器位址對照表
enum class Register : uint8_t {
	SMPLRT_DIV   = 0x19,   // 取樣率分頻器
	CONFIG       = 0x1A,   // DLPF 低通濾波器設定
	GYRO_CONFIG  = 0x1B,   // 陀螺儀量程設定
	ACCEL_CONFIG = 0x1C,   // 加速度計量程設定

	ACCEL_XOUT_H = 0x3B,   // Burst read 從這裡開始（連續 14 bytes）
	TEMP_OUT_H   = 0x41,
	GYRO_XOUT_H  = 0x43,

	PWR_MGMT_1   = 0x6B,   // 電源管理（重置、睡眠、時脈選擇）
	WHO_AM_I     = 0x75,   // 裝置 ID 驗證
};

// PWR_MGMT_1 bit 定義
namespace PWR_MGMT_1_BIT {
	static constexpr uint8_t DEVICE_RESET = (1 << 7); // 軟體重置（自動清 0）
	static constexpr uint8_t SLEEP        = (1 << 6); // 睡眠模式
	static constexpr uint8_t CLKSEL_PLL  = 0x01;     // 時脈源：X 軸陀螺儀 PLL（精準）
}

// CONFIG — DLPF（數位低通濾波器）設定
// DLPF_CFG = 3：加速度計 44Hz BW，陀螺儀 42Hz BW，延遲小，適合飛控
namespace CONFIG_BIT {
	static constexpr uint8_t DLPF_44HZ = 0x03;
}

// GYRO_CONFIG — FS_SEL[4:3] 陀螺儀量程
namespace GYRO_CONFIG_BIT {
	static constexpr uint8_t FS_SEL_250DPS  = (0x00 << 3); // ±250 °/s，65.5 LSB/°/s
	static constexpr uint8_t FS_SEL_500DPS  = (0x01 << 3); // ±500 °/s，65.5 LSB/°/s
	static constexpr uint8_t FS_SEL_1000DPS = (0x02 << 3); // ±1000 °/s
	static constexpr uint8_t FS_SEL_2000DPS = (0x03 << 3); // ±2000 °/s
}

// ACCEL_CONFIG — AFS_SEL[4:3] 加速度計量程
namespace ACCEL_CONFIG_BIT {
	static constexpr uint8_t AFS_SEL_2G  = (0x00 << 3); // ±2g，16384 LSB/g
	static constexpr uint8_t AFS_SEL_4G  = (0x01 << 3); // ±4g
	static constexpr uint8_t AFS_SEL_8G  = (0x02 << 3); // ±8g
	static constexpr uint8_t AFS_SEL_16G = (0x03 << 3); // ±16g
}

// Burst read 資料結構（從 ACCEL_XOUT_H 連續讀 14 bytes）
// MPU6050 支援 I2C 連續讀取，只需送一次起始位址
#pragma pack(push, 1)
struct SensorData {
	uint8_t ACCEL_XOUT_H;
	uint8_t ACCEL_XOUT_L;
	uint8_t ACCEL_YOUT_H;
	uint8_t ACCEL_YOUT_L;
	uint8_t ACCEL_ZOUT_H;
	uint8_t ACCEL_ZOUT_L;
	uint8_t TEMP_OUT_H;
	uint8_t TEMP_OUT_L;
	uint8_t GYRO_XOUT_H;
	uint8_t GYRO_XOUT_L;
	uint8_t GYRO_YOUT_H;
	uint8_t GYRO_YOUT_L;
	uint8_t GYRO_ZOUT_H;
	uint8_t GYRO_ZOUT_L;
};
#pragma pack(pop)
static_assert(sizeof(SensorData) == 14, "MPU6050 SensorData size mismatch");

} // namespace InvenSense_MPU6050
