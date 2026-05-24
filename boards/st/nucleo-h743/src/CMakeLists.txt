############################################################################
#
#   Copyright (c) 2024 PX4 Development Team. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. Neither the name PX4 nor the names of its contributors may be
#    used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
# OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
############################################################################

add_library(drivers_board
	i2c.cpp
	init.c
	led.c
	spi.cpp
	timer_config.cpp
)
add_dependencies(drivers_board arch_board_hw_info)

target_link_libraries(drivers_board
	PRIVATE
		arch_io_pins
		arch_spi
		arch_board_hw_info
		drivers__led
		nuttx_arch
		nuttx_drivers
		px4_layer
)

# BusInstanceIterator (platforms/common/i2c_spi_buses.cpp) always
# references px4_spi_buses even when no SPI sensors are used.
# Without this, spi.cpp.obj is never extracted from libdrivers_board.a
# because no one requests px4_spi_buses before libpx4_platform.a runs.
target_link_options(drivers_board INTERFACE -Wl,--undefined=px4_spi_buses)

# LED 跑馬燈測試模組（NSH 指令：led_chaser start/stop/status）
px4_add_module(
	MODULE boards__st__nucleo_h743__led_chaser
	MAIN led_chaser
	SRCS led_chaser.cpp
	DEPENDS drivers__led
)
