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

import logging
import time
from collections import defaultdict
from collections.abc import Sequence
from typing import NamedTuple

import buttplug

from .triggers import Response, Trigger, is_conditional
from .utils import clamp_value, round_value_to_nearest_step, Config, format_enum


class BuiltVibration(NamedTuple):
    intensity: float
    expiry: float


class Vibe:
    def __init__(self, response: Response, trigger: Trigger, creation_time: float) -> None:
        self.response = response
        self.trigger = trigger
        self.creation_time = creation_time

    def get_intensity(self, current_time: float) -> float | None:
        timestamp = current_time - self.creation_time
        unlimited = is_conditional(self.trigger)
        return self.response.get_intensity(timestamp, unlimited)


class VibeManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.current_time = 0.0
        self.last: dict[Trigger, float] = defaultdict(float)
        self.vibes: dict[Trigger, list[Vibe]] = defaultdict(list)
        self.current_intensity = 0.0
        self.real_intensity = 0.0
        self.all_intensities: dict[Trigger, list[float]] = defaultdict(list)

    def add_vibe(self, trigger: Trigger, response: Response, suppression_secs: float = 0.0) -> None:
        now = time.time()
        if now - self.last[trigger] < suppression_secs:
            return
        vibe = Vibe(response, trigger, self.current_time)
        self.vibes[trigger].append(vibe)
        self.last[trigger] = now

    def toggle_vibe_to_condition(self, trigger: Trigger, response: Response, condition: bool) -> None:
        vibe_exists_for_trigger = self.vibe_exists_for_trigger(trigger)
        if condition and not vibe_exists_for_trigger:
            self.add_vibe(trigger, response)
        elif not condition and vibe_exists_for_trigger:
            self.clear_vibes(trigger)

    def clear_vibes(self, trigger: Trigger | None = None) -> None:
        if trigger is None:
            self.vibes.clear()
        else:
            self.vibes[trigger].clear()

    async def stop_all_devices(self, devices: Sequence[buttplug.Device]) -> None:
        self.clear_vibes()
        for device in devices:
            await device.stop()
        self.current_intensity = 0
        self.real_intensity = 0
        logging.info("Stopped all devices.")

    def vibe_exists_for_trigger(self, trigger: Trigger) -> bool:
        return bool(self.vibes[trigger])

    def vibe_for_trigger_created_within_seconds(self, trigger: Trigger, seconds: float) -> bool:
        for vibe in self.vibes[trigger]:
            if vibe.creation_time > self.current_time - seconds:
                return True
        return False

    def _get_total_intensity(self) -> float:
        total_intensity = 0.0
        response_type_silence = False
        self.all_intensities.clear()
        for trigger, vibes in self.vibes.items():
            for vibe in vibes:
                intensity = vibe.get_intensity(self.current_time)
                if intensity is None:
                    self.vibes[vibe.trigger].remove(vibe)
                    continue
                total_intensity += intensity
                self.all_intensities[trigger].append(intensity)
                if intensity == -1.0:
                    response_type_silence = True
        if response_type_silence:
            return 0.0
        return total_intensity

    async def _update_intensity_for_devices(self, devices: Sequence[buttplug.Device]) -> None:
        for device in devices:
            try:
                # Send new intensity to every actuator within the device
                actuator_intensities = []
                for actuator in device.actuators:

                    # Set actuator intensity to the closest step supported by that actuator, and limit it to the
                    # user-defined max intensity
                    actuator_min_intensity_step = 1 / actuator.step_count
                    actuator_max_intensity = round_value_to_nearest_step(self.config.max_vibe_intensity,
                                                                         actuator_min_intensity_step)
                    while actuator_max_intensity > self.config.max_vibe_intensity:
                        actuator_max_intensity -= actuator_min_intensity_step
                    actuator_intensity = clamp_value(
                        round_value_to_nearest_step(self.real_intensity, actuator_min_intensity_step),
                        actuator_max_intensity, value_name="actuator intensity")
                    actuator_intensities.append(actuator_intensity)

                    await actuator.command(actuator_intensity)

                # Print new intensities of device actuators
                intensity_string = f"[{device.name}] Vibe 1: {actuator_intensities[0]}"
                for index in range(len(actuator_intensities) - 1):
                    intensity_string = f"{intensity_string}, Vibe {index + 2}: {actuator_intensities[index + 1]}"
                logging.info(intensity_string)

            except Exception as device_intensity_update_error:
                logging.warning(f"Stopping {device.name} due to an error while altering its vibration.")
                logging.error(device_intensity_update_error)
                await device.stop()

    def print_active_triggers(self) -> None:
        active_triggers = []
        for trigger, vibes in self.vibes.items():
            if vibes:
                active_triggers.append(f"{format_enum(trigger)} (x{len(vibes)})")
        if active_triggers:
            logging.info(", ".join(active_triggers))

    async def update(self, devices: Sequence[buttplug.Device], current_time: float) -> None:
        self.current_time = current_time
        latest_intensity = self._get_total_intensity()
        if self.config.scale_all_intensities_by_max_intensity:
            latest_intensity *= self.config.max_vibe_intensity
        latest_intensity = abs(round(latest_intensity, 4))
        if self.current_intensity != latest_intensity:
            self.current_intensity = latest_intensity
            latest_clamped_intensity = clamp_value(self.current_intensity, self.config.max_vibe_intensity,
                                                   value_name="intensity")
            logging.info(f"Updated intensity: {self.current_intensity * 100:.0f}%" + (
                "" if self.current_intensity == latest_clamped_intensity else f" ({latest_clamped_intensity})"))
            if self.real_intensity != latest_clamped_intensity:
                self.real_intensity = latest_clamped_intensity
                self.print_active_triggers()
                await self._update_intensity_for_devices(devices)
