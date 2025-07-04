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
import collections
import functools
import logging
import os

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QSettings
from PySide6.QtGui import QCloseEvent, QPixmap, QIcon, QAction, QColor, QPalette
from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QGridLayout, QComboBox, QLabel, QDialog, QMessageBox, QProgressBar, QTreeWidget,
    QTreeWidgetItem, QLineEdit, QSpinBox, QDoubleSpinBox, QAbstractItemView, QHeaderView, QFormLayout, QCheckBox,
    QDialogButtonBox, QHBoxLayout, QSizePolicy)
from pynput import keyboard

from .controller import Controller, ControllerInfo
from .heroes import Hero2
from .triggers import Trigger, is_conditional, hero_triggers, Response, ResponseType, Pattern, default_response
from .utils import Config, format_enum


class MainWindow(QMainWindow):
    DATA_HERO = 0
    DATA_TRIGGER = 1

    def __init__(self, version: str, path: str, path_assets: str, path_log: str) -> None:
        super().__init__()
        self.version = version
        self.path = path
        self.path_assets = path_assets
        self.path_log = path_log
        self.color_default = self.palette().color(QPalette.WindowText)
        self.color_highlight = QColor('#FE0080')
        self.current_hero: Hero2 | None = None

        # INITIALIZE SETTINGS ##########################################################################################

        self.settings = QSettings("OverStim", "OverStim")
        self.config = self.get_settings_config()

        # INITIALIZE USER INTERFACE ####################################################################################

        # Trigger and pattern box
        self.trigger_tree = QTreeWidget()
        self.trigger_tree.setHeaderLabels(["Hero / Trigger", "Vibe", "Duration", "Active"])
        for hero in Hero2:
            item = QTreeWidgetItem([format_enum(hero)])
            item.setData(0, Qt.UserRole + self.DATA_HERO, hero)
            for trigger in hero_triggers(hero):
                response = self.get_settings_response(hero, trigger)
                enabled = self.get_settings_enabled(hero, trigger)
                child = QTreeWidgetItem([format_enum(trigger)])
                child.setData(0, Qt.UserRole + self.DATA_HERO, hero)
                child.setData(0, Qt.UserRole + self.DATA_TRIGGER, trigger)
                child.setData(1, Qt.UserRole, response)
                child.setCheckState(1, Qt.Checked if enabled else Qt.Unchecked)
                item.addChild(child)
            self.trigger_tree.addTopLevelItem(item)
        self.trigger_tree.expandAll()
        self.trigger_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.trigger_tree.itemChanged.connect(self.slot_trigger_changed)
        self.trigger_tree.itemDoubleClicked.connect(self.slot_trigger_double_click)
        self.update_trigger_table()

        # Hero selection box
        # FIXME: Fix and re-enable auto-detect
        hero_select_items = []  # ["Auto-detect"]
        hero_select_items.extend(format_enum(hero) for hero in Hero2)
        self.hero_select_combo = QComboBox()
        self.hero_select_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hero_select_combo.addItems(hero_select_items)
        self.hero_select_combo.setCurrentIndex(self.get_settings_playing_hero())
        self.hero_select_combo.currentIndexChanged.connect(self.update_controller)
        hero_select = QHBoxLayout()
        hero_select.addWidget(QLabel("Playing hero:"))
        hero_select.addWidget(self.hero_select_combo)

        # Vibration progress bar
        self.vibe_intensity_bar = QProgressBar()
        self.vibe_intensity_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.vibe_intensity_bar.setRange(0, 1000)
        vibe_intensity = QHBoxLayout()
        vibe_intensity.addWidget(QLabel("Intensity:"))
        vibe_intensity.addWidget(self.vibe_intensity_bar)

        # Widget layout
        central_layout = QVBoxLayout()
        central_layout.addLayout(hero_select)
        central_layout.addWidget(self.trigger_tree)
        central_layout.addLayout(vibe_intensity)
        central_widget = QWidget()
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)
        self.setWindowTitle("OverStim")
        self.setWindowIcon(QIcon(os.path.join(self.path_assets, "icon.ico")))
        self.resize(420, 380)

        # TOOL BAR #####################################################################################################

        tool_bar = self.addToolBar("OverStim")
        tool_bar.setMovable(False)

        self.action_start = QAction("Start")
        self.action_start.triggered.connect(self.slot_control_start_button)
        tool_bar.addAction(self.action_start)

        self.action_stop = QAction("Stop")
        self.action_stop.setEnabled(False)
        self.action_stop.triggered.connect(self.slot_control_stop_button)
        tool_bar.addAction(self.action_stop)

        self.action_config = QAction("Settings")
        self.action_config.triggered.connect(self.slot_settings_dialog)
        tool_bar.addAction(self.action_config)

        self.action_about = QAction("About")
        self.action_about.triggered.connect(self.slot_about_dialog)
        tool_bar.addAction(self.action_about)

        self.action_log = QAction("Log")
        self.action_log.triggered.connect(functools.partial(os.startfile, self.path_log))
        tool_bar.addAction(self.action_log)

        self.action_reset = QAction("Reset")
        self.action_reset.triggered.connect(self.slot_reset_button)
        tool_bar.addAction(self.action_reset)

        # STATUS BAR ###################################################################################################

        self.status_program = QLabel()
        self.status_program.setToolTip("Program status")
        self.status_devices = QLabel()
        self.status_devices.setToolTip("Connected devices")
        self.status_fps = QLabel()
        self.status_fps.setToolTip("Detection frames per second")
        self.status_calculation_time = QLabel()
        self.status_calculation_time.setToolTip("Calculation time per frame")
        status_bar = self.statusBar()
        status_bar.addPermanentWidget(self.status_program, 1)
        status_bar.addPermanentWidget(self.status_devices, 1)
        status_bar.addPermanentWidget(self.status_fps, 1)
        status_bar.addPermanentWidget(self.status_calculation_time, 1)
        self.update_controller_info()

        # INITIALIZE PROGRAM CONTROLLER ################################################################################

        # Controller thread to perform main program functions
        self.controller_thread: ControllerThread | None = None

        # Close the application after the controller thread is stopped
        self.stop_request = False
        self.stop_request_timer = QTimer()
        self.stop_request_timer.timeout.connect(self.check_stop_request)
        self.stop_request_timer.setInterval(500)
        self.stop_request_timer.start(500)

        # Set up global keyboard hotkey using pynput for emergency stops
        try:
            keys = keyboard.HotKey.parse(self.config.emergency_stop_key_combo)
        except ValueError as e:
            emergency_stop_key_combo_default = Config().emergency_stop_key_combo
            logging.error(f'Invalid emergency stop key combo "{self.config.emergency_stop_key_combo}" ({e}); '
                          f'using default "{emergency_stop_key_combo_default}".')
            keys = keyboard.HotKey.parse(emergency_stop_key_combo_default)
        self.pynput_hotkey = keyboard.HotKey(
            keys=keys,
            on_activate=self.pynput_on_activate)
        self.pynput_listener = keyboard.Listener(
            on_press=self.pynput_for_canonical(self.pynput_hotkey.press),
            on_release=self.pynput_for_canonical(self.pynput_hotkey.release))
        self.pynput_listener.start()

    def pynput_for_canonical(self, f):
        return lambda k: f(self.pynput_listener.canonical(k))

    def pynput_on_activate(self) -> None:
        logging.info("Global hotkey for emergency stop activated")
        self.stop_request = True

    def check_stop_request(self) -> None:
        if self.stop_request:
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller_thread is not None:
            self.stop_request = True
            self.slot_control_stop_button()
            event.ignore()
            return
        self.pynput_listener.stop()
        event.accept()

    def get_settings_response(self, hero: Hero2, trigger: Trigger) -> Response:
        key = f"{hero.name}/{trigger.name}/response"
        response = default_response(hero, trigger)
        try:
            value = self.settings.value(key, type=str)
            if value:
                logging.info(f"Setting load: {key}={value}")
                response = Response.from_str(value)
        except Exception as e:
            logging.error("Failed to load setting; using default.", exc_info=e)
        return response

    def get_settings_enabled(self, hero: Hero2, trigger: Trigger) -> bool:
        key = f"{hero.name}/{trigger.name}/enabled"
        enabled = True
        try:
            value = self.settings.value(key, defaultValue=enabled, type=bool)
            logging.info(f"Setting load: {key}={value}")
            enabled = bool(value)
        except Exception as e:
            logging.error("Failed to load setting; using default.", exc_info=e)
        return enabled

    def get_settings_config(self) -> Config:
        default_config = Config()
        new_values = {}
        for name, default_value in default_config._asdict().items():
            key = f"config/{name}"
            value = self.settings.value(key, default_value, type=type(default_value))
            logging.info(f"Setting load: {key}={value}")
            new_values[name] = value
        return Config(**new_values)

    def get_settings_playing_hero(self) -> int:
        key = "playing_hero"
        value = 0
        try:
            value = self.settings.value(key, defaultValue=value, type=int)
            logging.info(f"Setting load: {key}={value}")
            value = int(value)
        except Exception as e:
            logging.error("Failed to load setting; using default.", exc_info=e)
        return value

    def set_settings_response(self, hero: Hero2, trigger: Trigger, response: Response) -> None:
        key = f"{hero.name}/{trigger.name}/response"
        value = str(response)
        logging.info(f"Setting update: {key}={value}")
        self.settings.setValue(key, value)

    def set_settings_enabled(self, hero: Hero2, trigger: Trigger, value: bool) -> None:
        key = f"{hero.name}/{trigger.name}/enabled"
        logging.info(f"Setting update: {key}={value}")
        self.settings.setValue(key, value)

    def set_settings_config(self, config: Config) -> None:
        for name, value in config._asdict().items():
            key = f"config/{name}"
            logging.info(f"Setting update: {key}={value}")
            self.settings.setValue(key, value)

    def set_settings_playing_hero(self, value: int) -> None:
        key = "playing_hero"
        logging.info(f"Setting update: {key}={value}")
        self.settings.setValue(key, value)

    def slot_trigger_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 1:
            return
        # Save response in settings
        hero = item.data(0, Qt.UserRole + self.DATA_HERO)
        trigger = item.data(0, Qt.UserRole + self.DATA_TRIGGER)
        response = item.data(1, Qt.UserRole)
        if hero is None or trigger is None or response is None:
            return
        self.set_settings_response(hero, trigger, response)
        # Save enabled in settings
        enabled = item.checkState(1) != Qt.Unchecked
        self.set_settings_enabled(hero, trigger, enabled)
        # Update controller
        self.update_controller()

    def slot_trigger_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        # Get initial response
        hero = item.data(0, Qt.UserRole + self.DATA_HERO)
        trigger = item.data(0, Qt.UserRole + self.DATA_TRIGGER)
        response = item.data(1, Qt.UserRole)
        if hero is None or trigger is None or response is None:
            return
        # Open response edit dialog
        conditional = is_conditional(trigger)
        dialog = ResponseDialog(self, hero, trigger, response, conditional)
        # Save updated response
        if dialog.exec() == QDialog.Accepted:
            try:
                updated_response = dialog.get_response()
            except Exception as e:
                self.slot_crash_dialog("Invalid input.", e)
            else:
                item.setData(1, Qt.UserRole, updated_response)
        # Update trigger table
        self.update_trigger_table()

    def slot_control_start_button(self) -> None:
        if self.controller_thread is not None:
            return
        try:
            self.controller_thread = ControllerThread(self.config, self.path_assets)
        except Exception as e:
            self.slot_crash_dialog("Failed to start the controller thread.", e)
            return
        self.action_start.setEnabled(False)
        self.action_stop.setEnabled(True)
        self.controller_thread.signal_crash.connect(self.slot_crash_dialog)
        self.controller_thread.signal_update_info.connect(self.update_controller_info)
        self.controller_thread.finished.connect(self.slot_controller_finished)
        self.controller_thread.start()
        # Apply current user settings
        self.update_controller()

    def slot_controller_finished(self) -> None:
        if self.controller_thread is None:
            return
        self.action_start.setEnabled(True)
        self.action_stop.setEnabled(False)
        self.controller_thread.quit()
        self.controller_thread.wait()
        self.controller_thread = None
        self.update_controller_info()

    def slot_control_stop_button(self) -> None:
        if self.controller_thread is None:
            return
        self.action_stop.setEnabled(False)
        self.controller_thread.stop()

    def update_controller(self) -> None:
        # Remember current choice
        index = self.hero_select_combo.currentIndex()
        self.set_settings_playing_hero(index)
        # Only update the controller if it is running
        if self.controller_thread is None:
            return
        # Get hero and auto-detect
        # if index <= 0:
        #     hero_auto_detect = True
        #     hero = Hero2.OTHER
        # else:
        #     hero_auto_detect = False
        #     hero = Hero2(index)
        hero_auto_detect = False
        hero = Hero2(index + 1)
        # Get trigger config
        responses = collections.defaultdict(dict)
        for index in range(self.trigger_tree.topLevelItemCount()):
            item = self.trigger_tree.topLevelItem(index)
            hero_ = item.data(0, Qt.UserRole + self.DATA_HERO)
            for index_ in range(item.childCount()):
                child = item.child(index_)
                if child.checkState(1) != Qt.Unchecked:
                    trigger = child.data(0, Qt.UserRole + self.DATA_TRIGGER)
                    response = child.data(1, Qt.UserRole)
                    responses[hero_][trigger] = response
        # Update controller
        self.controller_thread.controller.update_user_settings(
            hero_auto_detect=hero_auto_detect,
            hero=hero,
            responses=responses)

    def update_controller_info(self, controller_info: ControllerInfo | None = None) -> None:
        # Get status texts
        if controller_info is not None:
            program_status = "Started"
            hero_changed = controller_info.current_hero is not self.current_hero
            self.current_hero = controller_info.current_hero
        else:
            controller_info = ControllerInfo()
            program_status = "Not started"
            hero_changed = False
            self.current_hero = None
        # Update status bar
        self.vibe_intensity_bar.setValue(round(controller_info.vibe_intensity * 1000))
        self.status_program.setText(program_status)
        self.status_devices.setText(f"{controller_info.devices_connected:d} Devices")
        self.status_fps.setText(f"{controller_info.fps:d} FPS")
        self.status_calculation_time.setText(f"{controller_info.calculation_time * 1000:.0f} ms")
        # Update trigger tree
        for index in range(self.trigger_tree.topLevelItemCount()):
            item = self.trigger_tree.topLevelItem(index)
            hero = item.data(0, Qt.UserRole + self.DATA_HERO)
            # Update active hero
            if hero is self.current_hero:
                item.setForeground(0, self.color_highlight)
                if hero_changed:
                    self.trigger_tree.expandItem(item)
                    self.trigger_tree.scrollToItem(item, QAbstractItemView.PositionAtTop)
            else:
                item.setForeground(0, self.color_default)
            # Update active triggers
            for index_ in range(item.childCount()):
                child = item.child(index_)
                if hero is self.current_hero:
                    trigger = child.data(0, Qt.UserRole + self.DATA_TRIGGER)
                    intensities = controller_info.all_intensities.get(trigger, [])
                else:
                    intensities = []
                if intensities:
                    child.setForeground(0, self.color_highlight)
                    if len(intensities) == 1:
                        intensities_str = f"{sum(intensities) * 100:+.0f}%"
                    else:
                        intensities_str = f"{sum(intensities) * 100:+.0f}% ({len(intensities)}x)"
                else:
                    child.setForeground(0, self.color_default)
                    intensities_str = ""
                child.setText(3, intensities_str)

    def update_trigger_table(self) -> None:
        self.trigger_tree.blockSignals(True)
        for index in range(self.trigger_tree.topLevelItemCount()):
            item = self.trigger_tree.topLevelItem(index)
            for index_ in range(item.childCount()):
                child = item.child(index_)
                trigger = child.data(0, Qt.UserRole + self.DATA_TRIGGER)
                response = child.data(1, Qt.UserRole)
                conditional = is_conditional(trigger)
                child.setText(1, response.vibe_str)
                child.setText(2, "" if conditional else response.duration_str)
        self.trigger_tree.blockSignals(False)

    def slot_about_dialog(self) -> None:
        about_dialog = AboutDialog(self, self.version, self.path_assets)
        about_dialog.exec()

    def slot_settings_dialog(self) -> None:
        # Open the settings dialog
        dialog = ConfigDialog(self, self.config)
        # Save updated settings
        if dialog.exec() == QDialog.Accepted:
            try:
                self.config = dialog.get_config()
            except Exception as e:
                self.slot_crash_dialog("Invalid input.", e)
            else:
                self.set_settings_config(self.config)

    def slot_reset_button(self) -> None:
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Reset")
        message_box.setText("Are you sure you want to reset the vibration customization for all triggers, "
                            "as well as all settings, to the default values?\n"
                            "If you press Yes, you have to restart OverStim.")
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        message_box.setDefaultButton(QMessageBox.Cancel)
        result = message_box.exec()
        if result == QMessageBox.Yes:
            logging.info("All settings will be deleted.")
            self.settings.clear()
            self.close()

    def slot_crash_dialog(self, message: str, exception: BaseException) -> None:
        logging.error(message, exc_info=exception)
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Critical)
        message_box.setWindowTitle(type(exception).__name__)
        message_box.setText(f"{message}\n\n{exception}")
        message_box.exec()


