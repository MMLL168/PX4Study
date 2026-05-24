/****************************************************************************
 * MPU6050.cpp — 驅動實作
 *
 * 學習重點（狀態機流程）：
 *
 *   RunImpl() 每 10ms 被 work queue 呼叫一次，依 _state 執行不同動作：
 *
 *   RESET ──→ WAIT_FOR_RESET ──→ CONFIGURE ──→ READ ──→ READ ──→ ...
 *     ↑________________________失敗超過閾值__________________________↑
 *
 *   1. RESET：寫入 DEVICE_RESET bit，啟動軟體重置
 *   2. WAIT_FOR_RESET：輪詢 PWR_MGMT_1 等待 bit 自動清 0（約 100ms）
 *   3. CONFIGURE：設定量程、取樣率、DLPF
 *   4. READ：Burst read 14 bytes，換算成物理量，透過 uORB 發布
 ****************************************************************************/

#include "MPU6050.hpp"

#include <px4_platform_common/px4_config.h>
#include <px4_platform_common/getopt.h>

using namespace time_literals;

MPU6050::MPU6050(const I2CSPIDriverConfig &config) :
	device::I2C(config),                              // 初始化 I2C bus/address/freq
	I2CSPIDriver(config),                             // 初始化 work queue 框架
	_px4_accel(get_device_id(), config.rotation),     // 綁定裝置 ID（用於多感測器區分）
	_px4_gyro(get_device_id(), config.rotation)
{
}

MPU6050::~MPU6050()
{
	perf_free(_sample_perf);
	perf_free(_comms_errors);
	perf_free(_bad_register_perf);
}

// --- 框架入口 ---

I2CSPIDriverBase *MPU6050::instantiate(const I2CSPIDriverConfig &config, int runtime_instance)
{
	MPU6050 *instance = new MPU6050(config);

	if (!instance || instance->init() != PX4_OK) {
		delete instance;
		return nullptr;
	}

	return instance;
}

int MPU6050::init()
{
	// 初始化 I2C bus（設定 GPIO、時脈速率等底層設定）
	int ret = device::I2C::init();

	if (ret != PX4_OK) {
		PX4_ERR("I2C init failed (%d)", ret);
		return ret;
	}

	// probe() 在 I2C::init() 內部自動被呼叫（讀 WHO_AM_I 驗證）
	// 若 probe() 失敗，I2C::init() 會回傳錯誤

	// 觸發第一次 RunImpl()，讓狀態機開始運作
	ScheduleNow();
	return PX4_OK;
}

int MPU6050::probe()
{
	// 讀取 WHO_AM_I 暫存器（0x75），驗證是否為 MPU6050
	const uint8_t whoami = RegisterRead(Register::WHO_AM_I);

	if (whoami != WHOAMI) {
		PX4_ERR("WHO_AM_I: expected 0x%02X, got 0x%02X", WHOAMI, whoami);
		return -EIO;
	}

	return PX4_OK;
}

// --- 狀態機主迴圈 ---

