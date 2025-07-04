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
import os
from typing import NamedTuple

import cv2
import dxcam_cpp
import numpy

from .utils import Config


class Coord(NamedTuple):
    top: int
    left: int
    add_height: int = 0
    add_width: int = 0
    more: list[tuple[int, int]] | None = None
    offsets: list[tuple[int, int]] | None = None


class Resolution(NamedTuple):
    width: int
    height: int


class ComputerVision:
    COORDS: dict[str, Coord] = {
        "elimination": Coord(751, 833, 0, 100),  # Notif in first row
        "assist": Coord(751, 833, 0, 100),  # Notif in first row
        "save": Coord(751, 729, 0, 125),  # Notif in first row
        "killcam": Coord(89, 41, 6, 7),
        "death_spec": Coord(66, 1416, 1, 3),
        "being_beamed": Coord(763, 461),
        "being_orbed": Coord(760, 465, 0, 120),  # Can be pushed right by Mercy beam icon
        "hacked": Coord(860, 172),
        "overtime": Coord(37, 903, 1, 1),
        "baptiste_weapon": Coord(963, 1722),
        "brigitte_weapon": Coord(958, 1697),
        "kiriko_weapon": Coord(964, 1682),
        "lucio_weapon": Coord(958, 1702),
        "lucio_heal": Coord(668, 796),
        "lucio_speed": Coord(668, 1093),
        "mercy_staff": Coord(958, 1768),
        "mercy_pistol": Coord(946, 1669),
        "mercy_pistol_ult": Coord(945, 1669),  # Pistol icon changes during ult
        "mercy_heal_beam": Coord(672, 807),
        "mercy_damage_beam": Coord(673, 1080),
        "mercy_resurrect_cd": Coord(931, 1581, offsets=[
            (-1, -18),  # With controller
            (-3, -78),  # With Flash Heal perk
            (-4, -96),  # With Flash Heal perk and controller
        ]),
        "mercy_flash_heal": Coord(934, 1581, offsets=[
            (-1, -18),  # With controller
        ]),
        "zenyatta_weapon": Coord(966, 1717),
        "zenyatta_harmony": Coord(954, 738),
        "zenyatta_discord": Coord(954, 1157),
        "juno_weapon": Coord(950, 1679),
        "juno_glide_boost": Coord(931, 1425),
        "juno_pulsar_torpedoes": Coord(940, 1581),
        "endorsement": Coord(936, 73, more=[(73, 890), (73, 641), (73, 595)]),
    }
    MASK_NAMES: list[str] = [
    ]

    def __init__(self, config: Config, template_path: str) -> None:
        self.config = config

        # Define the base screen resolution used for all detections
        self.base_resolution = Resolution(width=1920, height=1080)
        self.base_aspect_ratio = self.base_resolution.width / self.base_resolution.height

        # Detect the user's screen resolution
        self.camera = dxcam_cpp.create(self.config.gpu_id, self.config.monitor_id, max_buffer_len=1)
        test_frame_shape = self.camera.grab().shape
        self.user_resolution = Resolution(width=test_frame_shape[1], height=test_frame_shape[0])
        self.user_aspect_ratio = self.user_resolution.width / self.user_resolution.height
        logging.info(f"Detected monitor resolution {self.user_resolution} "
                     f"and aspect ratio {self.user_aspect_ratio:.3f}:1")

        # Create record of improved resolution detection
        user_resolution_improved = Resolution(width=self.camera.width, height=self.camera.height)
        logging.info(f"Detected monitor resolution {user_resolution_improved} (test of new approach)")

        # Enable frame cropping, if the users aspect ratio differs from the base aspect ratio
        self.horizontal_padding: int | None = None
        self.vertical_padding: int | None = None
        if self.user_aspect_ratio != self.base_aspect_ratio:
            logging.warning("Please ensure that your in-game aspect ratio is set to 16:9! "
                            "If it already is, disregard this message.")
            if self.user_aspect_ratio > self.base_aspect_ratio:
                new_width = int(self.user_resolution.height * self.base_aspect_ratio)
                self.horizontal_padding = (self.user_resolution.width - new_width) // 2
            else:
                new_height = int(self.user_resolution.width / self.base_aspect_ratio)
                self.vertical_padding = (self.user_resolution.height - new_height) // 2

        # Prepare templates, masks, and the frame variable
        self.templates = {}
        for key in self.COORDS:
            filename = os.path.join(template_path, f"t_{key}.png")
            template = cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
            assert template is not None, f"Failed to read template {filename}"
            self.templates[key] = template
        self.masks = {}
        for key in self.MASK_NAMES:
            filename = os.path.join(template_path, f"m_{key}.png")
            mask = cv2.imread(os.path.join(template_path, f"m_{key}.png"), cv2.IMREAD_GRAYSCALE)
            assert mask is not None, f"Failed to read mask {filename}"
            self.masks[key] = mask
        self.frame: numpy.ndarray = numpy.empty(shape=(0, 0), dtype=numpy.uint8)

    def start_capturing(self, target_fps: int = 60) -> None:
        self.camera.start(target_fps=target_fps, video_mode=True)

    def stop_capturing(self) -> None:
        self.camera.stop()
        self.camera.release()
        # Close preview window
        if self.config.preview_window:
            cv2.destroyAllWindows()

    def wait_for_frame(self) -> None:
        self.frame = self.camera.get_latest_frame()

    def capture_frame(self) -> None:
        # Show preview window with original
        if self.config.preview_window:
            preview = cv2.resize(self.frame, (self.frame.shape[1] // 4, self.frame.shape[0] // 4))
            cv2.imshow("OverStim Preview Original", preview)
        # Prepare the frame
        if self.horizontal_padding is not None:
            self.frame = self.frame[:, self.horizontal_padding:-self.horizontal_padding]
        elif self.vertical_padding is not None:
            self.frame = self.frame[self.vertical_padding:-self.vertical_padding, :]
        if self.frame.shape[1] != self.base_resolution.width or self.frame.shape[0] != self.base_resolution.height:
            self.frame = cv2.resize(self.frame, (self.base_resolution.width, self.base_resolution.height))
        self.frame = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        # Show preview window
        if self.config.preview_window:
            preview = cv2.resize(self.frame, (self.frame.shape[1] // 4, self.frame.shape[0] // 4))
            cv2.imshow("OverStim Preview Processed", preview)
            cv2.waitKey(1)

    def detect_single(self, template_name: str, threshold: float = 0.9, coord_override: Coord | None = None) -> bool:
        # Get detection coordinates
        if coord_override is not None:
            coord = coord_override
        else:
            coord = self.COORDS[template_name]
        # Get top left points
        points = [(coord.left, coord.top)]
        if coord.more is not None:
            points.extend(coord.more)
        if coord.offsets is not None:
            for offset in coord.offsets:
                points.append((coord.left + offset[1], coord.top + offset[0]))
        # Check each offset
        template = self.templates[template_name]
        height = template.shape[0] + coord.add_height
        width = template.shape[1] + coord.add_width
        for point in points:
            left, top = point
            cropped_frame = self.frame[top:top + height, left:left + width]
            mask = self.masks.get(template_name, None)
            result = cv2.matchTemplate(cropped_frame, template, cv2.TM_CCOEFF_NORMED, mask=mask)
            score = float(numpy.nanmax(result))
            if score > threshold:
                return True
        return False

    def detect_color(self, xy: tuple[int, int], target: float, deviation: float) -> bool:
        color = self.frame[xy[1], xy[0]] / 255.0
        diff = abs(color - target)
        return diff <= deviation
