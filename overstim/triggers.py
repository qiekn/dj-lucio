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
import json
from collections.abc import Iterator
from typing import NamedTuple

from .heroes import Hero2
from .utils import format_enum, format_float


class ResponseType(enum.Enum):
    CONSTANT = 1
    PATTERN = 2
    SILENCE = 3


class Vibration(NamedTuple):
    intensity: float
    duration: float

    def __str__(self) -> str:
        return f"{self.intensity * 100:.0f}% {format_float(self.duration)}s"

    @classmethod
    def from_str(cls, value: str) -> "Vibration":
        parts = value.split(" ")
        parts = [part.strip().strip("%s") for part in parts]
        parts = [part for part in parts if part]
        return cls(intensity=float(parts[0]) / 100.0,
                   duration=float(parts[1]))


class Pattern(list[Vibration]):
    def __str__(self) -> str:
        return ', '.join(str(vibration) for vibration in self)

    @classmethod
    def from_str(cls, value: str) -> "Pattern":
        pattern = cls()
        for part in value.split(","):
            part = part.strip()
            if part:
                pattern.append(Vibration.from_str(part))
        return pattern

    @property
    def short_str(self) -> str:
        max_items = 2
        text = " ".join(f"{vibration.intensity * 100:.0f}%" for vibration in self[:max_items])
        if len(self) > max_items:
            text += " ..."
        return text

    @property
    def duration(self) -> float:
        return sum(vibration.duration for vibration in self)


class Response(NamedTuple):
    type: ResponseType = ResponseType.CONSTANT
    intensity: float = 0.1
    duration: float = 1.0
    pattern: Pattern = Pattern()
    pattern_loop: int = 1

    def __str__(self) -> str:
        response_dict = self._asdict()
        response_dict["type"] = self.type.name
        response_dict["pattern"] = [vibration._asdict() for vibration in self.pattern]
        return json.dumps(response_dict)

    @classmethod
    def from_str(cls, value: str) -> "Response":
        response_dict = json.loads(value)
        pattern = Pattern(Vibration(intensity=vibration_dict["intensity"],
                                    duration=vibration_dict["duration"])
                          for vibration_dict in response_dict["pattern"])
        response = cls(type=ResponseType[response_dict["type"]],
                       intensity=response_dict["intensity"],
                       duration=response_dict["duration"],
                       pattern=pattern,
                       pattern_loop=response_dict["pattern_loop"])
        response.validate()
        return response

    @property
    def vibe_str(self) -> str:
        if self.type is ResponseType.CONSTANT:
            return f"{self.intensity * 100:.0f}%"
        if self.type is ResponseType.PATTERN:
            return self.pattern.short_str
        if self.type is ResponseType.SILENCE:
            return format_enum(self.type)
        return ""

    @property
    def duration_str(self) -> str:
        if self.type in [ResponseType.CONSTANT, ResponseType.SILENCE]:
            return f"{format_float(self.duration)} secs"
        if self.type is ResponseType.PATTERN:
            return f"{self.pattern_loop} loops"
        return ""

    def validate(self) -> None:
        if self.type is ResponseType.PATTERN:
            assert self.pattern.duration > 0.0, "The pattern is empty or too short."

    def get_intensity(self, timestamp: float, unlimited: bool) -> float | None:
        if self.type is ResponseType.CONSTANT:
            if timestamp < self.duration or unlimited:
                return self.intensity
        if self.type is ResponseType.PATTERN:
            pattern_duration = self.pattern.duration
            repetition, position = divmod(timestamp, pattern_duration)
            if repetition < self.pattern_loop or unlimited:
                split = 0.0
                for vibration in self.pattern:
                    if split + vibration.duration > position:
                        return vibration.intensity
                    split += vibration.duration
        if self.type is ResponseType.SILENCE:
            if timestamp < self.duration or unlimited:
                return -1.0
        return None


class Trigger(enum.Enum):
    ELIMINATION = 1
    ASSIST = 2
    SAVE = 3
    HACKED_BY_SOMBRA = 4
    BEAMED_BY_MERCY = 5
    ORBED_BY_ZENYATTA = 6
    RESURRECT = 7
    FLASH_HEAL = 8
    HEAL_BEAM = 9
    DAMAGE_BEAM = 10
    GLIDE_BOOST = 11
    PULSAR_TORPEDOES_LOCK = 12
    PULSAR_TORPEDOES_FIRE = 13
    HEALING_SONG = 14
    SPEED_SONG = 15
    HARMONY_ORB = 16
    DISCORD_ORB = 17
    ENDORSEMENT_RECEIVED = 18


