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

import asyncio
import logging
import time
from collections.abc import Mapping, Callable
from typing import NamedTuple

from buttplug import Client, WebsocketConnector, ProtocolSpec, Device

from .heroes import Hero2
from .triggers import Trigger, Response, is_conditional
from .player_state import PlayerState
from .utils import Config, FPSCalculator
from .vibe import VibeManager


class ControllerInfo(NamedTuple):
    vibe_intensity: float = 0.0
    current_hero: Hero2 = Hero2.OTHER
    devices_connected: int = 0
    fps: int = 0
    calculation_time: float = 0.0
    all_intensities: dict[Trigger, list[float]] = {}


class Controller:
    def __init__(self, config: Config, asset_path: str, update_info: Callable[[ControllerInfo], None]) -> None:
        self.config = config
        self.update_info = update_info

        # Input attributes
        self.responses: Mapping[Hero2, Mapping[Trigger, Response]] = {}
        self.stop_request = False

        # Prepare resources
        self.client = Client("OverStim", ProtocolSpec.v3)
        self.vibe_manager = VibeManager(self.config)
        self.player_state = PlayerState(self.config, asset_path)

        # Program state
        self.fps_calculator = FPSCalculator()
        self.state_device_count = 0

    async def run(self) -> None:
        scanning = False
        try:

            # Connect to Intiface
            if self.config.using_intiface:
                connector = WebsocketConnector(self.config.websocket_address, logger=self.client.logger)
                await self.client.connect(connector)
                logging.info("Connected to Intiface")

                if self.client.connected:
                    await self.client.start_scanning()
                    scanning = True
                    if not self.config.continuous_scanning:
                        await asyncio.sleep(0.2)
                        await self.client.stop_scanning()
                        scanning = False
                    logging.info("Started scanning")

            # Run main loop
            await self.loop()

        finally:
            await self.vibe_manager.stop_all_devices(self.get_devices())
            self.player_state.stop_tracking()
            if self.config.using_intiface and self.client.connected:
                if scanning:
                    await self.client.stop_scanning()
                await self.client.disconnect()
                logging.info("Disconnected.")

    async def loop(self) -> None:
        # Initialize player state
        self.player_state.supported_heroes[Hero2.LUCIO].crossfade_buffer_size = \
            self.config.lucio_crossfade_buffer
        self.player_state.supported_heroes[Hero2.MERCY].beam_disconnect_buffer_size = \
            self.config.mercy_beam_disconnect_buffer
        self.player_state.supported_heroes[Hero2.ZENYATTA].orb_disconnect_buffer_size = \
            self.config.zen_orb_disconnect_buffer
        self.player_state.start_tracking(self.config.max_refresh_rate)

        # Initialize variables
        last_refresh = 0
        counter = 0
        start_time = time.time()

        while not self.stop_request:
            # Gives main time to respond to pings from Intiface
            await asyncio.sleep(0)

            if self.config.using_intiface:
                assert self.client.connected, "Lost connection to Intiface."

            counter += 1
            devices = self.get_devices()
            current_time = time.time()
            await self.vibe_manager.update(devices, current_time)

            if not self.player_state.is_dead or (
                    self.player_state.is_dead and
                    current_time >= last_refresh + (1 / float(self.config.dead_refresh_rate))):
                last_refresh = current_time
                self.player_state.wait_for_frame()
                processing_time_start = time.time()
                self.player_state.refresh()

                # Add other Vibes if not hacked
                for trigger, response in self.responses[self.player_state.hero.name].items():
                    if not is_conditional(trigger):

                        if trigger is Trigger.ELIMINATION:
                            new_elims = self.player_state.new_notifs.get("elimination", 0)
                            if new_elims > 0:
                                self.vibe_manager.add_vibe(trigger, response)

                        elif trigger is Trigger.ASSIST:
                            new_assists = self.player_state.new_notifs.get("assist", 0)
                            if new_assists > 0:
                                self.vibe_manager.add_vibe(trigger, response)

                        elif trigger is Trigger.SAVE:
                            new_saves = self.player_state.new_notifs.get("save", 0)
                            if new_saves > 0 and (self.player_state.hero.name is not Hero2.MERCY or
                                                  not self.player_state.hero.resurrecting):
                                self.vibe_manager.add_vibe(trigger, response)

                        elif trigger is Trigger.RESURRECT:
                            if self.player_state.hero.resurrecting and \
                                    not self.vibe_manager.vibe_for_trigger_created_within_seconds(trigger, 3):
                                self.vibe_manager.add_vibe(trigger, response)

                        elif trigger is Trigger.FLASH_HEAL:
                            if self.player_state.hero.flash_heal:
                                self.vibe_manager.add_vibe(trigger, response, suppression_secs=3.0)

                        elif trigger is Trigger.GLIDE_BOOST:
                            if self.player_state.hero.glide_boost and \
                                    not self.vibe_manager.vibe_exists_for_trigger(trigger):
                                self.vibe_manager.add_vibe(trigger, response)

                        elif trigger is Trigger.PULSAR_TORPEDOES_FIRE:
                            if self.player_state.hero.pulsar_torpedoes_firing and \
                                    not self.vibe_manager.vibe_exists_for_trigger(trigger):
                                self.vibe_manager.add_vibe(trigger, response)

                        elif trigger is Trigger.ENDORSEMENT_RECEIVED:
                            if self.player_state.endorsed:
                                self.vibe_manager.add_vibe(trigger, response, suppression_secs=4.8)

                    else:

                        if trigger is Trigger.HACKED_BY_SOMBRA:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hacked)

                        elif trigger is Trigger.BEAMED_BY_MERCY:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.being_beamed)

                        elif trigger is Trigger.ORBED_BY_ZENYATTA:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.being_orbed)

                        elif trigger is Trigger.PULSAR_TORPEDOES_LOCK:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response,
                                self.player_state.hero.pulsar_torpedoes_lock and
                                not self.vibe_manager.vibe_exists_for_trigger(Trigger.PULSAR_TORPEDOES_FIRE))

                        elif trigger is Trigger.HEALING_SONG:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hero.healing_song)

                        elif trigger is Trigger.SPEED_SONG:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hero.speed_song)

                        elif trigger is Trigger.HEAL_BEAM:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hero.heal_beam)

                        elif trigger is Trigger.DAMAGE_BEAM:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hero.damage_beam)

                        elif trigger is Trigger.HARMONY_ORB:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hero.harmony_orb)

                        elif trigger is Trigger.DISCORD_ORB:
                            self.vibe_manager.toggle_vibe_to_condition(
                                trigger, response, self.player_state.hero.discord_orb)

                if self.player_state.hero_auto_detect and \
                        self.player_state.detected_hero is not self.player_state.hero.name:
                    logging.info(f"Hero switch detected: {self.player_state.detected_hero}")
                    self.vibe_manager.clear_vibes()
                    self.player_state.switch_hero(self.player_state.hero_auto_detect, self.player_state.detected_hero)

                processing_time_end = time.time()
                self.update_info(ControllerInfo(
                    vibe_intensity=self.vibe_manager.real_intensity,
                    current_hero=self.player_state.hero.name,
                    devices_connected=len(devices),
                    fps=self.fps_calculator.update(current_time),
                    calculation_time=processing_time_end - processing_time_start,
                    all_intensities=self.vibe_manager.all_intensities))

        await self.vibe_manager.stop_all_devices(self.get_devices())
        logging.info("Stopped.")

        duration = time.time() - start_time
        logging.info(
            f"Loops: {counter} | "
            f"Loops per second: {round(counter / max(duration, 1.0), 2)} | "
            f"Avg. time: {round(1000 * (duration / max(counter, 1)), 2)}ms")

    def get_devices(self) -> list[Device]:
        return [device for device in self.client.devices.values()
                if device.name not in self.config.excluded_device_names]

    def update_user_settings(
            self,
            hero_auto_detect: bool,
            hero: Hero2,
            responses: Mapping[Hero2, Mapping[Trigger, Response]],
    ) -> None:
        self.player_state.switch_hero(hero_auto_detect, hero)
        self.responses = responses
