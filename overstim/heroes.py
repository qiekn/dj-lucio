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

import abc
import enum

from .computer_vision import ComputerVision


class Hero2(enum.Enum):
    MERCY = 1
    JUNO = 2
    LUCIO = 3
    ZENYATTA = 4
    OTHER = 5


class Hero(abc.ABC):
    def __init__(self, name: Hero2, role: str, weapons: list[str] | None = None) -> None:
        self.name = name
        self.role = role
        if weapons is None:
            self.weapons = [self.name.name.lower() + "_weapon"]
        else:
            self.weapons = weapons
        self.reset_attributes()

    def detect_hero(self, computer_vision: ComputerVision) -> bool:
        for weapon in self.weapons:
            if computer_vision.detect_single(weapon, threshold=0.97):
                return True
        return False

    def reset_attributes(self) -> None:
        pass

    def detect_all(self, computer_vision: ComputerVision) -> None:
        pass


class Other(Hero):
    def __init__(self) -> None:
        super().__init__(name=Hero2.OTHER, role="Other")

    def detect_hero(self, computer_vision: ComputerVision) -> bool:
        return False


class Juno(Hero):
    def __init__(self) -> None:
        super().__init__(name=Hero2.JUNO, role="Support")
        self.glide_boost = False
        self.pulsar_torpedoes_lock = False
        self.pulsar_torpedoes_firing = False
        self.pulsar_torpedoes_buffer = 0

    def reset_attributes(self) -> None:
        self.glide_boost = False
        self.pulsar_torpedoes_lock = False
        self.pulsar_torpedoes_firing = False

    def detect_glide_boost(self, computer_vision: ComputerVision) -> None:
        self.glide_boost = computer_vision.detect_single("juno_glide_boost", threshold=0.85)

    def detect_pulsar_torpedoes(self, computer_vision: ComputerVision) -> None:
        if computer_vision.detect_single("juno_pulsar_torpedoes"):
            self.pulsar_torpedoes_buffer = 11
        else:
            self.pulsar_torpedoes_buffer -= 1
        if self.pulsar_torpedoes_buffer >= 0:
            coords_l = (464, 346)
            coords_r = (1920 - coords_l[0], coords_l[1])
            self.pulsar_torpedoes_firing = (computer_vision.detect_color(coords_l, 1.0, 0.05) or
                                            computer_vision.detect_color(coords_r, 1.0, 0.05))
            self.pulsar_torpedoes_lock = not self.pulsar_torpedoes_firing
        else:
            self.pulsar_torpedoes_lock = False
            self.pulsar_torpedoes_firing = False

    def detect_all(self, computer_vision: ComputerVision) -> None:
        self.detect_glide_boost(computer_vision)
        self.detect_pulsar_torpedoes(computer_vision)


class Lucio(Hero):
    def __init__(self) -> None:
        super().__init__(name=Hero2.LUCIO, role="Support")
        self.crossfade_buffer_size = 6  # Overridden by config
        self.healing_song = False
        self.speed_song = False
        self.healing_song_buffer = 0
        self.speed_song_buffer = 0

    def reset_attributes(self) -> None:
        self.healing_song = False
        self.speed_song = False
        self.healing_song_buffer = 0
        self.speed_song_buffer = 0

    def detect_song(self, computer_vision: ComputerVision) -> None:
        if computer_vision.detect_single("lucio_heal"):
            self.healing_song = True
            self.speed_song = False
            self.healing_song_buffer = 0
            self.speed_song_buffer = 0
        elif self.healing_song:
            self.healing_song_buffer += 1
            if self.healing_song_buffer >= self.crossfade_buffer_size:
                self.healing_song = False

        # Can we skip this section if the previous section is True?
        if computer_vision.detect_single("lucio_speed"):
            self.speed_song = True
            self.healing_song = False
            self.speed_song_buffer = 0
            self.healing_song_buffer = 0
        elif self.speed_song:
            self.speed_song_buffer += 1
            if self.speed_song_buffer >= self.crossfade_buffer_size:
                self.speed_song = False

    def detect_all(self, computer_vision: ComputerVision) -> None:
        self.detect_song(computer_vision)


class Mercy(Hero):
    def __init__(self) -> None:
        super().__init__(name=Hero2.MERCY, role="Support", weapons=[
            "mercy_staff",
            "mercy_pistol",
            "mercy_pistol_ult",
        ])
        self.beam_disconnect_buffer_size = 8  # Overridden by config
        self.heal_beam = False
        self.damage_beam = False
        self.resurrecting = False
        self.flash_heal = False
        self.heal_beam_buffer = 0
        self.damage_beam_buffer = 0

    def reset_attributes(self) -> None:
        self.heal_beam = False
        self.damage_beam = False
        self.resurrecting = False
        self.flash_heal = False
        self.heal_beam_buffer = 0
        self.damage_beam_buffer = 0

    def detect_beams(self, computer_vision: ComputerVision) -> None:
        if computer_vision.detect_single("mercy_heal_beam"):
            self.heal_beam = True
            self.damage_beam = False
            self.heal_beam_buffer = 0
            self.damage_beam_buffer = 0
        elif self.heal_beam:
            self.heal_beam_buffer += 1
            if self.heal_beam_buffer >= self.beam_disconnect_buffer_size:
                self.heal_beam = False

        # Can we skip this section if the previous section is True?
        if computer_vision.detect_single("mercy_damage_beam"):
            self.damage_beam = True
            self.heal_beam = False
            self.damage_beam_buffer = 0
            self.heal_beam_buffer = 0
        elif self.damage_beam:
            self.damage_beam_buffer += 1
            if self.damage_beam_buffer >= self.beam_disconnect_buffer_size:
                self.damage_beam = False

    def detect_resurrect(self, computer_vision: ComputerVision) -> None:
        self.resurrecting = computer_vision.detect_single("mercy_resurrect_cd")

    def detect_flash_heal(self, computer_vision: ComputerVision) -> None:
        self.flash_heal = computer_vision.detect_single("mercy_flash_heal")


class Zenyatta(Hero):
    def __init__(self) -> None:
        super().__init__(name=Hero2.ZENYATTA, role="Support")
        # Orbs take up to 0.8s to switch targets at max range (w/ ~40ms RTT)
        self.orb_disconnect_buffer_size = 30  # Overridden by config
        self.harmony_orb = False
        self.discord_orb = False
        self.harmony_orb_buffer = 0
        self.discord_orb_buffer = 0

    def reset_attributes(self) -> None:
        self.harmony_orb = False
        self.discord_orb = False
        self.harmony_orb_buffer = 0
        self.discord_orb_buffer = 0

    def detect_orbs(self, computer_vision: ComputerVision) -> None:
        if computer_vision.detect_single("zenyatta_harmony"):
            self.harmony_orb = True
            self.harmony_orb_buffer = 0
        elif self.harmony_orb:
            self.harmony_orb_buffer += 1
            if self.harmony_orb_buffer >= self.orb_disconnect_buffer_size:
                self.harmony_orb = False

        if computer_vision.detect_single("zenyatta_discord"):
            self.discord_orb = True
            self.discord_orb_buffer = 0
        elif self.discord_orb:
            self.discord_orb_buffer += 1
            if self.discord_orb_buffer >= self.orb_disconnect_buffer_size:
                self.discord_orb = False

    def detect_all(self, computer_vision: ComputerVision) -> None:
        self.detect_orbs(computer_vision)
