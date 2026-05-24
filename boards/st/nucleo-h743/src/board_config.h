/****************************************************************************
 *
 *   Copyright (c) 2024 PX4 Development Team. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 * 3. Neither the name PX4 nor the names of its contributors may be
 *    used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 ****************************************************************************/

/**
 * @file board_config.h
 *
 * ST Nucleo-H743ZI2 board internal definitions.
 * Phase 1: USART3 virtual COM console + GPIO LED
 */

#pragma once

#include <px4_platform_common/px4_config.h>
#include <px4_platform_common/board_common.h>
#include <nuttx/compiler.h>
#include <stdint.h>
#include <stm32_gpio.h>

/* LEDs -----------------------------------------------------------------------
 * Nucleo-H743ZI2 user LEDs are active HIGH (drive HIGH to turn ON).
 *   LD1 (green):  PB0
 *   LD2 (yellow): PE1
 *   LD3 (red):    PB14
 */

#define GPIO_LED_GREEN   /* PB0  */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTB|GPIO_PIN0)
#define GPIO_LED_YELLOW  /* PE1  */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTE|GPIO_PIN1)
#define GPIO_LED_RED     /* PB14 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTB|GPIO_PIN14)

/* PX4 LED mapping */
#define BOARD_HAS_CONTROL_STATUS_LEDS      1
#define BOARD_ARMED_STATE_LED              0   /* index 0 = green  LD1 */
#define BOARD_OVERLOAD_LED                 1   /* index 1 = yellow LD2 */
#define BOARD_LED_RED                      2   /* index 2 = red    LD3 */

/* GPIO initialization list ---------------------------------------------------
 * Called by px4_gpio_init() during board startup.
 */
#define PX4_GPIO_INIT_LIST { \
	GPIO_LED_GREEN,          \
	GPIO_LED_YELLOW,         \
	GPIO_LED_RED,            \
}

/* I2C -------------------------------------------------------------------------
 * I2C1 (PB8=SCL, PB9=SDA) reserved for external MPU6050 (Phase 2).
 */
#define PX4_I2C_BUS_EXPANSION  1

/* USART3 is the console (PD8/PD9 via ST-Link VCP) -- no extra defines needed */

/* Console buffer (required by dmesg) */
#define BOARD_ENABLE_CONSOLE_BUFFER

/* HRT (High Resolution Timer) -----------------------------------------------
 * TIM8 is reserved for the HRT (same as CubeOrange / fmu-v5).
 * Do NOT enable CONFIG_STM32H7_TIM8 in defconfig.
 */
#define HRT_TIMER          8  /* use timer8 for the HRT */
#define HRT_TIMER_CHANNEL  3  /* use capture/compare channel 3 */

/* PWM outputs ---------------------------------------------------------------
 * TIM1 CH1 (PE9) and CH2 (PE11) are wired to Nucleo CN10 header.
 * Phase 1 does not drive any motors, but the timer config must declare them.
 */
#define DIRECT_PWM_OUTPUT_CHANNELS  2
#define BOARD_HAS_PWM               DIRECT_PWM_OUTPUT_CHANNELS
