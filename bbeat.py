#!/usr/bin/env python3

# Binaural Beat Generator (macOS M4 Compatible)
# CLEAN: Pure binaural tones only — no noise, no distractions

import sys
import numpy as np
import sounddevice as sd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QDial, QPushButton, QGroupBox, QGridLayout)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QFont, QFontDatabase, QBrush
)
import math


MONO_FAMILY = "Courier"


def find_monospace_family():
    try:
        fixed = QFontDatabase.families(QFontDatabase.WritingSystem.Latin)
        preferred = ["Menlo", "Monaco", "SF Mono", "Courier New", "Courier"]
        for fam in preferred:
            if fam in fixed:
                return fam
    except:
        pass
    return "Courier"


class GlowDial(QDial):
    """Analog mixer-style knob – clean, flat, no glow."""

    def __init__(self, parent=None, line_color="#4CAF50", knob_color="#1E1E1E",
                 text_color="#C7F464", accent_color="#7AFF37"):
        super().__init__(parent)
        self.line_color = QColor(line_color)
        self.knob_color = QColor(knob_color)
        self.text_color = QColor(text_color)
        self.accent_color = QColor(accent_color)

        self.setNotchesVisible(False)
        self.setMinimumSize(70, 70)
        self.setWrapping(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            size = min(self.width(), self.height())
            center = self.rect().center()
            outer_radius = size / 2 - 4
            knob_radius = outer_radius * 0.65

            rect = QRectF(center.x() - outer_radius, center.y() - outer_radius,
                         outer_radius * 2, outer_radius * 2)
            knob_rect = QRectF(center.x() - knob_radius, center.y() - knob_radius,
                              knob_radius * 2, knob_radius * 2)

            # Knob position (270° sweep, starts at 135°)
            span_angle = 270
            start_angle = 135
            angle_range = self.maximum() - self.minimum()
            angle = 0
            if angle_range > 0:
                angle = (self.value() - self.minimum()) / angle_range * span_angle

            # === 1. BACKGROUND RING — FLAT ===
            painter.setBrush(QBrush(QColor("#1A1A1A")))
            painter.setPen(QPen(QColor("#3A3A3A"), 1))
            painter.drawEllipse(rect.adjusted(2, 2, -2, -2))

            painter.setPen(QPen(QColor("#C7F464"), 1.5))
            painter.drawEllipse(rect.adjusted(-1, -1, 1, 1))

            # === 2. SWEEP LINE — THIN, NO GLOW ===
            arc_rect = rect.adjusted(6, 6, -6, -6)
            line_pen = QPen(self.line_color, 3)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(line_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            start_arc = int((90 - (start_angle + angle)) * 16)
            span_arc = int(angle * 16)
            painter.drawArc(arc_rect, start_arc, span_arc)

            # === 3. TICK MARKS ===
            painter.setPen(QPen(self.accent_color, 2))
            tick_rect = rect.adjusted(8, 8, -8, -8)
            for i in range(5):
                tick_angle = start_angle + (i * span_angle / 4) - 90
                rad = math.radians(tick_angle)
                x1 = center.x() + tick_rect.width() / 2 * math.cos(rad)
                y1 = center.y() + tick_rect.height() / 2 * math.sin(rad)
                x2 = center.x() + (tick_rect.width() / 2 - 8) * math.cos(rad)
                y2 = center.y() + (tick_rect.height() / 2 - 8) * math.sin(rad)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            # === 4. MAIN KNOB — FLAT ===
            painter.setBrush(QBrush(QColor("#2A2A2A")))
            painter.setPen(QPen(QColor("#3A3A3A"), 1))
            painter.drawEllipse(knob_rect)

            painter.setPen(QPen(QColor("#C7F464"), 1.5))
            painter.drawArc(knob_rect.adjusted(1, 1, -2, -2), 0, 360 * 16)

            # === 5. INDICATOR LINE ===
            painter.setPen(QPen(QColor("#C7F464"), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            indicator_length = int(knob_radius * 0.55)

            painter.save()
            painter.translate(center)
            painter.rotate(start_angle + angle)
            painter.drawLine(0, 0, 0, -indicator_length)
            painter.restore()

            # === 6. CENTER DOT — SOLID ===
            painter.setBrush(QBrush(QColor("#7AFF37")))
            painter.setPen(QPen(QColor("#1E1E1E"), 1))
            painter.drawEllipse(center.x() - 3, center.y() - 3, 6, 6)

        finally:
            painter.end()


# === SUBCLASSES: ONLY FOR WHEEL CONTROL ===
class CarrierDial(GlowDial):
    def wheelEvent(self, event):
        steps_per_tick = 1  # +1 Hz per notch
        delta = event.angleDelta().y()
        if delta == 0: return
        steps = (delta // 120) * steps_per_tick or (1 if delta > 0 else -1)
        self.setValue(max(self.minimum(), min(self.maximum(), self.value() + steps)))
        event.accept()


class BeatDial(GlowDial):
    def wheelEvent(self, event):
        steps_per_tick = 1   # +0.1 Hz per notch (value is *10)
        delta = event.angleDelta().y()
        if delta == 0: return
        steps = (delta // 120) * steps_per_tick or (1 if delta > 0 else -1)
        self.setValue(max(self.minimum(), min(self.maximum(), self.value() + steps)))
        event.accept()


class Oscilloscope(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.buffer = np.zeros(1024, dtype=np.float32)
        self.grid_color = QColor(40, 40, 40)
        self.wave_color = QColor(122, 255, 55)
        self.bg_color = QColor(20, 20, 20)

    def update_buffer(self, new_buffer: np.ndarray):
        if new_buffer is None:
            return
        n = len(self.buffer)
        if len(new_buffer) != n:
            new = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(new_buffer)), new_buffer)
        else:
            new = new_buffer
        self.buffer = new.astype(np.float32)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = self.rect()
        painter.fillRect(rect, self.bg_color)

        # Grid
        pen = QPen(self.grid_color, 1)
        painter.setPen(pen)
        w, h = rect.width(), rect.height()
        painter.drawLine(0, h // 2, w, h // 2)
        for i in range(1, 5):
            x = int(w * i / 5)
            painter.drawLine(x, 0, x, h)

        # Waveform
        pen = QPen(self.wave_color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        buf = self.buffer
        if buf is None or len(buf) == 0:
            return

        path = QPainterPath()
        L = len(buf)
        first = True
        for i, v in enumerate(buf):
            x = i / L * w
            y = (1 - (v + 1) / 2.0) * h
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)

        painter.drawPath(path)


class BinauralGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Binaural Beat Generator")
        self.setGeometry(80, 80, 980, 560)

        # Autodetect sample rate – works on all current sounddevice versions
        try:
            default_output_idx = sd.default.device['output']
            if default_output_idx is None or default_output_idx < 0:
                # Find first device with output channels
                for i, dev in enumerate(sd.query_devices()):
                    if dev['max_output_channels'] > 0:
                        default_output_idx = i
                        break
                else:
                    default_output_idx = 0
            self.sample_rate = sd.query_devices(default_output_idx)['default_samplerate']
        except Exception:
            print("Warning: Could not autodetect sample rate → using 48000 Hz")
            self.sample_rate = 48000.0

        self.chunk_size = 1024
        self.carrier_freq = 100.0
        self.beat_freq = 4.0
        self.phase_left = 0.0
        self.phase_right = 0.0
        self.playing = False
        self.master_gain = 0.3

        self.ramp_samples = int(self.sample_rate * 0.01)
        self.ramping = False
        self.ramp_pos = 0
        self.ramp_direction = 1

        self.stream = None

        self.init_ui()

        self.osc_timer = QTimer()
        self.osc_timer.setInterval(30)
        self.osc_timer.timeout.connect(self.push_oscilloscope_update)
        self.osc_timer.start()

        self.scope_buffer = np.zeros(self.chunk_size, dtype=np.float32)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)

        top_area = QHBoxLayout()
        top_area.setSpacing(18)

        # Carrier
        carrier_box = QGroupBox("Carrier Frequency")
        carrier_box.setStyleSheet(self.groupbox_style())
        carrier_layout = QVBoxLayout()
        carrier_label = QLabel(f"{self.carrier_freq:.1f} Hz")
        carrier_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        carrier_label.setFont(QFont(MONO_FAMILY, 10, QFont.Weight.Bold))
        self.carrier_label = carrier_label

        carrier_dial = CarrierDial()
        carrier_dial.setMinimum(50)
        carrier_dial.setMaximum(2000)
        carrier_dial.setValue(int(self.carrier_freq))
        carrier_dial.setNotchesVisible(True)
        carrier_dial.valueChanged.connect(self.update_carrier)
        self.carrier_dial = carrier_dial

        carrier_layout.addWidget(carrier_label)
        carrier_layout.addWidget(carrier_dial)
        carrier_box.setLayout(carrier_layout)

        # Beat
        beat_box = QGroupBox("Beat Frequency")
        beat_box.setStyleSheet(self.groupbox_style())
        beat_layout = QVBoxLayout()
        beat_label = QLabel(f"{self.beat_freq:.2f} Hz")
        beat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        beat_label.setFont(QFont(MONO_FAMILY, 10, QFont.Weight.Bold))
        self.beat_label = beat_label

        beat_dial = BeatDial()
        beat_dial.setMinimum(1)
        beat_dial.setMaximum(400)
        beat_dial.setValue(int(self.beat_freq * 10))
        beat_dial.setNotchesVisible(True)
        beat_dial.valueChanged.connect(self.update_beat)
        self.beat_dial = beat_dial

        beat_layout.addWidget(beat_label)
        beat_layout.addWidget(beat_dial)
        beat_box.setLayout(beat_layout)

        # Presets
        center_box = QGroupBox("Presets")
        center_box.setStyleSheet(self.groupbox_style())
        center_layout = QGridLayout()
        presets = [
            ("Deep sleep/Healing", 2.5), ("Astral/OBE/RV", 4.0), ("Creativity/Calm", 7.0),
            ("Relaxation/Flow", 10.0), ("Focus/Energy", 16.0), ("Peak Cognition",40.0),
        ]
        for i, (name, freq) in enumerate(presets):
            btn = QPushButton(name)
            btn.clicked.connect(lambda _, f=freq: self.apply_preset(f))
            btn.setStyleSheet(self.preset_button_style())
            center_layout.addWidget(btn, i // 3, i % 3)
        center_box.setLayout(center_layout)

        top_area.addWidget(carrier_box, 2)
        top_area.addWidget(center_box, 1)
        top_area.addWidget(beat_box, 2)

        self.osc = Oscilloscope()

        bottom = QHBoxLayout()
        self.left_freq_label = QLabel(f"Left: {self.carrier_freq:.2f} Hz")
        self.right_freq_label = QLabel(f"Right: {self.carrier_freq + self.beat_freq:.2f} Hz")
        for lab in (self.left_freq_label, self.right_freq_label):
            lab.setFont(QFont(MONO_FAMILY, 10))
            lab.setStyleSheet("color: #C7F464;")

        self.play_button = QPushButton("Start")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_button.setFixedHeight(36)
        self.play_button.setStyleSheet(self.play_button_style())

        bottom.addWidget(self.left_freq_label)
        bottom.addStretch()
        bottom.addWidget(self.play_button)
        bottom.addStretch()
        bottom.addWidget(self.right_freq_label)

        main_layout.addLayout(top_area)
        main_layout.addWidget(self.osc)
        main_layout.addLayout(bottom)

        self.setStyleSheet(self.window_style())

    def window_style(self):
        return "QMainWindow { background-color: #121212; } QWidget { color: #C7F464; } QGroupBox { border: 1px solid #2E2E2E; border-radius: 6px; margin-top: 6px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px 0 3px; }"

    def groupbox_style(self):
        return "QGroupBox { background: #151515; border: 1px solid #222; color: #C7F464; font-weight: bold; }"

    def preset_button_style(self):
        return "QPushButton { background: #1E1E1E; border: 1px solid #2B2B2B; padding: 8px; } QPushButton:hover { border: 1px solid #4CAF50; }"

    def play_button_style(self):
        return "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2C3E50, stop:1 #22313F); color: white; border-radius: 4px; padding: 6px 12px; } QPushButton:hover { background: #2E8B57; }"

    def apply_preset(self, beat_hz):
        self.beat_freq = float(beat_hz)
        self.beat_dial.blockSignals(True)
        self.beat_dial.setValue(int(self.beat_freq * 10))
        self.beat_dial.blockSignals(False)
        self.update_beat(int(self.beat_freq * 10))

    def update_carrier(self, value):
        self.carrier_freq = float(value)
        self.carrier_label.setText(f"{self.carrier_freq:.1f} Hz")
        self.update_freq_labels()

    def update_beat(self, value):
        self.beat_freq = value / 10.0
        self.beat_label.setText(f"{self.beat_freq:.2f} Hz")
        self.update_freq_labels()

    def update_freq_labels(self):
        leftist = self.carrier_freq
        right = self.carrier_freq + self.beat_freq
        self.left_freq_label.setText(f"Left: {leftist:.2f} Hz")
        self.right_freq_label.setText(f"Right: {right:.2f} Hz")

    # ------------------------------------------------------------------ #
    #   AUDIO GENERATION (unchanged – still returns raw bytes)
    # ------------------------------------------------------------------ #
    def generate_audio_chunk(self):
        t = (np.arange(self.chunk_size) / self.sample_rate).astype(np.float32)
        left = np.sin(2 * np.pi * self.carrier_freq * t + self.phase_left)
        right = np.sin(2 * np.pi * (self.carrier_freq + self.beat_freq) * t + self.phase_right)

        self.phase_left += 2 * np.pi * self.carrier_freq * (self.chunk_size / self.sample_rate)
        self.phase_right += 2 * np.pi * (self.carrier_freq + self.beat_freq) * (self.chunk_size / self.sample_rate)
        self.phase_left %= 2 * np.pi
        self.phase_right %= 2 * np.pi

        stereo = np.column_stack((left, right)).astype(np.float32)
        stereo *= self.master_gain

        if self.ramping:
            ramp = np.ones(self.chunk_size, dtype=np.float32)
            if self.ramp_direction == 1:          # ramp-in
                n = min(self.ramp_samples - self.ramp_pos, self.chunk_size)
                if n > 0:
                    ramp[:n] = np.linspace(self.ramp_pos / self.ramp_samples, 1.0, n)
                    self.ramp_pos += n
                if self.ramp_pos >= self.ramp_samples:
                    self.ramping = False
            else:                                 # ramp-out
                n = min(self.ramp_samples - self.ramp_pos, self.chunk_size)
                if n > 0:
                    ramp[-n:] = np.linspace(1.0 - self.ramp_pos / self.ramp_samples, 0.0, n)
                    self.ramp_pos += n
                if self.ramp_pos >= self.ramp_samples:
                    self.ramping = False
                    self.playing = False
            stereo *= ramp.reshape(-1, 1)

        mono = stereo.mean(axis=1)
        self.scope_buffer = mono.copy()
        return stereo.tobytes()

    # ------------------------------------------------------------------ #
    #   sounddevice CALLBACK (receives a numpy array to fill)
    # ------------------------------------------------------------------ #
    def _sd_callback(self, outdata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        chunk = self.generate_audio_chunk()
        audio = np.frombuffer(chunk, dtype=np.float32).reshape(-1, 2)
        outdata[:] = audio

    # ------------------------------------------------------------------ #
    #   PLAY / STOP
    # ------------------------------------------------------------------ #
    def start_playback(self):
        if self.stream and self.stream.active:
            return
        self.ramping = True
        self.ramp_direction = 1
        self.ramp_pos = 0

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=2,
            blocksize=self.chunk_size,
            callback=self._sd_callback,
            dtype='float32'
        )
        self.stream.start()
        self.playing = True
        self.play_button.setText("Stop")

    def stop_playback(self):
        if not (self.stream and self.stream.active):
            return
        self.ramping = True
        self.ramp_direction = -1
        self.ramp_pos = 0

        # wait for ramp-down
        while self.ramping:
            sd.sleep(10)

        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.playing = False
        self.play_button.setText("Start")
        self.phase_left = 0.0
        self.phase_right = 0.0

    def toggle_playback(self):
        if not self.playing:
            self.start_playback()
        else:
            self.stop_playback()

    # ------------------------------------------------------------------ #
    #   OSCILLOSCOPE UPDATE
    # ------------------------------------------------------------------ #
    def push_oscilloscope_update(self):
        try:
            self.osc.update_buffer(self.scope_buffer)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #   CLEANUP
    # ------------------------------------------------------------------ #
    def closeEvent(self, event):
        if self.stream and self.stream.active:
            self.stop_playback()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    MONO_FAMILY = find_monospace_family()
    window = BinauralGenerator()
    window.show()
    sys.exit(app.exec())