void MPU6050::RunImpl()
{
	switch (_state) {

	// ── RESET：送軟體重置指令 ──────────────────────────────────────────
	case STATE::RESET:
		RegisterWrite(Register::PWR_MGMT_1, PWR_MGMT_1_BIT::DEVICE_RESET);
		_reset_timestamp = hrt_absolute_time();
		_state = STATE::WAIT_FOR_RESET;
		ScheduleDelayed(100_ms); // 等 100ms 讓晶片完成重置
		break;

	// ── WAIT_FOR_RESET：輪詢等待 DEVICE_RESET bit 自動清 0 ──────────────
	case STATE::WAIT_FOR_RESET: {
		const uint8_t pwr = RegisterRead(Register::PWR_MGMT_1);

		if (pwr & PWR_MGMT_1_BIT::DEVICE_RESET) {
			// bit 尚未清 0，繼續等待
			if (hrt_elapsed_time(&_reset_timestamp) > 500_ms) {
				// 超過 500ms 仍未完成 → 重試
				PX4_WARN("reset timeout, retrying");
				_state = STATE::RESET;
			}

			ScheduleDelayed(10_ms);

		} else {
			// 重置完成，進入設定階段
			_state = STATE::CONFIGURE;
			ScheduleNow();
		}

		break;
	}

	// ── CONFIGURE：寫入所有工作暫存器 ────────────────────────────────────
	case STATE::CONFIGURE:
		if (Configure()) {
			_state = STATE::READ;
			_failure_count = 0;
			ScheduleDelayed(SAMPLE_INTERVAL_US);

		} else {
			// 設定失敗，重新重置
			PX4_WARN("configure failed, resetting");
			_state = STATE::RESET;
			ScheduleDelayed(100_ms);
		}

		break;

	// ── READ：正常取樣（每 10ms 執行一次）────────────────────────────────
	case STATE::READ: {
		// 步驟 1：記錄取樣時間戳（必須在讀取之前記錄，代表資料「被量到」的時刻）
		const hrt_abstime timestamp_sample = hrt_absolute_time();

		// 步驟 2：Burst read — 從 ACCEL_XOUT_H（0x3B）連讀 14 bytes
		//   [accelX H/L][accelY H/L][accelZ H/L][temp H/L][gyroX H/L][gyroY H/L][gyroZ H/L]
		SensorData data{};
		uint8_t reg = static_cast<uint8_t>(Register::ACCEL_XOUT_H);

		perf_begin(_sample_perf);
		int ret = transfer(&reg, 1, reinterpret_cast<uint8_t *>(&data), sizeof(data));
		perf_end(_sample_perf);

		if (ret != PX4_OK) {
			perf_count(_comms_errors);
			_failure_count++;

			if (_failure_count > 10) {
				// 連續 10 次失敗 → 重置感測器
				PX4_WARN("too many errors, resetting");
				_state = STATE::RESET;
				ScheduleDelayed(100_ms);
				return;
			}

			ScheduleDelayed(SAMPLE_INTERVAL_US);
			return;
		}

		_failure_count = 0;

		// 步驟 3：把 big-endian 原始值組合成 int16，再乘以比例換算成物理量
		//   MPU6050 資料為 Big-Endian（高 byte 先）
		const int16_t accel_x = (int16_t)((data.ACCEL_XOUT_H << 8) | data.ACCEL_XOUT_L);
		const int16_t accel_y = (int16_t)((data.ACCEL_YOUT_H << 8) | data.ACCEL_YOUT_L);
		const int16_t accel_z = (int16_t)((data.ACCEL_ZOUT_H << 8) | data.ACCEL_ZOUT_L);

		const int16_t gyro_x  = (int16_t)((data.GYRO_XOUT_H << 8) | data.GYRO_XOUT_L);
		const int16_t gyro_y  = (int16_t)((data.GYRO_YOUT_H << 8) | data.GYRO_YOUT_L);
		const int16_t gyro_z  = (int16_t)((data.GYRO_ZOUT_H << 8) | data.GYRO_ZOUT_L);

		const int16_t temp_raw = (int16_t)((data.TEMP_OUT_H << 8) | data.TEMP_OUT_L);
		const float temperature = (temp_raw / 340.f) + 36.53f; // °C

		// 步驟 4：發布 uORB topic（sensor_accel / sensor_gyro）
		//   update() 內部自動做單位換算、clip 檢查、publish
		_px4_accel.set_temperature(temperature);
		_px4_accel.update(timestamp_sample,
				  accel_x * ACCEL_SCALE,
				  accel_y * ACCEL_SCALE,
				  accel_z * ACCEL_SCALE);

		_px4_gyro.set_temperature(temperature);
		_px4_gyro.update(timestamp_sample,
				 gyro_x * GYRO_SCALE,
				 gyro_y * GYRO_SCALE,
				 gyro_z * GYRO_SCALE);

		ScheduleDelayed(SAMPLE_INTERVAL_US);
		break;
	}
	}
}

// --- 硬體設定 ---

bool MPU6050::Configure()
{
	// 喚醒晶片，選用 X 軸陀螺儀 PLL 作為時脈源（比內部振盪器準確）
	RegisterWrite(Register::PWR_MGMT_1, PWR_MGMT_1_BIT::CLKSEL_PLL);

	// 取樣率分頻器：0 → 取樣率 = 陀螺儀輸出率 / (1+0) = 1000Hz
	// 這裡我們每 10ms poll 一次（100Hz），sensor 本身以 1kHz 更新
	RegisterWrite(Register::SMPLRT_DIV, 0x00);

	// DLPF：44Hz 低通濾波器，減少高頻雜訊
	RegisterWrite(Register::CONFIG, CONFIG_BIT::DLPF_44HZ);

	// 陀螺儀量程 ±500°/s（靈敏度：65.5 LSB/°/s）
	RegisterWrite(Register::GYRO_CONFIG, GYRO_CONFIG_BIT::FS_SEL_500DPS);

	// 加速度計量程 ±2g（靈敏度：16384 LSB/g）
	RegisterWrite(Register::ACCEL_CONFIG, ACCEL_CONFIG_BIT::AFS_SEL_2G);

	// 驗證設定是否成功（讀回 GYRO_CONFIG 確認）
	const uint8_t gyro_cfg = RegisterRead(Register::GYRO_CONFIG);

	if (gyro_cfg != GYRO_CONFIG_BIT::FS_SEL_500DPS) {
		perf_count(_bad_register_perf);
		return false;
	}

	return true;
}

bool MPU6050::Reset()
{
	RegisterWrite(Register::PWR_MGMT_1, PWR_MGMT_1_BIT::DEVICE_RESET);
	return true;
}

// --- I2C 低階存取 ---

// RegisterRead：送暫存器位址（1 byte），接收回傳值（1 byte）
uint8_t MPU6050::RegisterRead(Register reg)
{
	uint8_t cmd   = static_cast<uint8_t>(reg);
	uint8_t value = 0;
	transfer(&cmd, 1, &value, 1);
	return value;
}

// RegisterWrite：送 [位址, 值]（2 bytes），無接收
void MPU6050::RegisterWrite(Register reg, uint8_t value)
{
	uint8_t buf[2] = {static_cast<uint8_t>(reg), value};
	transfer(buf, 2, nullptr, 0);
}

// --- 狀態列印 ---

void MPU6050::print_status()
{
	I2CSPIDriverBase::print_status();
	perf_print_counter(_sample_perf);
	perf_print_counter(_comms_errors);
	perf_print_counter(_bad_register_perf);
}
