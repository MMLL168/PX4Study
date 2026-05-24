/****************************************************************************
 * MPU6050.hpp — PX4 I2C IMU 驅動主類別
 *
 * 學習重點：
 *   1. 繼承 device::I2C：取得 transfer() I2C 底層通訊能力
 *   2. 繼承 I2CSPIDriver<MPU6050>：取得 work queue 排程（ScheduleNow/Delayed）
 *      及 start/stop/status 框架
 *   3. RunImpl() 是主迴圈，由 work queue 週期性呼叫
 *   4. PX4Accelerometer / PX4Gyroscope 負責發布 uORB topic
 ****************************************************************************/
#pragma once

#include "InvenSense_MPU6050_registers.hpp"

#include <drivers/drv_hrt.h>
#include <lib/drivers/accelerometer/PX4Accelerometer.hpp>
#include <lib/drivers/device/i2c.h>
#include <lib/drivers/gyroscope/PX4Gyroscope.hpp>
#include <lib/perf/perf_counter.h>
#include <px4_platform_common/i2c_spi_buses.h>

using namespace InvenSense_MPU6050;

class MPU6050 : public device::I2C, public I2CSPIDriver<MPU6050>
{
public:
	MPU6050(const I2CSPIDriverConfig &config);
	~MPU6050() override;

	// I2CSPIDriver 框架要求實作：建立實例
	static I2CSPIDriverBase *instantiate(const I2CSPIDriverConfig &config, int runtime_instance);

	// I2CSPIDriver 框架要求實作：列印用法
	static void print_usage();

	// work queue 每次觸發時執行（主要邏輯在此）
	void RunImpl();

	int  init() override;
	void print_status() override;

private:
	int probe() override; // 驗證 WHO_AM_I

	bool Reset();     // 送軟體重置指令
	bool Configure(); // 設定量程、取樣率、濾波器

	// I2C 暫存器存取（封裝 transfer()）
	uint8_t RegisterRead(Register reg);
	void    RegisterWrite(Register reg, uint8_t value);

	// uORB 發布器（PX4 標準輔助類別，自動處理 topic 格式轉換）
	PX4Accelerometer _px4_accel;
	PX4Gyroscope     _px4_gyro;

	// 效能計數器（可用 mpu6050 status 查看）
	perf_counter_t _sample_perf{perf_alloc(PC_ELAPSED, MODULE_NAME": read")};
	perf_counter_t _comms_errors{perf_alloc(PC_COUNT,   MODULE_NAME": comm_err")};
	perf_counter_t _bad_register_perf{perf_alloc(PC_COUNT, MODULE_NAME": bad_reg")};

	// 狀態機
	// RunImpl() 根據 _state 決定當次要做什麼
	enum class STATE : uint8_t {
		RESET,          // 送重置指令
		WAIT_FOR_RESET, // 等待重置完成（需等 >100ms）
		CONFIGURE,      // 寫入量程 / 濾波器設定
		READ,           // 正常取樣迴圈
	} _state{STATE::RESET};

	hrt_abstime _reset_timestamp{0}; // 記錄重置時刻，用於超時判斷
	int _failure_count{0};           // 連續失敗次數，超過閾值就重置

	// 物理量換算比例
	// Accel ±2g → 16384 LSB/g → 乘以 9.80665 得 m/s²
	static constexpr float ACCEL_SCALE{9.80665f / 16384.f};
	// Gyro ±500°/s → 65.5 LSB/(°/s) → 乘以 π/180 得 rad/s
	static constexpr float GYRO_SCALE{(float)M_PI / (180.f * 65.5f)};

	// 取樣週期：100Hz = 10,000 μs
	static constexpr uint32_t SAMPLE_INTERVAL_US{10'000};
};
