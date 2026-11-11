#!/usr/bin/env python3
# license: GPL v3.0
# copyright (c) 2026 - siriusky (github)
# contact: https://github.com/siriusky/siril-synthetic-color-channel/issues
#
# version 0.1.0 first release
#
#

"""
Siril Synthetic Color Channel script
Creates a synthetic red, green, blue, or luminance channel from a color image.
Choose a target channel and a pixelmath formula.

Script steps:
1. Load image from Siril
2. Split RGB channels.
3. Apply pixelmath to the selected channel.
4. Save the synthetic channel.
5. For RGB images: recombine channels and load the result.
   For Luminance: load the synthetic luminance image directly.
Batch processing is available.
"""

import sirilpy as s
s.ensure_installed('PyQt6')

import sys
import os
import re
import numpy as np
import ast


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QGroupBox, QMessageBox,
    QListWidget, QFileDialog, QComboBox,
    QLineEdit
)

from PyQt6.QtCore import Qt, QEvent, QTimer

from PyQt6.QtGui import QIcon, QPixmap, QColor

VERSION = "0.1.0"

if not s.check_module_version(">=0.6.42"):
    print("Error: requires sirilpy module >= 0.6.42")
    sys.exit(1)

class SyntheticColorWindow(QMainWindow):
    CHANNEL_PRESETS = {
        "r": {"2G - B": "2*g - b"},
        "g": {"(R+B)/2": "(r + b) / 2"},
        "b": {"2G - R": "2*g - r"},
        "luminance": {"Rec.709": "0.2126*r + 0.7152*g + 0.0722*b"}
    }
    DEFAULT_PRESET = {
        "r": "2G - B",
        "g": "(R+B)/2",
        "b": "2G - R",
        "luminance": "Rec.709"
    }

    def __init__(self, siril_interface):
        super().__init__()
        self.siril = siril_interface
        self.setWindowTitle(f"Synthetic Color Channel v{VERSION}")
        self.resize(500, 580)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Dark theme
        self.apply_dark_theme()

        # Formula group
        formula_group = QGroupBox("Synthetic Channel Formula")
        formula_layout = QVBoxLayout(formula_group)

        # Target channel selection
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Target channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.addItem(self.create_color_icon("red"), "Red", "r")
        self.channel_combo.addItem(self.create_color_icon("green"), "Green", "g")
        self.channel_combo.addItem(self.create_color_icon("blue"), "Blue", "b")
        self.channel_combo.addItem(self.create_color_icon("white"), "Luminance", "luminance")
        self.channel_combo.setCurrentIndex(2)  # default Blue
        self.channel_combo.currentIndexChanged.connect(self.on_channel_changed)
        channel_layout.addWidget(self.channel_combo)
        formula_layout.addLayout(channel_layout)

        # Preset selection
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        formula_layout.addLayout(preset_layout)

        # Manual formula entry
        formula_edit_layout = QHBoxLayout()
        formula_edit_layout.addWidget(QLabel("Formula:"))
        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("e.g. 2g - r")
        self.formula_edit.setToolTip(
            "Allowed variables: r, g, b (case‑insensitive)\n"
            "Operators: + - * / **\n"
            "Functions: sin, cos, tan, asin, acos, atan,\n"
            "sinh, cosh, tanh, asinh, acosh, atanh,\n"
            "log, log10, log2, sqrt, abs, exp"
        )
        self.formula_edit.setText("")  # start blank, placeholder shows
        self.formula_edit.textEdited.connect(self.on_formula_edited)  # <-- add this
        formula_edit_layout.addWidget(self.formula_edit)
        formula_layout.addLayout(formula_edit_layout)

        # Buttons: Apply and Reset Formula
        buttons_layout = QHBoxLayout()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_synthetic_channel)
        buttons_layout.addWidget(self.apply_btn)

        self.reset_btn = QPushButton("Reset Formula")
        self.reset_btn.clicked.connect(self.reset_formula)
        buttons_layout.addWidget(self.reset_btn)

        formula_layout.addLayout(buttons_layout)

        main_layout.addWidget(formula_group)

        # Batch processing group (collapsible)
        self.batch_group = QGroupBox("Batch Processing")
        self.batch_group.setCheckable(True)

        # Create a content widget that can be hidden/shown
        self.batch_content = QWidget()
        batch_layout = QVBoxLayout(self.batch_content)
        batch_layout.setContentsMargins(0, 0, 0, 0)  # keep internal spacing contained

        # Warning label above the select button
        self.warning_label = QLabel("save unsaved changes before running batch")
        self.warning_label.setStyleSheet("color: #CC9900;")
        self.warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warning_label.setWordWrap(True)
        batch_layout.addWidget(self.warning_label)

        self.select_btn = QPushButton("Select Images")
        self.select_btn.setObjectName("selectImagesButton")
        self.select_btn.clicked.connect(self.select_images)
        batch_layout.addWidget(self.select_btn)

        self.batch_list_widget = QListWidget()
        self.batch_list_widget.setObjectName("batchListWidget")
        self.batch_list_widget.setMinimumHeight(40)
        batch_layout.addWidget(self.batch_list_widget)

        self.batch_count_label = QLabel("Selected images: 0")
        self.batch_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        batch_layout.addWidget(self.batch_count_label)

        # Output directory selection
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(QLabel("Output directory:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setReadOnly(True)
        self.output_dir_edit.setPlaceholderText("Auto (source folder)")
        self.output_dir_edit.setToolTip("Click to choose output directory")
        self.output_dir_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_dir_edit.installEventFilter(self)
        output_dir_layout.addWidget(self.output_dir_edit, stretch=1)
        batch_layout.addLayout(output_dir_layout)

        # Output format selection
        output_format_layout = QHBoxLayout()
        output_format_layout.addWidget(QLabel("Output format:"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItem("TIFF (16-bit)", "tiff")
        self.output_format_combo.addItem("JPEG", "jpg")
        self.output_format_combo.addItem("PNG", "png")
        self.output_format_combo.addItem("BMP", "bmp")
        self.output_format_combo.addItem("PNM", "pnm")
        self.output_format_combo.addItem("TIFF (32-bit)", "tiff32")
        self.output_format_combo.addItem("TIFF (8-bit)", "tiff8")
        self.output_format_combo.addItem("FITS", "fits")
        output_format_layout.addWidget(self.output_format_combo)
        batch_layout.addLayout(output_format_layout)

        batch_buttons = QHBoxLayout()
        self.run_btn = QPushButton("Run Batch")
        self.run_btn.clicked.connect(self.run_batch)
        batch_buttons.addWidget(self.run_btn)

        self.clear_btn = QPushButton("Clear List")
        self.clear_btn.clicked.connect(self.clear_batch_list)
        batch_buttons.addWidget(self.clear_btn)

        batch_layout.addLayout(batch_buttons)

        # Place the content widget inside the group box
        group_layout = QVBoxLayout(self.batch_group)
        group_layout.addWidget(self.batch_content)

        main_layout.addWidget(self.batch_group)

        # Set collapsed as the default state (before connecting the signal)
        self.batch_group.setChecked(False)
        self.batch_content.setVisible(False)

        # Connect checkbox toggle to a method that also resizes the window
        self.batch_group.toggled.connect(self.on_batch_toggled)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Internal state
        self.batch_files = []

        # Initialize presets and formula
        self.on_channel_changed(self.channel_combo.currentIndex())

        # Start with the collapsed height
        main_layout.activate()
        self.resize(500, self.minimumSizeHint().height())

    def _raw_to_rgb(self, raw):
        """Convert raw Siril image data to normalized HxWxC float RGB.

        Integer data is scaled based on its actual maximum value:
          - max ≤ 255      → assume 8-bit  → divide by 255
          - max ≤ 65535    → assume 16-bit → divide by 65535
          - otherwise      → divide by dtype max
        Float data is assumed to be normalized [0,1] unless its max > 1,
        in which case it is scaled down by the same logic.
        """
        if np.issubdtype(raw.dtype, np.integer):
            max_val = float(raw.max())
            if max_val <= 255.0:
                scale = 255.0
            elif max_val <= 65535.0:
                scale = 65535.0
            else:
                scale = float(np.iinfo(raw.dtype).max)
            img = raw.astype(np.float32) / scale
        else:
            img = raw.astype(np.float32)
            max_val = float(img.max())
            if max_val > 1.0:
                if max_val <= 255.0:
                    img = img / 255.0
                elif max_val <= 65535.0:
                    img = img / 65535.0
                else:
                    img = img / max_val

        img = np.clip(img, 0.0, 1.0)

        if img.ndim == 2:
            return np.repeat(img[:, :, None], 3, axis=2), True
        if img.shape[0] == 1:
            return np.repeat(img[0, :, :, None], 3, axis=2), True
        if img.shape[0] == 3:
            return np.transpose(img, (1, 2, 0)), False
        return img, False

    def _push_image(self, img, undo_message="Synthetic Color Channel"):
        """Push an HxW or HxWxC float image back to Siril."""
        out = np.clip(img, 0.0, 1.0).astype(np.float32)

        if out.ndim == 3:
            out = np.transpose(out, (2, 0, 1))

        with self.siril.image_lock():
            self.siril.undo_save_state(undo_message)
            self.siril.set_image_pixeldata(out)

#used by def _eval_ast_node
    _BIN_OPS = {
        ast.Add: np.add,
        ast.Sub: np.subtract,
        ast.Mult: np.multiply,
        ast.Div: np.divide,
        ast.Pow: np.power,
    }

    FUNCTIONS = {
        'sin': np.sin,
        'cos': np.cos,
        'tan': np.tan,
        'asin': np.arcsin,
        'acos': np.arccos,
        'atan': np.arctan,
        'sinh': np.sinh,
        'cosh': np.cosh,
        'tanh': np.tanh,
        'asinh': np.arcsinh,
        'acosh': np.arccosh,
        'atanh': np.arctanh,
        'log': np.log,
        'log10': np.log10,
        'log2': np.log2,
        'sqrt': np.sqrt,
        'abs': np.abs,
        'exp': np.exp,
    }

    def _eval_ast_node(self, node, env):
        """Recursively evaluate an AST node using only allowed operations."""
        if isinstance(node, ast.Expression):
            return self._eval_ast_node(node.body, env)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise ValueError(f"Unknown variable: {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in self._BIN_OPS:
            left = self._eval_ast_node(node.left, env)
            right = self._eval_ast_node(node.right, env)
            return self._BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in {ast.UAdd, ast.USub}:
            value = self._eval_ast_node(node.operand, env)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in self.FUNCTIONS:
                raise ValueError(f"Unsupported function: {getattr(node.func, 'id', '?')}")
            args = [self._eval_ast_node(arg, env) for arg in node.args]
            return self.FUNCTIONS[node.func.id](*args)

        raise ValueError("Unsupported formula element")

    def _evaluate_formula(self, formula, R, G, B):
        """Evaluate a formula string using NumPy arrays.

        The formula uses r, g, b as variables (case-insensitive).
        Implicit multiplication (e.g. 2g → 2*g) is inserted automatically.
        Only arithmetic operators +, -, *, /, ** and parentheses are allowed.
        """
        # Replace r/g/b that are not part of a longer identifier.
        formula_clean = re.sub(
            r'(?<![A-Za-z])(r|g|b)(?![A-Za-z])',
            lambda m: m.group(1).upper(),
            formula,
            flags=re.IGNORECASE
        )

        # Insert implicit multiplication:
        # 1) number followed by variable: 2R -> 2*R
        formula_clean = re.sub(r'(\d)([A-Z])', r'\1*\2', formula_clean)
        # 2) closing parenthesis followed by variable: )R -> )*R
        formula_clean = re.sub(r'(\))([A-Z])', r'\1*\2', formula_clean)
        # 3) variable followed by opening parenthesis: R( -> R*(
        formula_clean = re.sub(r'([A-Z])(\()', r'\1*\2', formula_clean)
        # 4) variable followed by variable: RG -> R*G (only single letters here)
        formula_clean = re.sub(r'([A-Z])([A-Z])', r'\1*\2', formula_clean)

        env = {'R': R, 'G': G, 'B': B}
        tree = ast.parse(formula_clean, mode='eval')
        return self._eval_ast_node(tree, env)
    def create_color_icon(self, color_name: str, size: int = 16) -> QIcon:
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(color_name))
        return QIcon(pixmap)

    def apply_dark_theme(self):
        """Apply a dark theme to the whole window."""
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QLabel { color: #ffffff; font-size: 13px; }
            QGroupBox {
                color: #ffffff; border: 1px solid #444444;
                border-radius: 5px; margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPushButton {
                background-color: #3c3c3c; color: #ffffff;
                border: none; padding: 8px 16px;
                font-size: 13px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #505050; }
            QPushButton:pressed { background-color: #252525; }
            QPushButton:disabled { background-color: #2b2b2b; color: #808080; }
            QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
                background-color: #3c3c3c; color: #ffffff;
                border: 1px solid #555555; border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c; color: #ffffff;
                selection-background-color: #505050;
                border: 1px solid #555555;
            }
            QListWidget {
                background-color: #3c3c3c; color: #ffffff;
                border: 1px solid #555555; border-radius: 3px;
            }
            QSlider::groove:horizontal {
                height: 6px; background: #555555; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #aaaaaa; width: 16px; height: 16px;
                margin: -5px 0; border-radius: 8px;
            }
            QSlider::handle:horizontal:hover { background: #cccccc; }

            #selectImagesButton {
                background-color: #4d4d4d;
            }
            #selectImagesButton:hover {
                background-color: #5a5a5a;
            }
            #batchListWidget {
                background-color: #4d4d4d;
            }
            #statusLabel {
                color: #00ff00;
            }

            /* Ensure QMessageBox text is readable (black on white) */
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: #000000;
            }
        """)

    def on_channel_changed(self, index):
        """Handle target channel change: update presets and formula."""
        self.update_presets()

    def update_presets(self):
        """Update preset combo box based on selected target channel."""
        channel = self.channel_combo.currentData()
        channel_presets = self.CHANNEL_PRESETS.get(channel, {})
        default_name = self.DEFAULT_PRESET.get(channel)

        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Custom", "")

        for name, formula in channel_presets.items():
            self.preset_combo.addItem(name, formula)

        # Select default preset if defined, otherwise Custom
        idx = self.preset_combo.findText(default_name) if default_name else 0
        self.preset_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.preset_combo.blockSignals(False)

        # Update formula field according to the selected preset
        self.on_preset_changed(self.preset_combo.currentIndex())

    def on_preset_changed(self, index):
        """Set formula from selected preset.
        If index 0 (Custom), the formula field is blanked, leaving only the placeholder text.
        """
        if index > 0:
            formula = self.preset_combo.currentData()
            if formula:
                self.formula_edit.setText(formula)
        else:
            self.formula_edit.clear()  # blank, placeholder will show

    def on_formula_edited(self, text):
        """Switch the preset to Custom when the user manually edits the formula."""
        if self.preset_combo.currentIndex() != 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(0)
            self.preset_combo.blockSignals(False)

    def reset_formula(self):
        """Reset formula to the default for the current channel."""
        channel = self.channel_combo.currentData()
        preset_name = self.DEFAULT_PRESET.get(channel)

        if preset_name:
            idx = self.preset_combo.findText(preset_name)
        else:
            idx = 0  # Custom

        if idx < 0:
            idx = 0

        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.blockSignals(False)
        self.on_preset_changed(idx)

    def browse_output_dir(self):
        """Open directory chooser and set the output directory field."""
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_dir_edit.setText(directory)

    def on_batch_toggled(self, checked):
        """Show/hide batch content and adjust window size immediately."""
        self.batch_content.setVisible(checked)

        self.batch_expanded = checked

        # Recalculate the group box layout and the real content layout
        self.batch_group.layout().invalidate()
        self.batch_group.layout().activate()
        self.centralWidget().layout().invalidate()
        self.centralWidget().layout().activate()

        # Defer the resize until Qt has processed pending layout requests
        QTimer.singleShot(0, self._resize_window)

    def _resize_window(self):
        """Resize the window to fit its current content while keeping width."""
        self.centralWidget().layout().activate()

        if getattr(self, 'batch_expanded', False):
            # Expanding: use the preferred size, which gives more room
            target_height = self.sizeHint().height()
        else:
            # Collapsing: shrink to the minimal height
            target_height = self.minimumSizeHint().height()

        self.resize(self.width(), target_height)

    def eventFilter(self, obj, event):
        """Handle mouse clicks on the output directory field to open the picker."""
        if obj == self.output_dir_edit and event.type() == QEvent.Type.MouseButtonPress:
            self.browse_output_dir()
            return True  # consume the event
        return super().eventFilter(obj, event)

    def apply_synthetic_channel(self):
        """Apply the synthetic channel process to the currently loaded image."""
        formula = self.formula_edit.text().strip()
        if not formula:
            QMessageBox.warning(self, "Invalid Formula", "Please enter a synthetic channel formula.")
            return

        if self._process_loaded_image(show_errors=True):
            channel_name = self.channel_combo.currentText()
            self.status_label.setText(f"Synthetic {channel_name} channel applied successfully")

    def _process_loaded_image(self, show_errors=True):
        """
        Core processing using Python/NumPy only.

        1. Get the current image from Siril.
        2. Convert to normalized RGB (or mono).
        3. Evaluate the formula on the appropriate channel(s).
        4. Replace the selected channel, or create a luminance image.
        5. Push the result back to Siril.
        """
        formula = self.formula_edit.text().strip()
        target = self.channel_combo.currentData()

        if not formula:
            if show_errors:
                QMessageBox.warning(self, "Invalid Formula", "Please enter a synthetic channel formula.")
            else:
                self.siril.log("Synthetic channel formula is empty.")
            return False

        try:
            fit = self.siril.get_image()
            raw = fit.data
            img_rgb, was_mono = self._raw_to_rgb(raw)

            if was_mono and target != "luminance":
                raise ValueError("Channel replacement requires an RGB image.")

            R = img_rgb[:, :, 0]
            G = img_rgb[:, :, 1]
            B = img_rgb[:, :, 2]

            synth = np.clip(self._evaluate_formula(formula, R, G, B), 0.0, 1.0)

            if target == "luminance":
                out_img = synth
                out_is_mono = True
            else:
                out_img = img_rgb.copy()
                channel_index = {"r": 0, "g": 1, "b": 2}[target]
                out_img[:, :, channel_index] = synth
                out_is_mono = False

            self._push_image(out_img, "Synthetic Color Channel")
            return True

        except Exception as e:
            msg = f"Synthetic channel processing failed: {e}"
            if show_errors:
                QMessageBox.critical(self, "Error", msg)
            else:
                self.siril.log(msg)
            return False

    def select_images(self):
        """Open file dialog to select images and add them to the batch list."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.fit *.fits *.tif *.tiff *.png *.jpg *.jpeg)"
        )
        if file_paths and not self.output_dir_edit.text().strip():
            first_dir = os.path.dirname(file_paths[0])
            self.output_dir_edit.setText(first_dir)

        for fp in file_paths:
            if fp not in self.batch_files:
                self.batch_files.append(fp)
                self.batch_list_widget.addItem(fp)
        self.batch_count_label.setText(f"Selected images: {len(self.batch_files)}")

    def clear_batch_list(self):
        """Clear the batch processing list."""
        self.batch_files.clear()
        self.batch_list_widget.clear()
        self.batch_count_label.setText("Selected images: 0")

    def get_save_config(self):
        fmt = self.output_format_combo.currentData()
        configs = {
            "tiff":    ("savetif", "-astro"),
            "jpg":     ("savejpg", "100"),
            "png":     ("savepng", ""),
            "bmp":     ("savebmp", ""),
            "pnm":     ("savepnm", ""),
            "tiff32":  ("savetif32", ""),
            "tiff8":   ("savetif8", ""),
            "fits":    ("save", ""),
        }
        return configs.get(fmt, ("savetif", "-astro"))

    def run_batch(self):
        """Process all images in the batch list using current settings."""
        if not self.batch_files:
            QMessageBox.information(self, "Batch Processing", "No images selected.")
            return

        save_func, extra_args = self.get_save_config()
        chosen_output_dir = self.output_dir_edit.text().strip()

        for file_path in self.batch_files:
            self.status_label.setText(f"Processing: {os.path.basename(file_path)}")
            self.siril.log(f"Batch loading: {file_path}")

            load_cmd = f'load "{file_path}"'
            if not self._run_cmd(load_cmd):
                self.siril.log(f"Failed to load {file_path}, skipping.")
                continue

            if not self._process_loaded_image(show_errors=False):
                self.siril.log(f"Synthetic channel processing failed for {file_path}, skipping.")
                continue

            if chosen_output_dir:
                output_dir = chosen_output_dir
            else:
                output_dir = os.path.dirname(file_path)

            os.makedirs(output_dir, exist_ok=True)

            stem, _ = os.path.splitext(os.path.basename(file_path))
            output_stem = f"{stem}_synth"
            output_path = os.path.join(output_dir, output_stem)

            if extra_args:
                save_cmd = f'{save_func} "{output_path}" {extra_args}'
            else:
                save_cmd = f'{save_func} "{output_path}"'

            if not self._run_cmd(save_cmd):
                self.siril.log(f"Save failed for {output_path}.")
                continue

            self.siril.log(f"Processed and saved: {output_path} (extension added by Siril)")

        self.status_label.setText("Batch processing completed.")


    def _run_cmd(self, command_str):
        """Run a Siril command.

        sirilpy's cmd() returns None on success and raises on failure
        (older versions returned True), so only an exception or an
        explicit False counts as failure.
        """
        try:
            result = self.siril.cmd(command_str)
        except Exception as e:
            self.siril.log(f"Command error: {e}  ({command_str})")
            return False
        if result is False:
            self.siril.log(f"Command returned False: {command_str}")
            return False
        return True


def main():
    app = QApplication(sys.argv)
    siril = s.SirilInterface()
    try:
        siril.connect()
    except s.SirilConnectionError:
        QMessageBox.critical(None, "Error", "Failed to connect to Siril")
        sys.exit(1)

    window = SyntheticColorWindow(siril)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()