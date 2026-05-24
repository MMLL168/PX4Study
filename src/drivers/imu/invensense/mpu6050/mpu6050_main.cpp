/****************************************************************************
 * mpu6050_main.cpp — NSH 指令入口
 *
 * 學習重點：
 *   - BusCLIArguments{true, false}：宣告支援 I2C，不支援 SPI
 *   - BusInstanceIterator：讓框架在所有 I2C bus 上搜尋裝置
 *   - module_start / module_stop / module_status：框架提供的標準指令
 *
 * NSH 用法：
 *   mpu6050 start -b 1 -a 0x68   啟動（I2C bus 1，位址 0x68）
 *   mpu6050 status                查看取樣計數 / 錯誤計數
 *   mpu6050 stop                  停止驅動
 ****************************************************************************/

#include "MPU6050.hpp"

#include <px4_platform_common/module.h>

void MPU6050::print_usage()
{
	PRINT_MODULE_DESCRIPTION("MPU6050 I2C IMU 驅動（加速度計 + 陀螺儀）");
	PRINT_MODULE_USAGE_NAME("mpu6050", "driver");
	PRINT_MODULE_USAGE_SUBCATEGORY("imu");
	PRINT_MODULE_USAGE_COMMAND("start");
	PRINT_MODULE_USAGE_PARAMS_I2C_SPI_DRIVER(true, false); // I2C only
	PRINT_MODULE_USAGE_DEFAULT_COMMANDS();
}

extern "C" int mpu6050_main(int argc, char *argv[])
{
	// I2C=true, SPI=false：只允許 I2C 匯流排
	BusCLIArguments cli{true, false};
	cli.default_i2c_frequency = 400'000; // Fast Mode 400kHz
	cli.i2c_address = I2C_ADDRESS_DEFAULT; // 0x68

	const char *verb = cli.parseDefaultArguments(argc, argv);

	if (!verb) {
		MPU6050::print_usage();
		return -1;
	}

	// DRV_IMU_DEVTYPE_MPU6050：讓框架用裝置類型區分多個相同 sensor
	BusInstanceIterator iterator(MODULE_NAME, cli, DRV_IMU_DEVTYPE_MPU6050);

	if (!strcmp(verb, "start")) {
		return MPU6050::module_start(cli, iterator);
	}

	if (!strcmp(verb, "stop")) {
		return MPU6050::module_stop(iterator);
	}

	if (!strcmp(verb, "status")) {
		return MPU6050::module_status(iterator);
	}

	MPU6050::print_usage();
	return -1;
}
