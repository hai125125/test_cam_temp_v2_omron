"""
visualizer.py — Realtime thermal visualization + CSV logging

Depends: matplotlib, numpy, pandas
Install:  pip install matplotlib numpy pandas pyserial

Run:
    python receiver.py --port COM3 --baud 921600
    python receiver.py --port /dev/ttyUSB0 --eeprom eeprom.bin
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.animation as animation
import csv
import time
import threading
import queue
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

ROWS, COLS = 24, 32
D6T_CSV_MIN_VALID_C = 0.0
D6T_CSV_MAX_VALID_C = 350.0
D6T_CSV_MAX_STEP_C = 80.0

# ── Thermal colormap (black→blue→cyan→yellow→red→white) ──────
_THERMAL_COLORS = [
    (0.0,  (0.0,  0.0,  0.0)),
    (0.2,  (0.0,  0.0,  0.8)),
    (0.4,  (0.0,  0.8,  0.8)),
    (0.6,  (0.8,  0.8,  0.0)),
    (0.8,  (0.9,  0.2,  0.0)),
    (1.0,  (1.0,  1.0,  1.0)),
]
_cmap_data = {"red":[], "green":[], "blue":[]}
for pos, (r, g, b) in _THERMAL_COLORS:
    _cmap_data["red"].append((pos, r, r))
    _cmap_data["green"].append((pos, g, g))
    _cmap_data["blue"].append((pos, b, b))
THERMAL_CMAP = LinearSegmentedColormap("thermal", _cmap_data)


@dataclass
class DisplayState:
    temps:        Optional[np.ndarray] = None   # (24,32) latest frame
    hotspot:      tuple = (0, 0)
    min_t:        float = 20.0
    max_t:        float = 40.0
    avg_t:        float = 25.0
    center_t:     float = 25.0
    Ta:           float = 25.0
    frame_id:     int   = 0
    fps:          float = 0.0
    has_mlx640:   bool  = False
    # SMH
    smh_max:      Optional[float] = None
    has_smh:      bool = False
    smh_temps:    Optional[np.ndarray] = None   # (64,) in °C
    # D6T
    d6t_max:      Optional[float] = None
    d6t_raw_max:  Optional[float] = None
    d6t_max_pos:  tuple = (0, 0)
    d6t_temps:    Optional[np.ndarray] = None   # (16,) in C
    has_d6t:      bool = False
    diff_mlx640_d6t: Optional[float] = None
    diff_smh_d6t: Optional[float] = None
    diff640_avg:     Optional[float] = None
    diffd6t_avg:     Optional[float] = None
    diff640_max_abs: Optional[float] = None
    diffd6t_max_abs: Optional[float] = None


class ThermalVisualizer:
    """
    Realtime matplotlib dashboard:
      - Left:    MLX90640 thermal image (24×32)
      - Top-right:  SMH-01B01 8×8 heatmap
      - Bottom: Time series and difference history
    """

    HISTORY_LEN = 5 * 60  # seconds of history in graphs
    DISPLAY_FPS = 4

    def __init__(self, result_queue: queue.Queue):
        self._q      = result_queue
        self._state  = DisplayState()
        self._history = deque(maxlen=self.HISTORY_LEN * self.DISPLAY_FPS)
        self.diff640_history = deque(maxlen=self.HISTORY_LEN * self.DISPLAY_FPS)
        self.diffsmh_history = deque(maxlen=self.HISTORY_LEN * self.DISPLAY_FPS)
        self._frame_times = deque(maxlen=20)
        self._fig = None
        self._ani = None
        self._running = False
        self._start_time = time.time()

    # ── Public ───────────────────────────────────────────────

    def start(self):
        self._running = True
        self._setup_figure()
        self._ani = animation.FuncAnimation(
            self._fig, self._update,
            interval=250,          # 4 fps display
            blit=False,
            cache_frame_data=False,
        )
        plt.show()

    @staticmethod
    def _fmt_diff(value: Optional[float]) -> str:
        if value is None or not np.isfinite(value):
            return "---"
        return f"{value:+.1f} °C"

    @staticmethod
    def _history_stats(history: deque) -> tuple:
        vals = [v for _, v in history if np.isfinite(v)]
        if not vals:
            return None, None
        arr = np.asarray(vals, dtype=np.float32)
        return float(np.mean(arr)), float(np.max(np.abs(arr)))

    @staticmethod
    def _smh_max_c(s: DisplayState) -> Optional[float]:
        if s.smh_temps is None:
            return s.smh_max
        arr = np.asarray(s.smh_temps)
        if arr.size == 0:
            return s.smh_max
        return float(np.nanmax(arr / 10.0)) if arr.dtype.kind in ("u", "i") else float(np.nanmax(arr))

    @staticmethod
    def _set_right_label(text, value: Optional[float], label: str):
        if value is None or not np.isfinite(value):
            text.set_visible(False)
            return
        text.set_visible(True)
        text.set_y(float(value))
        text.set_text(f"{label}: {value:.1f} °C")

    def _update_diff_history(self, s: DisplayState, elapsed: float):
        smh_max = self._smh_max_c(s)
        if smh_max is not None and np.isfinite(smh_max):
            s.smh_max = smh_max
            s.has_smh = True

        if s.has_mlx640 and s.has_d6t and s.d6t_max is not None:
            s.diff_mlx640_d6t = float(s.max_t - s.d6t_max)
            self.diff640_history.append((elapsed, s.diff_mlx640_d6t))

        if s.has_d6t and s.has_smh and s.smh_max is not None and s.d6t_max is not None:
            s.diff_smh_d6t = float(s.smh_max - s.d6t_max)
            self.diffsmh_history.append((elapsed, s.diff_smh_d6t))

        s.diff640_avg, s.diff640_max_abs = self._history_stats(self.diff640_history)
        s.diffd6t_avg, s.diffd6t_max_abs = self._history_stats(self.diffsmh_history)

    # ── Figure setup ─────────────────────────────────────────

    def _setup_figure(self):
        plt.style.use("dark_background")
        self._fig = plt.figure(figsize=(16, 10), facecolor="#0a0a0a")
        self._fig.suptitle(
            "Thermal Node Dashboard", fontsize=14,
            color="#00ff88", fontweight="bold", y=0.98
        )

        gs = gridspec.GridSpec(
            4, 3,
            figure=self._fig,
            left=0.05, right=0.97,
            top=0.93,  bottom=0.06,
            hspace=0.55, wspace=0.35,
        )

        # ── MLX90640 thermal image (large, spans 2 rows) ─────
        ax_thermal = self._fig.add_subplot(gs[0:2, 0:2])
        ax_thermal.set_title("MLX90640  32×24", color="#aaaaaa", fontsize=10)
        ax_thermal.set_xlabel("Column", color="#666666", fontsize=8)
        ax_thermal.set_ylabel("Row",    color="#666666", fontsize=8)
        ax_thermal.tick_params(colors="#666666", labelsize=7)

        dummy = np.full((ROWS, COLS), 25.0)
        self._im_thermal = ax_thermal.imshow(
            dummy, cmap=THERMAL_CMAP, aspect="auto",
            vmin=20, vmax=40, interpolation="bilinear",
        )
        self._cb_thermal = plt.colorbar(
            self._im_thermal, ax=ax_thermal, fraction=0.03, pad=0.02
        )
        self._cb_thermal.ax.tick_params(colors="#aaaaaa", labelsize=7)
        self._cb_thermal.set_label("°C", color="#aaaaaa", fontsize=8)

        # Hotspot marker
        self._hotspot_pt, = ax_thermal.plot([], [], "w+", ms=12, mew=2)

        # Stats text overlay
        self._txt_stats = ax_thermal.text(
            0.02, 0.97, "", transform=ax_thermal.transAxes,
            color="#00ff88", fontsize=8, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#000000aa"),
        )

        # ── SMH-01B01 8×8 heatmap ────────────────────────────
        ax_smh = self._fig.add_subplot(gs[0, 2])
        ax_smh.set_title("SMH-01B01  8×8", color="#aaaaaa", fontsize=9)
        ax_smh.tick_params(colors="#555555", labelsize=6)
        dummy_smh = np.full((8, 8), 25.0)
        self._im_smh = ax_smh.imshow(
            dummy_smh, cmap=THERMAL_CMAP, aspect="auto",
            vmin=20, vmax=40, interpolation="nearest",
        )
        plt.colorbar(self._im_smh, ax=ax_smh, fraction=0.05, pad=0.04).ax.tick_params(labelsize=6)

        # ── D6T 4x4 heatmap ───────────────────────
        ax_d6t = self._fig.add_subplot(gs[1, 2])
        ax_d6t.set_title("Omron D6T 4×4", color="#aaaaaa", fontsize=9)
        ax_d6t.tick_params(colors="#555555", labelsize=6)
        dummy_d6t = np.full((4, 4), 25.0)
        self._im_d6t = ax_d6t.imshow(
            dummy_d6t, cmap=THERMAL_CMAP, aspect="auto",
            vmin=20, vmax=40, interpolation="nearest",
        )
        plt.colorbar(self._im_d6t, ax=ax_d6t, fraction=0.05, pad=0.04).ax.tick_params(labelsize=6)
        self._hotspot_d6t, = ax_d6t.plot([], [], "w+", ms=10, mew=1.8)
        self._txt_d6t = ax_d6t.text(
            0.02, 0.96, "", transform=ax_d6t.transAxes,
            color="white", fontsize=8, va="top",
            bbox=dict(facecolor="#00000099", edgecolor="none", alpha=0.8, pad=2),
        )

        # ── Time-series (Max Comparison) ──────────────────
        ax_ts = self._fig.add_subplot(gs[2, 0:3])
        ax_ts.set_title("Max Temperature Comparison", color="#aaaaaa", fontsize=9)
        ax_ts.set_xlabel("Time (s)", color="#666666", fontsize=7)
        ax_ts.set_ylabel("°C",    color="#666666", fontsize=7)
        ax_ts.tick_params(colors="#555555", labelsize=7)
        ax_ts.set_facecolor("#111111")
        self._line_mlx640, = ax_ts.plot([], [], color="#00ff88", lw=1.5, label="MLX640 Max")
        self._line_smh,    = ax_ts.plot([], [], color="#ffaa00", lw=1.5, label="SMH Max")
        self._line_d6t, = ax_ts.plot([], [], color="#ff6600", lw=1.5, label="D6T Max")
        ax_ts.legend(loc="upper left", fontsize=7, facecolor="#222222", edgecolor="#444444")
        self._txt_ts_mlx640 = ax_ts.text(
            0.995, 25.0, "", transform=ax_ts.get_yaxis_transform(),
            ha="right", va="center", color="#00ff88", fontsize=8,
            bbox=dict(facecolor="#111111", edgecolor="none", alpha=0.8, pad=1.5),
        )
        self._txt_ts_smh = ax_ts.text(
            0.995, 24.0, "", transform=ax_ts.get_yaxis_transform(),
            ha="right", va="center", color="#ffaa00", fontsize=8,
            bbox=dict(facecolor="#111111", edgecolor="none", alpha=0.8, pad=1.5),
        )
        self._txt_ts_d6t = ax_ts.text(
            0.995, 23.0, "", transform=ax_ts.get_yaxis_transform(),
            ha="right", va="center", color="#ff6600", fontsize=8,
            bbox=dict(facecolor="#111111", edgecolor="none", alpha=0.8, pad=1.5),
        )
        self._ax_ts = ax_ts

        ax_diff = self._fig.add_subplot(gs[3, 0:3])
        ax_diff.set_title("Temperature Difference vs Omron D6T", color="#aaaaaa", fontsize=9)
        ax_diff.set_xlabel("Time (s)", color="#666666", fontsize=7)
        ax_diff.set_ylabel(" °C difference", color="#666666", fontsize=7)
        ax_diff.tick_params(colors="#555555", labelsize=7)
        ax_diff.set_facecolor("#111111")
        ax_diff.axhline(0.0, color="#777777", lw=0.8, ls="--")
        self._line_diff640, = ax_diff.plot([], [], color="#00ff88", lw=1.5, label="MLX640 - D6T")
        self._line_diffd6t, = ax_diff.plot([], [], color="#ffaa00", lw=1.5, label="SMH - D6T")
        ax_diff.legend(loc="upper left", fontsize=7, facecolor="#222222", edgecolor="#444444")
        self._txt_diff640 = ax_diff.text(
            0.995, 0.0, "", transform=ax_diff.get_yaxis_transform(),
            ha="right", va="center", color="#00ff88", fontsize=8,
            bbox=dict(facecolor="#111111", edgecolor="none", alpha=0.8, pad=1.5),
        )
        self._txt_diffd6t = ax_diff.text(
            0.995, -1.0, "", transform=ax_diff.get_yaxis_transform(),
            ha="right", va="center", color="#ffaa00", fontsize=8,
            bbox=dict(facecolor="#111111", edgecolor="none", alpha=0.8, pad=1.5),
        )
        self._ax_diff = ax_diff

        # ── Sensor comparison bar ─────────────────────────────
        # Store axes for update
        self._ax_thermal = ax_thermal
        self._ax_smh     = ax_smh
        self._ax_d6t     = ax_d6t

    # ── Animation update ─────────────────────────────────────

    def _update(self, _frame):
        # Drain result queue — keep only latest frame per sensor type
        while not self._q.empty():
            try:
                item = self._q.get_nowait()
                self._ingest(item)
            except queue.Empty:
                break

        s = self._state
        elapsed = time.time() - self._start_time
        self._update_diff_history(s, elapsed)

        # ── Thermal image ─────────────────────────────────────
        if s.temps is not None:
            vmin = max(s.min_t - 2, -20)
            vmax = min(s.max_t + 2, 120)
            self._im_thermal.set_data(s.temps)
            self._im_thermal.set_clim(vmin, vmax)
            self._hotspot_pt.set_data([s.hotspot[1]], [s.hotspot[0]])
            self._txt_stats.set_text(
                f"Min:{s.min_t:.1f}  Avg:{s.avg_t:.1f}  "
                f"Max:{s.max_t:.1f} °C\n"
                f"Delta MLX640-D6T:{self._fmt_diff(s.diff_mlx640_d6t)}  "
                f"Delta SMH-D6T:{self._fmt_diff(s.diff_smh_d6t)}\n"
                f"Avg Delta:{self._fmt_diff(s.diff640_avg)} / {self._fmt_diff(s.diffd6t_avg)}  "
                f"MaxAbs Delta:{self._fmt_diff(s.diff640_max_abs)} / {self._fmt_diff(s.diffd6t_max_abs)}\n"
                f"Ta:{s.Ta:.1f}°C  FPS:{s.fps:.1f}  ID:{s.frame_id}"
            )

        # ── SMH heatmap ───────────────────────────────────────
        if s.smh_temps is not None:
            arr = np.asarray(s.smh_temps)
            # If integers, assume old firmware semantics: values in 0.1°C
            if arr.dtype.kind in ("u", "i"):
                grid = (arr / 10.0).reshape(8, 8)
            else:
                grid = arr.reshape(8, 8)
            self._im_smh.set_data(grid)
            self._im_smh.set_clim(np.nanmin(grid) - 1, np.nanmax(grid) + 1)

        # ── D6T 4x4 heatmap ──────────────────────────────────────
        if s.d6t_temps is not None:
            d6t_grid = np.asarray(s.d6t_temps, dtype=np.float32).reshape(4, 4)
            self._im_d6t.set_data(d6t_grid)
            self._im_d6t.set_clim(20, 40)
            self._hotspot_d6t.set_data([s.d6t_max_pos[0]], [s.d6t_max_pos[1]])
            self._txt_d6t.set_text(f"{s.d6t_max:.1f}°C @ {s.d6t_max_pos}")

        # ── Time series ───────────────────────────────────────
        smh_max = s.smh_max if s.smh_max is not None else np.nan

        self._history.append((
            elapsed,
            s.max_t if s.has_mlx640 else np.nan,
            smh_max,
            s.d6t_max if s.d6t_max is not None else np.nan,
        ))

        if len(self._history) > 1:
            ts    = [h[0] for h in self._history]
            m640  = [h[1] for h in self._history]
            smh   = [h[2] for h in self._history]
            d6t   = [h[3] for h in self._history]
            
            self._line_mlx640.set_data(ts, m640)
            self._line_smh.set_data(ts, smh)
            self._line_d6t.set_data(ts, d6t)
            
            self._ax_ts.set_xlim(max(0, elapsed - self.HISTORY_LEN), max(self.HISTORY_LEN, elapsed))
            self._ax_ts.relim()
            self._ax_ts.autoscale_view(scalex=False, scaley=True)
            self._set_right_label(self._txt_ts_mlx640, m640[-1], "MLX640")
            self._set_right_label(self._txt_ts_smh, smh[-1], "SMH")
            self._set_right_label(self._txt_ts_d6t, d6t[-1], "D6T")

        if self.diff640_history or self.diffsmh_history:
            d640_t = [h[0] for h in self.diff640_history]
            d640_v = [h[1] for h in self.diff640_history]
            smh_t = [h[0] for h in self.diffsmh_history]
            smh_v = [h[1] for h in self.diffsmh_history]
            self._line_diff640.set_data(d640_t, d640_v)
            self._line_diffd6t.set_data(smh_t, smh_v)
            self._ax_diff.set_xlim(max(0, elapsed - self.HISTORY_LEN), max(self.HISTORY_LEN, elapsed))
            self._ax_diff.relim()
            self._ax_diff.autoscale_view(scalex=False, scaley=True)
            self._set_right_label(self._txt_diff640, d640_v[-1] if d640_v else None, "MLX640-D6T")
            self._set_right_label(self._txt_diffd6t, smh_v[-1] if smh_v else None, "SMH-D6T")

        # ── Comparison bars ───────────────────────────────────
        # SMH max: handle both integer (tenths) and float (°C)
        self._fig.canvas.draw_idle()

    def _ingest(self, item):
        from thermography import ThermalResult
        from protocol import SMHFrame, D6TFrame

        now = time.time()
        s = self._state

        if isinstance(item, ThermalResult):
            self._frame_times.append(now)
            if len(self._frame_times) >= 2:
                dt = self._frame_times[-1] - self._frame_times[0]
                s.fps = (len(self._frame_times) - 1) / dt if dt > 0 else 0
            s.temps     = item.temperatures
            s.hotspot   = item.hotspot_idx
            s.min_t     = item.min_temp
            s.max_t     = item.max_temp
            s.avg_t     = item.avg_temp
            s.center_t  = item.center_temp
            s.Ta        = item.Ta
            s.frame_id  = item.frame_id
            s.has_mlx640 = True

        elif isinstance(item, SMHFrame):
            s.smh_temps = item.pixels
            s.smh_max = self._smh_max_c(s)
            s.has_smh = s.smh_max is not None

        elif isinstance(item, D6TFrame):
            if not getattr(item, "d6t_valid", True):
                logger.warning(
                    "[D6T CHART SKIP] raw=%.2f calib=%.2f valid=False reason=%s",
                    item.max_celsius,
                    item.calib_celsius,
                    ",".join(getattr(item, "d6t_invalid_reasons", ["frame_flag_invalid"])),
                )
                return
            s.d6t_temps = item.pixels_celsius
            s.d6t_raw_max = item.max_celsius
            s.d6t_max = item.calib_celsius
            s.d6t_max_pos = (item.max_x, item.max_y)
            s.has_d6t = True


class CSVLogger:
    """Thread-safe CSV logger for all sensor data."""

    FIELDS = [
        "time",
        "mlx90640_max",
        "smh01b01_max",
        "d6t_max",
        "diff_mlx90640_d6t",
        "diff_smh01b01_d6t",
    ]

    def __init__(
        self,
        path: str,
        append: bool = False,
    ):
        self._path = path
        self._append = bool(append)
        self._lock = threading.Lock()
        self._file = None
        self._writer = None
        self._latest_mlx640 = None
        self._latest_smh = None
        self._latest_d6t = None
        self._last_written_ids = None
        self._last_written_d6t_id = None
        self._last_skipped_d6t_id = None
        self._previous_valid_d6t = None

    def open(self):
        import os

        mode = "a" if self._append else "w"
        needs_header = True
        if self._append and os.path.exists(self._path) and os.path.getsize(self._path) > 0:
            needs_header = False
            with open(self._path, "r", encoding="utf-8", newline="") as existing:
                first_line = existing.readline().strip()
            expected_header = ",".join(self.FIELDS)
            if first_line and first_line != expected_header:
                logger.warning(
                    "CSV header differs from simplified schema; appending rows without rewriting existing data: %s",
                    self._path,
                )

        self._file = open(self._path, mode, newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDS)
        if needs_header:
            self._writer.writeheader()
            logger.info("CSV header written: %s", self._path)
        else:
            logger.info("CSV header skipped for append: %s", self._path)
        self._file.flush()
        logger.info(
            "CSV logging to %s append=%s",
            self._path,
            self._append,
        )

    def log_mlx640(self, result):
        from thermography import ThermalResult
        if not isinstance(result, ThermalResult): return
        with self._lock:
            self._latest_mlx640 = {
                "frame_id": int(result.frame_id),
                "max": float(result.max_temp),
            }
            self._try_log_combined_locked()

    def log_d6t(self, frame):
        from protocol import D6TFrame
        if not isinstance(frame, D6TFrame): return
        with self._lock:
            self._latest_d6t = {
                "frame_id": int(frame.frame_id),
                "raw_max": float(frame.max_celsius),
                "max": float(frame.calib_celsius),
                "x": int(frame.max_x),
                "y": int(frame.max_y),
                "calib_x10": int(frame.calib_x10),
                "firmware_raw_max_x10": int(getattr(frame, "firmware_raw_max_x10", 0)),
                "payload_hex": frame.payload.hex(" ") if getattr(frame, "payload", None) else "",
                "pixels_raw": np.asarray(frame.pixels_raw, dtype=np.uint16).tolist(),
                "pixels_c": [float(v) for v in frame.pixels_celsius.tolist()],
            }
            self._try_log_combined_locked()

    def log_smh(self, frame):
        from protocol import SMHFrame
        if not isinstance(frame, SMHFrame): return
        arr = np.asarray(frame.pixels)
        max_v = float(np.nanmax(arr) / 10.0) if arr.dtype.kind in ('u', 'i') else float(np.nanmax(arr))
        with self._lock:
            self._latest_smh = {
                "frame_id": int(frame.frame_id),
                "max": max_v,
            }
            self._try_log_combined_locked()

    def _try_log_combined_locked(self):
        if self._writer is None:
            return
        if self._latest_mlx640 is None or self._latest_smh is None or self._latest_d6t is None:
            return

        ids = (
            self._latest_mlx640["frame_id"],
            self._latest_smh["frame_id"],
            self._latest_d6t["frame_id"],
        )
        if ids == self._last_written_ids:
            return
        if self._latest_d6t["frame_id"] == self._last_written_d6t_id:
            return

        mlx640 = self._latest_mlx640
        smh = self._latest_smh
        d6t = self._latest_d6t
        diff640 = mlx640["max"] - d6t["max"]
        diffsmh = smh["max"] - d6t["max"]
        if not self._is_valid_d6t_for_csv_locked(d6t, mlx640, smh, diff640, diffsmh):
            self._last_skipped_d6t_id = d6t["frame_id"]
            self._last_written_d6t_id = d6t["frame_id"]
            return

        self._writer.writerow({
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mlx90640_max": f"{mlx640['max']:.2f}",
            "smh01b01_max": f"{smh['max']:.2f}",
            "d6t_max": f"{d6t['max']:.2f}",
            "diff_mlx90640_d6t": f"{diff640:.2f}",
            "diff_smh01b01_d6t": f"{diffsmh:.2f}",
        })
        self._file.flush()
        self._last_written_ids = ids
        self._last_written_d6t_id = self._latest_d6t["frame_id"]
        self._previous_valid_d6t = d6t["max"]
        logger.debug(
            "CSV row: mlx640_d6t_diff=%+.2fC smh_d6t_diff=%+.2fC d6t_raw=%.2fC d6t_calib=%.2fC d6t_pos=(%d,%d)",
            diff640,
            diffsmh,
            d6t["raw_max"],
            d6t["max"],
            d6t["x"],
            d6t["y"],
        )

    def _is_valid_d6t_for_csv_locked(self, d6t, mlx640, smh, diff640, diffsmh) -> bool:
        d6t_max = d6t["max"]
        reasons = []
        if not np.isfinite(d6t_max):
            reasons.append("not_finite")
        if d6t_max < D6T_CSV_MIN_VALID_C or d6t_max > D6T_CSV_MAX_VALID_C:
            reasons.append(f"range_{d6t_max:.2f}")
        if (
            self._previous_valid_d6t is not None
            and np.isfinite(self._previous_valid_d6t)
            and abs(d6t_max - self._previous_valid_d6t) > D6T_CSV_MAX_STEP_C
        ):
            reasons.append(f"step_{d6t_max - self._previous_valid_d6t:+.2f}")

        if not reasons:
            return True

        if self._last_skipped_d6t_id != d6t["frame_id"]:
            logger.warning(
                "[D6T OUTLIER] CSV row skipped reasons=%s timestamp=%s "
                "payload_hex=%s pixels_raw_x10=%s pixels_c=%s "
                "d6t_raw_max=%.2f d6t_calib=%.2f calib_x10=%d firmware_raw_max_x10=%d max_x=%d max_y=%d "
                "mlx90640_max=%.2f smh01b01_max=%.2f "
                "diff_mlx90640_d6t=%+.2f diff_smh01b01_d6t=%+.2f previous_valid_d6t=%s",
                ",".join(reasons),
                time.strftime("%Y-%m-%dT%H:%M:%S"),
                d6t["payload_hex"],
                d6t["pixels_raw"],
                [round(v, 1) for v in d6t["pixels_c"]],
                d6t["raw_max"],
                d6t["max"],
                d6t["calib_x10"],
                d6t["firmware_raw_max_x10"],
                d6t["x"],
                d6t["y"],
                mlx640["max"],
                smh["max"],
                diff640,
                diffsmh,
                f"{self._previous_valid_d6t:.2f}" if self._previous_valid_d6t is not None else "None",
            )
        return False

    def close(self):
        if self._file:
            self._file.close()