class ControllerThread(QThread):
    signal_crash = Signal(str, BaseException)
    signal_update_info = Signal(ControllerInfo)

    def __init__(self, config: Config, path_assets: str) -> None:
        super().__init__()
        self.controller = Controller(config, path_assets, self.signal_update_info.emit)

    def stop(self) -> None:
        logging.info("Waiting for OverStim to stop ...")
        self.controller.stop_request = True

    def run(self) -> None:
        logging.info("OverStim is started.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.controller.run())
        except Exception as e:
            self.signal_crash.emit("OverStim stopped with an error.", e)
        finally:
            loop.close()
        logging.info("OverStim is stopped.")


class ResponseDialog(QDialog):
    def __init__(self, parent: QWidget, hero: Hero2, trigger: Trigger, response: Response, conditional: bool) -> None:
        super().__init__(parent)
        self.conditional = conditional
        self.setWindowTitle(f"{format_enum(hero)} / {format_enum(trigger)}")

        # Create widgets
        self.type_combo = QComboBox()
        self.type_combo.addItems([format_enum(response_type) for response_type in ResponseType])
        self.type_combo.setCurrentIndex(response.type.value - 1)
        self.type_combo.currentIndexChanged.connect(self.hide_ui)
        self.intensity_spin = QSpinBox()
        self.intensity_spin.setRange(0, 100)
        self.intensity_spin.setSingleStep(5)
        self.intensity_spin.setSuffix("%")
        self.intensity_spin.setValue(int(response.intensity * 100))
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.0, 60.0)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSingleStep(1.0)
        self.duration_spin.setSuffix("s")
        self.duration_spin.setValue(response.duration)
        self.pattern_edit = QLineEdit(str(response.pattern))
        self.pattern_edit.setToolTip("List of intensity and duration pairs.\n"
                                     "Example: 20% 2.5s, 65% 1s, 5% 4s\n"
                                     "Equivalent: 20 2.5, 65 1, 5 4")
        self.pattern_loop_spin = QSpinBox()
        self.pattern_loop_spin.setRange(1, 1000)
        self.pattern_loop_spin.setValue(response.pattern_loop)
        self.pattern_loop_spin.setToolTip("How often the pattern is repeated.")

        # Form layout
        self.form_layout = QFormLayout()
        self.form_layout.addRow(QLabel("Type:"), self.type_combo)
        self.form_layout.addRow(QLabel("Intensity:"), self.intensity_spin)
        self.form_layout.addRow(QLabel("Duration:"), self.duration_spin)
        self.form_layout.addRow(QLabel("Pattern:"), self.pattern_edit)
        self.form_layout.addRow(QLabel("Loop count:"), self.pattern_loop_spin)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Set the main layout
        layout = QVBoxLayout()
        layout.addLayout(self.form_layout)
        layout.addWidget(button_box)
        self.setLayout(layout)

        # Initiate UI hiding state
        self.hide_ui(self.type_combo.currentIndex())

    def hide_ui(self, type_index: int) -> None:
        response_type = ResponseType(type_index + 1)
        self.form_layout.setRowVisible(
            self.intensity_spin, response_type is ResponseType.CONSTANT)
        self.form_layout.setRowVisible(
            self.duration_spin, response_type in [ResponseType.CONSTANT, ResponseType.SILENCE] and not self.conditional)
        self.form_layout.setRowVisible(
            self.pattern_edit, response_type is ResponseType.PATTERN)
        self.form_layout.setRowVisible(
            self.pattern_loop_spin, response_type is ResponseType.PATTERN and not self.conditional)
        self.adjustSize()
        self.adjustPosition(self.parentWidget())

    def get_response(self) -> Response:
        response = Response(type=ResponseType(self.type_combo.currentIndex() + 1),
                            intensity=float(self.intensity_spin.value()) / 100.0,
                            duration=self.duration_spin.value(),
                            pattern=Pattern.from_str(self.pattern_edit.text()),
                            pattern_loop=self.pattern_loop_spin.value())
        response.validate()
        return response


