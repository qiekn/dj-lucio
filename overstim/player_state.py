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

import os
import time
from typing import NamedTuple

from .computer_vision import ComputerVision
from .heroes import Hero2, Hero, Other, Juno, Lucio, Mercy, Zenyatta
from .utils import Config


class Notif(NamedTuple):
    notif_type: str
    expiry_time: float


class PlayerState:
    def __init__(self, config: Config, asset_path: str) -> None:
        self.config = config
        self.computer_vision = ComputerVision(self.config, os.path.join(asset_path, "templates"))
        self.current_time = 0
        self.supported_heroes: dict[Hero2, Hero] = {
            Hero2.JUNO: Juno(),
            Hero2.LUCIO: Lucio(),
            Hero2.MERCY: Mercy(),
            Hero2.ZENYATTA: Zenyatta(),
        }
        self.hero: Hero = Other()
        self.detected_hero: Hero2 = Hero2.OTHER
        self.detected_hero_time = 0
        self.last_hero_detection_attempt_time = 0
        self.hero_auto_detect = True
        self.in_killcam = False
        self.death_spectating = False
        self.is_dead = False
        self.notifs: list[Notif] = []
        self.new_notifs: dict[str, int] = {}
        self.being_beamed = False
        self.being_orbed = False
        self.hacked = False
        self.endorsed = False

    def wait_for_frame(self) -> None:
        self.computer_vision.wait_for_frame()

    def refresh(self) -> None:
        self.computer_vision.capture_frame()

        # TODO: Shouldn't check for things that aren't enabled in the config
        self.current_time = time.time()
        self.expire_notifs()
        self.new_notifs = {}

        # TODO: Find out if the player is alive (there is a period of time between death and kill cam, should handle
        #  that with "you were eliminated" message and a timer)
        self.in_killcam = self.computer_vision.detect_single("killcam")
        if not self.in_killcam:
            self.death_spectating = self.computer_vision.detect_single("death_spec")
        player_is_alive = not (self.in_killcam or self.death_spectating)

        self.endorsed = self.computer_vision.detect_single("endorsement")

        if player_is_alive:
            if self.is_dead:
                self.is_dead = False

            self.detect_new_notifs()

            self.being_beamed = self.computer_vision.detect_single("being_beamed")

            self.being_orbed = self.computer_vision.detect_single("being_orbed")

            self.hacked = self.computer_vision.detect_single("hacked")

            if self.hero.name is Hero2.OTHER:
                pass
            elif self.hero.name is Hero2.MERCY:
                self.hero.detect_beams(self.computer_vision)
                if self.count_notifs_of_type("save") > 0:
                    # Could we use self.new_notifs here or is rez icon too delayed?
                    self.hero.detect_resurrect(self.computer_vision)
                self.hero.detect_flash_heal(self.computer_vision)
            else:
                self.hero.detect_all(self.computer_vision)

            if self.hero_auto_detect:
                # Check for current hero once per second.
                # If not found after 3 seconds, check for every hero each second (starting with heroes in the same role).
                # If not found after 6 seconds (total), switch to Other.
                time_since_successful_hero_detection = self.current_time - self.detected_hero_time
                time_since_attempted_hero_detection = self.current_time - self.last_hero_detection_attempt_time
                if time_since_attempted_hero_detection >= 1:
                    if self.hero.name is Hero2.OTHER:
                        if time_since_attempted_hero_detection >= 2:
                            self.detect_hero()  # Detect all heroes
                    else:
                        if time_since_successful_hero_detection >= 4:
                            self.detect_hero(prioritize_current_role=True)  # Detect all heroes, starting with same role
                        else:
                            self.detect_hero(current_hero_only=True)  # Detect just self.hero

        # If player is dead:
        else:
            if not self.is_dead:
                self.is_dead = True
                self.being_beamed = False
                self.being_orbed = False
                self.hacked = False
                self.hero.reset_attributes()

    def detect_hero(self, current_hero_only: bool = False, prioritize_current_role: bool = False) -> None:
        hero_detected = False
        if current_hero_only:
            if self.hero.detect_hero(self.computer_vision):
                self.detected_hero_time = self.current_time
                hero_detected = True
        else:
            if prioritize_current_role:
                heroes_to_detect = self.get_supported_heroes_prioritizing_current_role()
            else:
                heroes_to_detect = self.supported_heroes
            for hero in heroes_to_detect.values():
                if hero.detect_hero(self.computer_vision):
                    self.detected_hero = hero.name
                    self.detected_hero_time = self.current_time
                    hero_detected = True
                    break
        # If no supported hero has been detected within the last 8 seconds:
        time_since_successful_hero_detection = self.current_time - self.detected_hero_time
        if not hero_detected and self.detected_hero is not Hero2.OTHER and time_since_successful_hero_detection >= 6:
            self.detected_hero = Hero2.OTHER
        self.last_hero_detection_attempt_time = self.current_time

    def switch_hero(self, hero_auto_detect: bool, hero: Hero2) -> None:
        self.hero.reset_attributes()
        self.hero_auto_detect = hero_auto_detect
        if not hero_auto_detect:
            if hero is Hero2.OTHER:
                self.hero = Other()
            else:
                self.hero = self.supported_heroes[hero]

    def detect_new_notifs(self) -> None:
        # Coords are for the first row
        notif_types = ["elimination", "assist", "save"]

        notifs = {}
        for row in range(0, 2):
            pixel_offset = row * 35  # Pixels between rows @ 1080p
            no_notif_detected = True
            for notif_type in notif_types:
                notif_coord = self.computer_vision.COORDS[notif_type]
                notif_coord = notif_coord._replace(top=notif_coord.top + row * pixel_offset)
                if self.computer_vision.detect_single(notif_type, coord_override=notif_coord):
                    no_notif_detected = False
                    notifs[notif_type] = notifs.get(notif_type, 0) + 1
                    # If a notif was detected on this row, no need to check for other notifs on this row
                    break
            # If no notif was detected on this row, no need to check the next row
            if no_notif_detected:
                break

        for notif_type, notifs_detected in notifs.items():
            existing_notifs = self.count_notifs_of_type(notif_type)
            new_notifs = max(0, notifs_detected - existing_notifs)
            for _ in range(new_notifs):
                self.add_notif(notif_type)
            self.new_notifs[notif_type] = new_notifs

    def count_notifs_of_type(self, notif_type: str) -> int:
        return sum(notif[0] == notif_type for notif in self.notifs)

    def get_expired_items(self) -> list[Notif]:
        expired_items = []
        for notif in self.notifs:
            if notif.expiry_time <= self.current_time:
                expired_items.append(notif)
            else:
                break
        return expired_items

    def expire_notifs(self) -> None:
        for expired_notif in self.get_expired_items():
            self.notifs.remove(expired_notif)

    def add_notif(self, notif_type: str) -> None:
        if len(self.notifs) == 3:
            del self.notifs[0]
        self.notifs.append(Notif(notif_type=notif_type, expiry_time=self.current_time + 2.705))

    def start_tracking(self, refresh_rate: int) -> None:
        self.computer_vision.start_capturing(refresh_rate)

    def stop_tracking(self) -> None:
        self.computer_vision.stop_capturing()

    def get_supported_heroes_prioritizing_current_role(self) -> dict[str, Hero]:
        current_role_heroes = {name: hero for name, hero in self.supported_heroes.items() if
                               hero.role == self.hero.role}
        other_heroes = {name: hero for name, hero in self.supported_heroes.items() if hero.role != self.hero.role}
        sorted_heroes = {**current_role_heroes, **other_heroes}

        return sorted_heroes