TRIGGERS_GENERIC: dict[Trigger, Response] = {
    Trigger.ELIMINATION: Response(type=ResponseType.CONSTANT, intensity=0.3, duration=6.0),
    Trigger.ASSIST: Response(type=ResponseType.CONSTANT, intensity=0.15, duration=3.0),
    Trigger.SAVE: Response(type=ResponseType.CONSTANT, intensity=0.5, duration=4.0),
    Trigger.HACKED_BY_SOMBRA: Response(
        type=ResponseType.SILENCE,
        pattern=Pattern([Vibration(1.0, 0.5), Vibration(0.3, 0.5), Vibration(0.6, 0.5), Vibration(0.3, 0.25),
                         Vibration(1.0, 0.75), Vibration(0.0, 0.25), Vibration(1.0, 0.5), Vibration(0.0, 0.25),
                         Vibration(0.6, 0.5), Vibration(0.3, 0.5), Vibration(1.0, 0.5)])),
    Trigger.BEAMED_BY_MERCY: Response(type=ResponseType.CONSTANT, intensity=0.3),
    Trigger.ORBED_BY_ZENYATTA: Response(type=ResponseType.CONSTANT, intensity=0.3),
    Trigger.ENDORSEMENT_RECEIVED: Response(
        type=ResponseType.PATTERN,
        pattern=Pattern([Vibration(1.0, 0.1), Vibration(0.0, 0.1), Vibration(1.0, 0.1), Vibration(0.0, 0.1),
                         Vibration(1.0, 3.5)])),
}


TRIGGERS_SPECIFIC: dict[Hero2, dict[Trigger, Response]] = {
    Hero2.MERCY: {
        Trigger.HEAL_BEAM: Response(type=ResponseType.CONSTANT, intensity=0.1),
        Trigger.DAMAGE_BEAM: Response(type=ResponseType.CONSTANT, intensity=0.3),
        Trigger.RESURRECT: Response(type=ResponseType.CONSTANT, intensity=1.0, duration=4.0),
        Trigger.FLASH_HEAL: Response(type=ResponseType.CONSTANT, intensity=1.0, duration=0.5),
    },
    Hero2.JUNO: {
        Trigger.GLIDE_BOOST: Response(
            type=ResponseType.PATTERN, duration=4.0,
            pattern=Pattern([Vibration(0.10, 1.0), Vibration(0.15, 1.0), Vibration(0.20, 1.0), Vibration(0.25, 1.0)])),
        Trigger.PULSAR_TORPEDOES_LOCK: Response(
            type=ResponseType.PATTERN,
            pattern=Pattern([Vibration(0.15, 0.5), Vibration(0.20, 0.5), Vibration(0.25, 0.5), Vibration(0.30, 0.5),
                             Vibration(0.35, 0.5), Vibration(0.40, 0.5), Vibration(0.45, 0.5), Vibration(0.50, 0.5)])),
        Trigger.PULSAR_TORPEDOES_FIRE: Response(type=ResponseType.CONSTANT, intensity=1.0, duration=1.3),
    },
    Hero2.LUCIO: {
        Trigger.HEALING_SONG: Response(type=ResponseType.CONSTANT, intensity=0.15),
        Trigger.SPEED_SONG: Response(type=ResponseType.CONSTANT, intensity=0.3),
    },
    Hero2.ZENYATTA: {
        Trigger.HARMONY_ORB: Response(type=ResponseType.CONSTANT, intensity=0.15),
        Trigger.DISCORD_ORB: Response(type=ResponseType.CONSTANT, intensity=0.2),
    },
}


def hero_triggers(hero: Hero2) -> Iterator[Trigger]:
    yield from TRIGGERS_SPECIFIC.get(hero, {}).keys()
    yield from TRIGGERS_GENERIC.keys()


TRIGGERS_CONDITIONAL = {
    Trigger.HACKED_BY_SOMBRA,
    Trigger.BEAMED_BY_MERCY,
    Trigger.ORBED_BY_ZENYATTA,
    Trigger.HEAL_BEAM,
    Trigger.DAMAGE_BEAM,
    Trigger.PULSAR_TORPEDOES_LOCK,
    Trigger.HEALING_SONG,
    Trigger.SPEED_SONG,
    Trigger.HARMONY_ORB,
    Trigger.DISCORD_ORB,
}


def is_conditional(trigger: Trigger) -> bool:
    return trigger in TRIGGERS_CONDITIONAL


def default_response(hero: Hero2, trigger: Trigger) -> Response:
    try:
        return TRIGGERS_GENERIC[trigger]
    except KeyError:
        pass
    try:
        return TRIGGERS_SPECIFIC[hero][trigger]
    except KeyError:
        pass
    return Response()
