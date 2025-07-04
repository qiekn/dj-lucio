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

import atexit
import logging.handlers
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow


def create_lock_file(lock_file_path):
    try:
        # Try to create a lock file exclusively
        fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except OSError:
        # Lock file already exists, another instance is running
        return False
    return True


def remove_lock_file(lock_file_path):
    try:
        os.unlink(lock_file_path)
    except OSError:
        pass


def main() -> None:
    # Prepare paths
    path = os.path.dirname(os.path.dirname(__file__))
    path_assets = os.path.join(path, "assets")
    path_log = os.path.join(path, "log")
    path_lock = os.path.join(path, "OverStim.lock")

    # Create the application instance
    app = QApplication(sys.argv)

    # Create lock file
    if not create_lock_file(path_lock):
        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Warning")
        message_box.setText("It seems that another instance of OverStim is already running.")
        message_box.setStandardButtons(QMessageBox.Ignore | QMessageBox.Abort)
        message_box.setDefaultButton(QMessageBox.Abort)
        result = message_box.exec()
        if result == QMessageBox.Ignore:
            logging.warning("Ignoring the lock file")
        else:
            sys.exit(1)
    atexit.register(remove_lock_file, path_lock)

    # Set up logging
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)d - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    # Stream handler for logging to console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # File handler to create a log file
    if not os.path.exists(path_log):
        os.mkdir(path_log)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(path_log, "OverStim_Log.txt"), when="d", interval=1, backupCount=3)
    file_handler.setFormatter(formatter)
    file_handler.namer = lambda default_name: default_name + ".txt"  # ensure that old log files keep the file extension
    logger.addHandler(file_handler)

    # Read version file
    filename = os.path.join(os.path.dirname(__file__), "version.txt")
    with open(filename) as file:
        version = file.read().strip()
    logging.info(f"Starting version {version}")

    # Start application
    main_window = MainWindow(version, path, path_assets, path_log)
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