class ConfigDialog(QDialog):
    def __init__(self, parent: QWidget, config: Config) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        # Create a form layout for the settings
        form_layout = QFormLayout()

        # MAX_VIBE_INTENSITY
        self.max_vibe_intensity = QSpinBox()
        self.max_vibe_intensity.setRange(0, 100)
        self.max_vibe_intensity.setSingleStep(5)
        self.max_vibe_intensity.setSuffix("%")
        self.max_vibe_intensity.setValue(int(config.max_vibe_intensity * 100))
        self.max_vibe_intensity.setToolTip(
            "Allows you to limit the maximum vibration intensity. Cannot be less than 0 or greater than 1.")
        form_layout.addRow(QLabel("Max Vibe Intensity:"), self.max_vibe_intensity)

        # EMERGENCY_STOP_KEY_COMBO
        self.emergency_stop_key_combo = QLineEdit(config.emergency_stop_key_combo)
        self.emergency_stop_key_combo.setToolTip(
            'Defines the key combination to trigger an emergency stop for the vibration and the application. Empty the '
            'field to restore the default of "<ctrl>+<shift>+<cmd>". Key combination strings are sequences of key '
            'identifiers separated by "+". Key identifiers are either single characters representing a keyboard key, '
            'such as "a", or special key names identified by names enclosed by brackets, such as "<ctrl>". This must '
            'not contain any spaces. The special key names are listed at '
            '<https://pynput.readthedocs.io/en/latest/keyboard.html#pynput.keyboard.Key>.')
        form_layout.addRow(QLabel("Emergency Stop Key Combo:"), self.emergency_stop_key_combo)

        # SCALE_ALL_INTENSITIES_BY_MAX_INTENSITY
        self.scale_all_intensities = QCheckBox()
        self.scale_all_intensities.setChecked(config.scale_all_intensities_by_max_intensity)
        self.scale_all_intensities.setToolTip(
            "Multiplies all intensities by MAX_VIBE_INTENSITY e.g. if MAX_VIBE_INTENSITY is 0.5 then all vibration "
            "triggers will be half as intense. Recommended True. When false, intensity is capped by MAX_INTENSITY but "
            "not scaled by it. May cause added intensities to vary by one vibration step due to rounding, depending on "
            "how many vibration steps your device supports.")
        form_layout.addRow(QLabel("Scale All Intensities by Max Intensity:"), self.scale_all_intensities)

        # CONTINUOUS_SCANNING
        self.continuous_scanning = QCheckBox()
        self.continuous_scanning.setChecked(config.continuous_scanning)
        self.continuous_scanning.setToolTip("Keep scanning for new devices until program closes.")
        form_layout.addRow(QLabel("Continuous Scanning:"), self.continuous_scanning)

        # EXCLUDED_DEVICE_NAMES
        self.excluded_device_names = QLineEdit("; ".join(config.excluded_device_names))
        self.excluded_device_names.setToolTip(
            "Exclude devices from having their vibration controlled. Separate entries with a semicolon (;).")
        form_layout.addRow(QLabel("Excluded Device Names:"), self.excluded_device_names)

        # USING_INTIFACE
        self.using_intiface = QCheckBox()
        self.using_intiface.setChecked(config.using_intiface)
        self.using_intiface.setToolTip("Disable if you want to test without Intiface.")
        form_layout.addRow(QLabel("Using Intiface:"), self.using_intiface)

        # WEBSOCKET_ADDRESS
        self.websocket_address = QLineEdit(config.websocket_address)
        self.websocket_address.setToolTip("Must match whatever is set in Intiface.")
        form_layout.addRow(QLabel("WebSocket Address:"), self.websocket_address)

        # GPU_ID
        self.gpu_id = QSpinBox()
        self.gpu_id.setRange(0, 10)
        self.gpu_id.setValue(config.gpu_id)
        self.gpu_id.setToolTip("Select the GPU that Overwatch is running on, starting count at 0.")
        form_layout.addRow(QLabel("GPU ID:"), self.gpu_id)

        # MONITOR_ID
        self.monitor_id = QSpinBox()
        self.monitor_id.setRange(0, 10)
        self.monitor_id.setValue(config.monitor_id)
        self.monitor_id.setToolTip("Select the Monitor that Overwatch is running on, starting count at 0.")
        form_layout.addRow(QLabel("Monitor ID:"), self.monitor_id)

        # MAX_REFRESH_RATE
        self.max_refresh_rate = QSpinBox()
        self.max_refresh_rate.setRange(1, 160)
        self.max_refresh_rate.setValue(config.max_refresh_rate)
        self.max_refresh_rate.setToolTip(
            "How many times per second OverStim should check the screen. Higher values require a larger "
            "BEAM_DISCONNECT_BUFFER, to prevent minor issues with Mercy's beam detection.")
        form_layout.addRow(QLabel("Max Refresh Rate:"), self.max_refresh_rate)

        # DEAD_REFRESH_RATE
        self.dead_refresh_rate = QSpinBox()
        self.dead_refresh_rate.setRange(1, 160)
        self.dead_refresh_rate.setValue(config.dead_refresh_rate)
        self.dead_refresh_rate.setToolTip(
            "How many times per second OverStim should check the screen when the player is dead.")
        form_layout.addRow(QLabel("Dead Refresh Rate:"), self.dead_refresh_rate)

        # LUCIO_CROSSFADE_BUFFER
        self.lucio_crossfade_buffer = QSpinBox()
        self.lucio_crossfade_buffer.setRange(0, 100)
        self.lucio_crossfade_buffer.setValue(config.lucio_crossfade_buffer)
        self.lucio_crossfade_buffer.setToolTip(
            "Prevents pause in vibration while switching song. See comment on MERCY_BEAM_DISCONNECT_BUFFER. Unsure if "
            "latency affects this one.")
        form_layout.addRow(QLabel("Lucio Crossfade Buffer:"), self.lucio_crossfade_buffer)

        # MERCY_BEAM_DISCONNECT_BUFFER
        self.mercy_beam_disconnect_buffer = QSpinBox()
        self.mercy_beam_disconnect_buffer.setRange(0, 100)
        self.mercy_beam_disconnect_buffer.setValue(config.mercy_beam_disconnect_buffer)
        self.mercy_beam_disconnect_buffer.setToolTip(
            "#Amount of confirmations needed to confirm that Mercy's beam has truly disconnected. Affected by in-game "
            "latency and MAX_REFRESH_RATE. Higher in-game latency requires a larger buffer. 9 seemed to work for me on "
            "around 40ms latency, YMMV.")
        form_layout.addRow(QLabel("Mercy Beam Disconnect Buffer:"), self.mercy_beam_disconnect_buffer)

        # ZEN_ORB_DISCONNECT_BUFFER
        self.zen_orb_disconnect_buffer = QSpinBox()
        self.zen_orb_disconnect_buffer.setRange(0, 100)
        self.zen_orb_disconnect_buffer.setValue(config.zen_orb_disconnect_buffer)
        self.zen_orb_disconnect_buffer.setToolTip(
            "Prevents pause in vibration while switching orb target. See comment on MERCY_BEAM_DISCONNECT_BUFFER. "
            "Unsure if latency affects this one, but distance from target does.")
        form_layout.addRow(QLabel("Zen Orb Disconnect Buffer:"), self.zen_orb_disconnect_buffer)

        # Preview window
        self.preview_window = QCheckBox()
        self.preview_window.setChecked(config.preview_window)
        self.preview_window.setToolTip(
            "Show a preview window of the screen visible to OverStim at 1/4 of the size. This is only for testing "
            "purposes and might increase the CPU load a little.")
        form_layout.addRow(QLabel("Preview window:"), self.preview_window)

        # Add OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Set the main layout
        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def get_config(self) -> Config:
        # Restore default emergency stop key combo
        emergency_stop_key_combo = self.emergency_stop_key_combo.text().strip()
        if not emergency_stop_key_combo:
            emergency_stop_key_combo = Config().emergency_stop_key_combo
        # Validate hotkey string
        keyboard.HotKey.parse(emergency_stop_key_combo)
        # Create config object
        return Config(
            max_vibe_intensity=self.max_vibe_intensity.value() / 100.0,
            emergency_stop_key_combo=emergency_stop_key_combo,
            scale_all_intensities_by_max_intensity=self.scale_all_intensities.isChecked(),
            continuous_scanning=self.continuous_scanning.isChecked(),
            excluded_device_names=[name.strip() for name in self.excluded_device_names.text().split(';')],
            using_intiface=self.using_intiface.isChecked(),
            websocket_address=self.websocket_address.text(),
            gpu_id=self.gpu_id.value(),
            monitor_id=self.monitor_id.value(),
            max_refresh_rate=self.max_refresh_rate.value(),
            dead_refresh_rate=self.dead_refresh_rate.value(),
            lucio_crossfade_buffer=self.lucio_crossfade_buffer.value(),
            mercy_beam_disconnect_buffer=self.mercy_beam_disconnect_buffer.value(),
            zen_orb_disconnect_buffer=self.zen_orb_disconnect_buffer.value(),
            preview_window=self.preview_window.isChecked())


