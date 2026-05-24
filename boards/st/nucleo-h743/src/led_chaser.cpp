/****************************************************************************
 * boards/st/nucleo-h743/src/led_chaser.cpp
 *
 * LED 跑馬燈模組 — Nucleo-H743ZI2 板級測試工具
 *
 * 用法（從 NSH 終端）：
 *   led_chaser start    開始 LD1→LD2→LD3 循環
 *   led_chaser stop     停止，恢復綠燈常亮
 *   led_chaser status   顯示執行狀態
 ****************************************************************************/

#include <px4_platform_common/module.h>
#include <px4_platform_common/px4_work_queue/ScheduledWorkItem.hpp>
#include "board_config.h"

using namespace time_literals;

__BEGIN_DECLS
extern void led_on(int led);
extern void led_off(int led);
extern void drv_led_start(void);
__END_DECLS

extern "C" __EXPORT int led_chaser_main(int argc, char *argv[]);

class LedChaser : public ModuleBase, public px4::ScheduledWorkItem
{
public:
	static Descriptor desc;

	LedChaser() :
		ModuleBase(),
		ScheduledWorkItem(MODULE_NAME, px4::wq_configurations::lp_default) {}

	~LedChaser() override
	{
		led_off(0); led_off(1); led_off(2);
		led_on(BOARD_LED_GREEN);
	}

	static int task_spawn(int argc, char *argv[]);
	static int custom_command(int argc, char *argv[]);
	static int print_usage(const char *reason = nullptr);

	bool init() { ScheduleNow(); return true; }

	void Run() override
	{
		if (should_exit()) {
			ScheduleClear();
			exit_and_cleanup(desc);
			return;
		}

		led_off(_current);
		_current = (_current + 1) % 3;
		led_on(_current);

		ScheduleDelayed(300_ms);
	}

private:
	int _current{2};
};

ModuleBase::Descriptor LedChaser::desc{task_spawn, custom_command, print_usage};

int LedChaser::task_spawn(int argc, char *argv[])
{
	LedChaser *obj = new LedChaser();

	if (!obj || !obj->init()) {
		delete obj;
		return PX4_ERROR;
	}

	desc.object.store(obj);
	desc.task_id = task_id_is_work_queue;
	return PX4_OK;
}

int LedChaser::custom_command(int argc, char *argv[])
{
	return print_usage("unknown command");
}

int LedChaser::print_usage(const char *reason)
{
	if (reason) { PX4_WARN("%s\n", reason); }

	PRINT_MODULE_DESCRIPTION("LED 跑馬燈：LD1(綠)→LD2(黃)→LD3(紅) 循環，確認板子正常運行");
	PRINT_MODULE_USAGE_NAME("led_chaser", "driver");
	PRINT_MODULE_USAGE_COMMAND("start");
	PRINT_MODULE_USAGE_DEFAULT_COMMANDS();
	return 0;
}

int led_chaser_main(int argc, char *argv[])
{
	return ModuleBase::main(LedChaser::desc, argc, argv);
}
