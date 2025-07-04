#  OverStim - Controls sex toys based on the game Overwatch 2
#  Copyright (C) 2023-2025 cryo-es
#  Copyright (C) 2024-2025 Pharmercy69 <pharmercy69@protonmail.ch>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#  SPDX-License-Identifier: AGPL-3.0-or-later

import enum
import logging
from typing import NamedTuple


class Config(NamedTuple):
    max_vibe_intensity: float = 1.0
    emergency_stop_key_combo: str = "<ctrl>+<shift>+<cmd>"
    scale_all_intensities_by_max_intensity: bool = True
    continuous_scanning: bool = True
    excluded_device_names: list[str] = ["XBox (XInput) Compatible Gamepad"]
    using_intiface: bool = True
    websocket_address: str = "ws://localhost:12345"
    gpu_id: int = 0
    monitor_id: int = 0
    max_refresh_rate: int = 30
    dead_refresh_rate: int = 5
    lucio_crossfade_buffer: int = 6
    mercy_beam_disconnect_buffer: int = 11
    zen_orb_disconnect_buffer: int = 27
    preview_window: bool = False


def clamp_value(value: float, max_value: float, min_value: float = 0, value_name: str = "value") -> float:
    if value > max_value:
        value = max_value
    elif value < min_value:
        logging.info(f"Tried to set {value_name} to {value} but it cannot be lower than {min_value}. "
                     f"Setting it to {min_value}.")
        value = min_value
    return value


def round_value_to_nearest_step(value: float, step: float) -> float:
    digits_to_round_to = len(str(float(step)).split(".")[1])
    return round(step * round(value / step, 0), digits_to_round_to)


def format_enum(enum_: enum.Enum) -> str:
    return " ".join(word.capitalize() for word in enum_.name.split("_"))


def format_float(number: float) -> str:
    num_str = f"{number:.1f}"
    num_str = num_str.rstrip("0").rstrip(".")
    return num_str


class FPSCalculator:
    def __init__(self) -> None:
        self.frame_times = []

    def update(self, current_time: float) -> int:
        # Add the current frame time
        self.frame_times.append(current_time)
        # Remove frame times that are older than the window duration
        while self.frame_times and self.frame_times[0] < current_time - 1.0:
            del self.frame_times[0]
        # FPS is the number of frames divided by the duration
        return len(self.frame_times)