class AboutDialog(QDialog):
    PROGRAM_TEXT = """
        <p><b>OverStim {}</b><br>
        Controls sex toys based on the game Overwatch 2</p>

        <p>Copyright © 2023-2025 cryo-es<br>
        Copyright © 2024-2025 Pharmercy69</p>

        <p>To find usage instructions, contact info, and the source code, visit the homepage at
        <a href="https://codeberg.org/pharmercy/OverStim">https://codeberg.org/pharmercy/OverStim</a>.</p>

        <p>For update announcements and technical support, join the Discord server at
        <a href="https://discord.gg/J8eS2BtbDk">https://discord.gg/J8eS2BtbDk</a>.</p>

        <p>Have fun &hearts;</p>
        """
    LICENSE_TEXT = """
        <p>This program is free software: you can redistribute it and/or modify
        it under the terms of the GNU Affero General Public License as
        published by the Free Software Foundation, either version 3 of the
        License, or (at your option) any later version.</p>

        <p>This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU Affero General Public License for more details.</p>

        <p>You should have received a copy of the GNU Affero General Public License
        along with this program.  If not, see 
        <a href="https://www.gnu.org/licenses/">https://www.gnu.org/licenses/</a>.</p>
        """

    def __init__(self, parent: QWidget, version: str, path_assets: str) -> None:
        super().__init__(parent)
        path_icon = os.path.join(path_assets, "icon.ico")
        path_icon_license = os.path.join(path_assets, "agplv3-with-text-162x68.png")

        # Icon
        icon_pixmap = QPixmap(path_icon)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setPixmap(icon_pixmap)

        # Program Name and Version
        program_label = QLabel(self.PROGRAM_TEXT.format(version))
        program_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        program_label.setWordWrap(True)
        program_label.setOpenExternalLinks(True)

        # License icon
        license_icon_pixmap = QPixmap(path_icon_license)
        license_icon_label = QLabel()
        license_icon_label.setAlignment(Qt.AlignCenter)
        license_icon_label.setPixmap(license_icon_pixmap)

        # Copyright and License
        license_label = QLabel(self.LICENSE_TEXT)
        license_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        license_label.setWordWrap(True)
        license_label.setOpenExternalLinks(True)

        # Layout
        layout = QGridLayout()
        layout.addWidget(icon_label, 0, 0)
        layout.addWidget(program_label, 1, 0)
        layout.addWidget(license_icon_label, 0, 1)
        layout.addWidget(license_label, 1, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        self.setLayout(layout)

        # Dialog setup
        self.setFixedSize(self.sizeHint())
        self.setWindowTitle("About OverStim")
