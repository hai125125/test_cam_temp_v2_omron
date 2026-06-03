"""
receiver.py — Thermal Node serial receiver

Usage:
    python receiver.py --port COM7
    python receiver.py --port /dev/ttyUSB0 --baud 921600
    python receiver.py --port COM7 --eeprom eeprom.bin --csv output.csv
    python receiver.py --port COM7 --no-gui --csv output.csv   # headless

Requires:
    pip install pyserial numpy matplotlib pandas

Optional:
    pip install pyserial numpy matplotlib pandas
"""

import argparse
from datetime import datetime
import csv
import logging
import queue
import threading
import time
import sys
import numpy as np
import serial

from protocol     import ThermalNodeParser, MLX640Frame, MLX90640LegacyFrame, SMHFrame, D6TFrame, D6TStatusFrame
from thermography import ApplicationCorrectionConfig, MLX90640Processor
from visualizer   import ThermalVisualizer, CSVLogger

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("receiver")
logging.getLogger("matplotlib").setLevel(logging.WARNING)

try:
    from calib_profiles import CALIB_PROFILES, calibrate
except ImportError:
    CALIB_PROFILES = {}

    def calibrate(sensor_name, raw_value, distance_cm, direction=None):
        logger.warning("[CALIB] profile not found, using raw value")
        return raw_value
else:
    logger.info("[CALIB] loaded profiles sensors=%s", sorted(CALIB_PROFILES))

D6T_MIN_VALID_C = 0.0
D6T_MAX_VALID_C = 80.0
logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

BAUD_DEFAULT = 921600
D6T_BUILTIN_CALIB_PROFILES = set()
D6T_DISABLED_BUILTIN_CALIB_PROFILES = {5, 10, 15, 20}
D6T_CHART_MIN_VALID_C = 0.0
D6T_CHART_MAX_VALID_C = 350.0
D6T_CHART_MAX_STEP_C = 80.0


def iso_now_ms() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def parse_iso_timestamp(value: str) -> float:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).timestamp()


def load_d6t_manual_calibration(path: str | None) -> dict[int, list[tuple[float, float]]]:
    if not path:
        return {}

    tables: dict[int, list[tuple[float, float]]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"distance_cm", "d6t_raw", "reference_temp"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"D6T calibration CSV missing columns: {sorted(missing)}")

        for row_num, row in enumerate(reader, start=2):
            try:
                distance = int(float(row["distance_cm"]))
                raw = float(row["d6t_raw"])
                reference = float(row["reference_temp"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid D6T calibration row {row_num}: {row}") from exc

            if not (np.isfinite(raw) and np.isfinite(reference)):
                raise ValueError(f"Invalid D6T calibration row {row_num}: non-finite value")
            tables.setdefault(distance, []).append((raw, reference))

    for distance, points in tables.items():
        points.sort(key=lambda p: p[0])
        deduped: list[tuple[float, float]] = []
        for raw, reference in points:
            if deduped and abs(raw - deduped[-1][0]) < 1e-6:
                logger.warning(
                    "[D6T] Duplicate manual calibration raw point for %dcm: %.3f, using last value",
                    distance,
                    raw,
                )
                deduped[-1] = (raw, reference)
            else:
                deduped.append((raw, reference))
        tables[distance] = deduped

    logger.info(
        "[D6T] Loaded manual calibration CSV %s distances=%s",
        path,
        {distance: len(points) for distance, points in sorted(tables.items())},
    )
    return tables


def calibrate_d6t_manual_csv(
    raw_temp_c: float,
    distance_cm: int | None,
    manual_tables: dict[int, list[tuple[float, float]]],
) -> tuple[float, str] | None:
    if distance_cm is None or distance_cm not in manual_tables:
        return None

    points = manual_tables[distance_cm]
    if not points:
        return None

    if len(points) == 1:
        only_raw, only_reference = points[0]
        if abs(raw_temp_c - only_raw) < 1e-6:
            return only_reference, "manual_csv"
        logger.warning(
            "[D6T CALIB] distance=%s raw=%.2f outside single-point manual table, using raw value",
            distance_cm,
            raw_temp_c,
        )
        return raw_temp_c, "raw_fallback"

    min_raw = points[0][0]
    max_raw = points[-1][0]
    if raw_temp_c < min_raw or raw_temp_c > max_raw:
        logger.warning(
            "[D6T CALIB] distance=%s raw=%.2f outside manual CSV range %.2f..%.2f, using raw value",
            distance_cm,
            raw_temp_c,
            min_raw,
            max_raw,
        )
        return raw_temp_c, "raw_fallback"

    for (raw0, ref0), (raw1, ref1) in zip(points, points[1:]):
        if raw0 <= raw_temp_c <= raw1:
            if abs(raw1 - raw0) < 1e-6:
                return ref1, "manual_csv"
            ratio = (raw_temp_c - raw0) / (raw1 - raw0)
            return ref0 + ratio * (ref1 - ref0), "manual_csv"

    return raw_temp_c, "raw_fallback"


def calibrate_d6t(
    raw_temp_c: float,
    distance_cm: int | None,
    manual_tables: dict[int, list[tuple[float, float]]] | None = None,
) -> tuple[float, str]:
    manual = calibrate_d6t_manual_csv(raw_temp_c, distance_cm, manual_tables or {})
    if manual is not None:
        return manual

    if raw_temp_c < 40.0:
        return raw_temp_c, "raw_fallback"

    if distance_cm not in D6T_BUILTIN_CALIB_PROFILES:
        return raw_temp_c, "raw_fallback"

    a = 1.0
    b = 0.0
    temp = raw_temp_c
    # CM5, CM10, and CM20 legacy coefficients are intentionally kept for
    # reference below, but disabled by D6T_BUILTIN_CALIB_PROFILES. The CM15
    # builtin profile was removed so 15cm uses the raw value unless a manual
    # CSV calibration table is provided.
    if distance_cm == 5:
        if temp < 40: a, b = 1, 0
        elif temp < 43.0: a, b = 2.619, -47.458
        elif temp < 53.4: a, b = 1.985, -21.839
        elif temp < 63.0: a, b = 1.796, -12.333
        elif temp < 73.6: a, b = 1.694, -4.753
        elif temp < 82.6: a, b = 1.997, -27.095
        elif temp < 91.8: a, b = 1.384, 23.810
        elif temp < 101.6: a, b = 1.297, 31.786
        elif temp < 112.7: a, b = 1.427, 18.473
        elif temp < 123.9: a, b = 1.219, 42.441
        else: a, b = 0.464, 138.475
    elif distance_cm == 10:
        if temp < 30: a, b = 1, 0
        elif temp < 32.0: a, b = 4.549, -85.771
        elif temp < 39.4: a, b = 4.735, -92.874
        elif temp < 46.2: a, b = 2.944, -21.495
        elif temp < 53.2: a, b = 3.361, -38.793
        elif temp < 59.8: a, b = 2.919, -17.660
        elif temp < 67.6: a, b = 2.809, -13.009
        elif temp < 74.1: a, b = 2.301, 18.906
        elif temp < 80.9: a, b = 1.433, 83.284
        elif temp < 86.3: a, b = 0.667, 146.267
        else: a, b = 0.268, 182.156
    elif distance_cm == 20:
        if temp < 30: a, b = 1, 0
        elif temp < 30.0: a, b = 1.113, 8.329
        elif temp < 31.2: a, b = 17.425, -485.622
        elif temp < 32.4: a, b = 20.618, -579.625
        elif temp < 33.5: a, b = 36.069, -1081.714
        elif temp < 34.7: a, b = 6.357, -90.993
        elif temp < 35.6: a, b = 11.252, -260.541
        elif temp < 36.5: a, b = 15.667, -420.833
        elif temp < 38.4: a, b = 11.284, -265.856
        elif temp < 39.3: a, b = 0.000, 171.100
        elif temp < 40.6: a, b = 8.600, -169.460
        elif temp < 42.1: a, b = 0.000, 183.800
        elif temp < 43.3: a, b = 39.000, -1496.800
        elif temp < 45.1: a, b = 0.000, 196.000
        elif temp < 47.0: a, b = 0.000, 199.500
        else: a, b = 0.000, 202.700

    return temp * a + b, f"builtin_cm{distance_cm}"


def apply_d6t_calibration(
    frame: D6TFrame,
    distance_cm: int | None,
    manual_tables: dict[int, list[tuple[float, float]]] | None = None,
) -> D6TFrame:
    raw_max = frame.max_celsius
    calib, mode = calibrate_d6t(raw_max, distance_cm, manual_tables)

    if calib < 0 or calib > 350 or abs(calib - raw_max) > 150:
        logger.warning(
            "[D6T CALIB WARN] raw=%.2f calib=%.2f distance=%s, using raw value",
            raw_max,
            calib,
            distance_cm,
        )
        calib = raw_max
        mode = "raw_fallback"

    frame.calib_x10 = int(round(calib * 10.0))
    frame.d6t_calib_mode = mode
    frame.d6t_calib_distance_cm = distance_cm
    logger.info(
        "[D6T CALIB] distance=%s raw=%.2f calib=%.2f mode=%s",
        distance_cm,
        raw_max,
        calib,
        mode,
    )
    return frame


def d6t_profile_name(distance_cm: int | None) -> str:
    return f"CM{distance_cm}" if distance_cm in D6T_BUILTIN_CALIB_PROFILES else "RAW"


def d6t_validation_reasons(frame: D6TFrame, previous_valid_d6t: float | None) -> list[str]:
    reasons = []
    pixels_c = np.asarray(frame.pixels_raw, dtype=np.float32) / 10.0
    d6t_calib = frame.calib_celsius

    if pixels_c.size != 16 or not np.all(np.isfinite(pixels_c)):
        reasons.append(f"bad_pixels_size_{pixels_c.size}")
    if not np.isfinite(d6t_calib):
        reasons.append("calib_not_finite")
    if d6t_calib < D6T_CHART_MIN_VALID_C or d6t_calib > D6T_CHART_MAX_VALID_C:
        reasons.append(f"calib_range_{d6t_calib:.2f}")
    if (
        previous_valid_d6t is not None
        and np.isfinite(previous_valid_d6t)
        and abs(d6t_calib - previous_valid_d6t) > D6T_CHART_MAX_STEP_C
    ):
        reasons.append(f"calib_step_{d6t_calib - previous_valid_d6t:+.2f}")

    return reasons


def log_smh_matrix_diagnostics(frame_id: int, temps: np.ndarray):
    arr = np.asarray(temps, dtype=np.float32)
    if arr.size != 64:
        logger.warning(f"SMH diagnostics skipped: frame={frame_id} size={arr.size}")
        return

    grid = arr.reshape(8, 8)
    top = grid[:4, :]
    bottom = grid[4:, :]
    top_bottom_max_diff = float(np.nanmax(np.abs(top - bottom)))

    chunks = arr.reshape(4, 16)
    chunk01_max_diff = float(np.nanmax(np.abs(chunks[0] - chunks[1])))
    chunk02_max_diff = float(np.nanmax(np.abs(chunks[0] - chunks[2])))
    chunk13_max_diff = float(np.nanmax(np.abs(chunks[1] - chunks[3])))

    logger.debug(
        "SMH matrix frame=%d rows=%s",
        frame_id,
        [" ".join(f"{v:5.1f}" for v in row) for row in grid],
    )
    logger.debug(
        "SMH duplicate check frame=%d top_bottom_max_diff=%.3f "
        "chunk0-1=%.3f chunk0-2=%.3f chunk1-3=%.3f",
        frame_id,
        top_bottom_max_diff,
        chunk01_max_diff,
        chunk02_max_diff,
        chunk13_max_diff,
    )

    if top_bottom_max_diff < 0.05:
        logger.warning(
            "SMH frame=%d top half and bottom half are nearly identical; "
            "suspect I2C repeated read/chunking or sensor read-order issue",
            frame_id,
        )
    if chunk02_max_diff < 0.05 and chunk13_max_diff < 0.05:
        logger.warning(
            "SMH frame=%d chunks 0/2 and 1/3 are nearly identical; "
            "this matches a repeated 64-byte read pattern",
            frame_id,
        )


# ── EEPROM dump helper ────────────────────────────────────────

def dump_eeprom(port: str, baud: int, outfile: str):
    """
    Dump MLX90640 EEPROM via special firmware command.
    Firmware must support 'DUMP_EEPROM' command (future extension).
    For now: use the dedicated ATmega2560 EEPROM dump firmware to create
    a local binary file, then load that file with --eeprom.
    """
    logger.info("EEPROM dump is not implemented in this receiver.")
    logger.info("Use the ATmega2560 EEPROM dump firmware to save eeprom.bin locally.")
    logger.info("Then run receiver.py with --eeprom eeprom.bin.")


def log_d6t_rx_debug(frame: D6TFrame, distance_cm: int | None = None):
    pixels_raw = np.asarray(frame.pixels_raw, dtype=np.uint16)
    pixels_c = pixels_raw.astype(np.float32) / 10.0
    firmware_raw_max_x10 = int(getattr(frame, "firmware_raw_max_x10", 0))
    payload = getattr(frame, "payload", b"")
    if not payload:
        payload = (
            pixels_raw.astype("<u2", copy=False).tobytes()
            + int(frame.calib_x10).to_bytes(2, "little", signed=True)
            + bytes([int(frame.max_x), int(frame.max_y)])
        )
    logger.debug("[D6T RX] payload_len=%d", len(payload))
    logger.debug("[D6T RX] payload_hex=%s", payload.hex(" "))
    logger.debug("[D6T RX] pixels_raw_x10=%s", pixels_raw.tolist())
    logger.debug("[D6T RX] pixels_c=%s", [round(float(v), 1) for v in pixels_c.tolist()])
    logger.info(
        "[D6T] raw=%.2f calib=%.2f profile=%s raw_max_x10=%d calib_x10=%d firmware_raw_max_x10=%d",
        frame.max_celsius,
        frame.calib_celsius,
        d6t_profile_name(distance_cm),
        frame.max_raw,
        int(frame.calib_x10),
        firmware_raw_max_x10,
    )
    logger.debug(
        "[D6T RX] max=%.1f min=%.1f avg=%.1f pos=(%d,%d)",
        float(np.nanmax(pixels_c)),
        float(np.nanmin(pixels_c)),
        float(np.nanmean(pixels_c)),
        int(frame.max_x),
        int(frame.max_y),
    )


def is_valid_d6t_frame(frame: D6TFrame) -> bool:
    pixels_c = np.asarray(frame.pixels_raw, dtype=np.float32) / 10.0
    if pixels_c.size != 16 or not np.all(np.isfinite(pixels_c)):
        logger.warning("[WARN] Suspicious D6T frame: bad pixel payload size=%d", pixels_c.size)
        return True

    min_c = float(np.nanmin(pixels_c))
    max_c = float(np.nanmax(pixels_c))
    if min_c < D6T_MIN_VALID_C or max_c > D6T_MAX_VALID_C:
        logger.warning(
            "[WARN] Suspicious D6T frame accepted: min=%.1f max=%.1f pixels=%s",
            min_c,
            max_c,
            [round(float(v), 1) for v in pixels_c.tolist()],
        )

    return True


# ── Serial reader thread ──────────────────────────────────────

class SerialReader(threading.Thread):
    """
    Reads bytes from serial port, feeds to ThermalNodeParser,
    puts parsed frames in result_queue for processing thread.
    """

    def __init__(self, ser: serial.Serial, raw_queue: queue.Queue):
        super().__init__(daemon=True, name="SerialReader")
        self._ser    = ser
        self._raw_q  = raw_queue
        self._running = True
        self._bytes_rx = 0
        self._t_start  = time.time()

    def run(self):
        parser = ThermalNodeParser()
        logger.info("Serial reader started")

        while self._running:
            try:
                data = self._ser.read(256)
                if not data:
                    continue
                self._bytes_rx += len(data)

                frames = parser.feed(data)
                for f in frames:
                    self._raw_q.put(f)

                # Print ASCII debug lines (comments from firmware)
                # Already consumed by parser if recognized
                # Unrecognized lines → log
                elapsed = time.time() - self._t_start
                if elapsed > 0 and int(elapsed) % 10 == 0:
                    bps = self._bytes_rx / elapsed
                    logger.debug(f"RX rate: {bps:.0f} B/s  stats={parser.stats}")

            except serial.SerialException as e:
                logger.error(f"Serial error: {e}")
                self._running = False
                break
            except Exception as e:
                logger.error(f"Reader error: {e}")

    def stop(self):
        self._running = False


# ── Processing thread ─────────────────────────────────────────

class ProcessingThread(threading.Thread):
    """
    Takes raw frames from raw_queue, runs thermography,
    puts ThermalResult in result_queue for visualization.
    """

    def __init__(self, raw_queue: queue.Queue,
                 result_queue: queue.Queue,
                 processor: MLX90640Processor,
                 csv_logger: CSVLogger,
                 d6t_distance_cm: int | None = None,
                 d6t_manual_calib: dict[int, list[tuple[float, float]]] | None = None,
                 calib_direction: str | None = None):
        super().__init__(daemon=True, name="Processing")
        self._raw_q    = raw_queue
        self._res_q    = result_queue
        self._proc     = processor
        self._csv      = csv_logger
        self._running  = True
        self._d6t_distance_cm = d6t_distance_cm
        self._d6t_manual_calib = d6t_manual_calib or {}
        self._calib_direction = calib_direction
        self._previous_valid_d6t = None

    def run(self):
        logger.info("Processing thread started")
        while self._running:
            try:
                frame = self._raw_q.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                if isinstance(frame, MLX640Frame):

                    if np.all(frame.pixels_raw == 0x7FFF):
                        logger.error("MCU sending all invalid pixels (0x7FFF)")

                    logger.info(
                        f"RAW FRAME F{frame.frame_id} "
                        f"min={np.min(frame.pixels_raw)} "
                        f"max={np.max(frame.pixels_raw)}"
                    )

                    result = self._proc.process(frame)
                    if result:
                        result.mlx90640_calib = calibrate(
                            "mlx90640",
                            result.max_temp,
                            self._d6t_distance_cm,
                            self._calib_direction,
                        )
                        logger.debug(
                            "[DASH CHECK] receiver->queue sensor=mlx90640 raw=%.2f calib=%.2f attr=mlx90640_calib",
                            result.max_temp,
                            result.mlx90640_calib,
                        )
                        self._res_q.put(result)
                        if self._csv:
                            self._csv.log_mlx640(result)
                        logger.debug(
                            f"F{result.frame_id} "
                            f"Ta={result.Ta:.1f} "
                            f"Ctr={result.center_temp:.1f} "
                            f"Max={result.max_temp:.1f}"
                        )

                elif isinstance(frame, MLX90640LegacyFrame):
                    self._res_q.put(frame)
                    logger.info(
                        f"Legacy MLX90640 F{frame.frame_id} "
                        f"Min={frame.min_c:.1f} Avg={frame.avg_c:.1f} "
                        f"Ctr={frame.center_c:.1f} Max={frame.max_c:.1f} "
                        f"Ta={frame.ta_c:.1f}"
                    )

                elif isinstance(frame, SMHFrame):
                    # SMH frames are already calibrated on the MCU as uint16 values.
                    try:
                        pixels = frame.pixels
                        # Debug: basic payload inspection
                        logger.debug(
                            f"SMH raw frame={frame.frame_id} size={pixels.size} dtype={pixels.dtype} "
                            f"min={int(pixels.min())} max={int(pixels.max())} "
                            f"first8={pixels.ravel()[:8].tolist()}"
                        )

                        # SMH-01B01 temperature output is signed 2's-complement
                        # and equals 10x Celsius according to the datasheet.
                        # Do not auto-scale here; high-temperature frames can
                        # legitimately exceed 120 C.
                        chosen = 10.0
                        temps = pixels.astype("float32") / chosen
                        saturated = pixels == -10000
                        if np.any(saturated):
                            temps[saturated] = np.nan
                            logger.warning(
                                "SMH frame=%d has %d saturated pixels (-10000 / 0xD8F0)",
                                frame.frame_id,
                                int(np.count_nonzero(saturated)),
                            )

                        # Replace payload with temps in °C (float32)
                        frame.pixels = temps

                        # Final debug after conversion
                        try:
                            tmin = float(np.nanmin(temps))
                            tmax = float(np.nanmax(temps))
                        except Exception:
                            tmin = float('nan'); tmax = float('nan')

                        logger.debug(
                            f"SMH frame={frame.frame_id} scale={chosen} "
                            f"min={tmin:.2f} max={tmax:.2f} mean={float(np.nanmean(temps)):.2f} "
                            f"shape={temps.shape}"
                        )
                        frame.smh_max = float(np.nanmax(temps))
                        log_smh_matrix_diagnostics(frame.frame_id, temps)

                    except Exception:
                        logger.exception("Error processing SMH frame")

                    # Emit processed SMH frame
                    if getattr(frame, "smh_max", None) is None:
                        smh_arr = np.asarray(frame.pixels)
                        frame.smh_max = (
                            float(np.nanmax(smh_arr) / 10.0)
                            if smh_arr.dtype.kind in ("u", "i")
                            else float(np.nanmax(smh_arr))
                        )
                    frame.smh01b01_calib = calibrate(
                        "smh01b01",
                        frame.smh_max,
                        self._d6t_distance_cm,
                        self._calib_direction,
                    )
                    logger.debug(
                        "[DASH CHECK] receiver->queue sensor=smh01b01 raw=%.2f calib=%.2f attr=smh01b01_calib",
                        frame.smh_max,
                        frame.smh01b01_calib,
                    )
                    self._res_q.put(frame)
                    if self._csv:
                        self._csv.log_smh(frame)

                elif isinstance(frame, D6TFrame):
                    frame = apply_d6t_calibration(
                        frame,
                        self._d6t_distance_cm,
                        self._d6t_manual_calib,
                    )
                    log_d6t_rx_debug(frame, self._d6t_distance_cm)
                    is_valid_d6t_frame(frame)
                    reasons = d6t_validation_reasons(frame, self._previous_valid_d6t)
                    if reasons:
                        frame.d6t_valid = False
                        frame.d6t_invalid_reasons = reasons
                        logger.warning(
                            "[D6T CHART SKIP] raw=%.2f calib=%.2f valid=False reason=%s "
                            "profile=%s raw_max_x10=%d calib_x10=%d firmware_raw_max_x10=%d "
                            "pos=(%d,%d) pixels_raw_x10=%s",
                            frame.max_celsius,
                            frame.calib_celsius,
                            ",".join(reasons),
                            d6t_profile_name(self._d6t_distance_cm),
                            frame.max_raw,
                            int(frame.calib_x10),
                            int(getattr(frame, "firmware_raw_max_x10", 0)),
                            int(frame.max_x),
                            int(frame.max_y),
                            np.asarray(frame.pixels_raw, dtype=np.uint16).tolist(),
                        )
                        continue

                    frame.d6t_valid = True
                    frame.d6t_invalid_reasons = []
                    logger.info(
                        "[D6T CHART UPDATE] raw=%.2f calib=%.2f valid=True profile=%s",
                        frame.max_celsius,
                        frame.calib_celsius,
                        d6t_profile_name(self._d6t_distance_cm),
                    )
                    self._previous_valid_d6t = frame.calib_celsius
                    logger.debug(
                        "[DASH CHECK] receiver->queue sensor=d6t raw=%.2f calib=%.2f attr=calib_celsius",
                        frame.max_celsius,
                        frame.calib_celsius,
                    )
                    self._res_q.put(frame)
                    if self._csv:
                        self._csv.log_d6t(frame)

                elif isinstance(frame, D6TStatusFrame):
                    logger.info(
                        "[D6T STATUS] attempts=%d success=%d fail=%d pec_fail=%d "
                        "request_len_fail=%d endtx_fail=%d",
                        frame.read_attempt_count,
                        frame.read_success_count,
                        frame.read_fail_count,
                        frame.pec_fail_count,
                        frame.request_len_fail_count,
                        frame.endtx_fail_count,
                    )

            except Exception as e:
                logger.error(f"Processing error: {e}", exc_info=True)

    def stop(self):
        self._running = False


# ── Headless mode (no GUI) ────────────────────────────────────

def headless_loop(result_queue: queue.Queue):
    """Print stats to console when --no-gui is set."""
    while True:
        try:
            item = result_queue.get(timeout=2.0)
            from thermography import ThermalResult
            if isinstance(item, ThermalResult):
                print(
                    f"[MLX640] F{item.frame_id:5d}  "
                    f"Ta={item.Ta:5.1f}°C  "
                    f"Min={item.min_temp:5.1f}  "
                    f"Avg={item.avg_temp:5.1f}  "
                    f"Ctr={item.center_temp:5.1f}  "
                    f"Max={item.max_temp:5.1f}  "
                    f"Hot@{item.hotspot_idx}"
                )
            elif isinstance(item, SMHFrame):
                avg = float(np.nanmean(item.pixels))
                mx = float(np.nanmax(item.pixels))
                print(f"[SMH614] F{item.frame_id:5d}  Avg={avg:.1f}°C Max={mx:.1f}°C")
            elif isinstance(item, D6TFrame):
                print(f"[D6T] F{item.frame_id:5d}  "
                      f"RawMax={item.max_celsius:.1f}C  "
                      f"CalibMax={item.calib_celsius:.1f}C  "
                      f"Max@({item.max_x},{item.max_y})")
        except queue.Empty:
            pass


# ── Main ──────────────────────────────────────────────────────

def _csv_label_value(value: float) -> str:
    return f"{float(value):g}"


def calibration_direction_from_range(start_c: float | None, end_c: float | None) -> str | None:
    if start_c is None or end_c is None:
        return None
    if start_c < end_c:
        return "up"
    if start_c > end_c:
        return "down"
    return None


class NTCReference:
    def latest(self, timestamp_s: float | None = None) -> float | None:
        return None

    def close(self):
        pass


class NTCReferenceCSV(NTCReference):
    def __init__(self, path: str):
        self._path = path
        self._samples: list[tuple[float, float]] = []

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"timestamp"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"NTC reference CSV missing columns: {sorted(missing)}")
            temp_field = "reference_temp" if "reference_temp" in (reader.fieldnames or []) else "ntc_ref_c"
            if temp_field not in (reader.fieldnames or []):
                raise ValueError("NTC reference CSV missing column: reference_temp or ntc_ref_c")

            for row_num, row in enumerate(reader, start=2):
                try:
                    ts = parse_iso_timestamp(row["timestamp"])
                    temp = float(row[temp_field])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid NTC reference row {row_num}: {row}") from exc
                if np.isfinite(temp):
                    self._samples.append((ts, temp))

        self._samples.sort(key=lambda item: item[0])
        logger.info("[NTC] Loaded %d reference samples from %s", len(self._samples), path)

    def latest(self, timestamp_s: float | None = None) -> float | None:
        if not self._samples:
            return None
        if timestamp_s is None:
            return self._samples[-1][1]

        best_ts, best_temp = min(self._samples, key=lambda item: abs(item[0] - timestamp_s))
        logger.debug(
            "[NTC] CSV nearest sample dt=%.3fs temp=%.2fC",
            timestamp_s - best_ts,
            best_temp,
        )
        return best_temp


class GDM8342NTCReader(threading.Thread, NTCReference):
    def __init__(
        self,
        port: str = "COM8",
        baud: int = 115200,
        query: str = "READ?",
        interval_s: float = 0.5,
    ):
        threading.Thread.__init__(self, daemon=True, name="GDM8342NTC")
        self._port = port
        self._baud = int(baud)
        self._query = query
        self._interval_s = float(interval_s)
        self._lock = threading.Lock()
        self._running = True
        self._ser = None
        self._latest: tuple[float, float] | None = None

    def run(self):
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=1.0,
                write_timeout=1.0,
            )
            logger.info("[GDM] connected %s @ %d", self._port, self._baud)
        except serial.SerialException as exc:
            logger.warning("[GDM] cannot open %s @ %d: %s", self._port, self._baud, exc)
            self._running = False
            return

        query = self._query.strip()
        while self._running:
            try:
                if query:
                    self._ser.reset_input_buffer()
                    self._ser.write((query + "\r\n").encode("ascii"))
                    self._ser.flush()
                line = self._ser.readline().decode("ascii", errors="ignore").strip()
                logger.info("[GDM] READ? -> %r", line)
                if not line:
                    logger.warning("[GDM] empty response")
                    self._clear_latest()
                    time.sleep(self._interval_s)
                    continue

                value = self._parse_temperature(line)
                if value is None:
                    logger.warning("[GDM] could not parse response: %r", line)
                    self._clear_latest()
                    time.sleep(self._interval_s)
                    continue

                with self._lock:
                    self._latest = (time.time(), value)
                logger.info("[GDM] reference_temp=%.2f", value)

            except serial.SerialException as exc:
                logger.warning("[GDM] serial error: %s", exc)
                self._clear_latest()
                self._running = False
            except Exception:
                logger.warning("[GDM] read error", exc_info=True)
                self._clear_latest()

            time.sleep(self._interval_s)

    @staticmethod
    def _parse_temperature(line: str) -> float | None:
        token = line.split(",", 1)[0].strip()
        if not token:
            return None
        try:
            value = float(token)
        except ValueError:
            return None
        if np.isfinite(value):
            return value
        return None

    def latest(self, timestamp_s: float | None = None) -> float | None:
        with self._lock:
            return self._latest[1] if self._latest else None

    def _clear_latest(self):
        with self._lock:
            self._latest = None

    def close(self):
        self._running = False
        if self._ser:
            self._ser.close()


class CalibrationCSVLogger:
    FIELDS = [
        "timestamp",
        "reference_temp",
        "mlx90640_max",
        "mlx90640_calib",
        "smh01b01_max",
        "smh01b01_calib",
        "d6t_raw",
        "d6t_calib",
    ]

    def __init__(
        self,
        path: str,
        ntc_ref: NTCReference,
        append: bool = False,
        distance_cm: int | None = None,
        direction: str | None = None,
    ):
        self._path = path
        self._ntc_ref = ntc_ref
        self._append = bool(append)
        self._distance_cm = distance_cm
        self._direction = direction
        self._lock = threading.Lock()
        self._file = None
        self._writer = None
        self._latest_mlx640 = None
        self._latest_smh = None
        self._latest_d6t = None
        self._last_written_ids = None
        self._last_written_d6t_id = None

    def open(self):
        import os

        mode = "a" if self._append else "w"
        needs_header = True
        if self._append and os.path.exists(self._path) and os.path.getsize(self._path) > 0:
            needs_header = False
        self._file = open(self._path, mode, newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDS)
        if needs_header:
            self._writer.writeheader()
        self._file.flush()
        logger.info("[CALIB LOG] CSV logging to %s append=%s", self._path, self._append)

    def log_mlx640(self, result):
        from thermography import ThermalResult
        if not isinstance(result, ThermalResult):
            return
        with self._lock:
            self._latest_mlx640 = {
                "frame_id": int(result.frame_id),
                "max": float(result.max_temp),
            }
            self._try_log_combined_locked()

    def log_smh(self, frame):
        from protocol import SMHFrame
        if not isinstance(frame, SMHFrame):
            return
        arr = np.asarray(frame.pixels)
        max_v = float(np.nanmax(arr) / 10.0) if arr.dtype.kind in ("u", "i") else float(np.nanmax(arr))
        with self._lock:
            self._latest_smh = {
                "frame_id": int(frame.frame_id),
                "max": max_v,
            }
            self._try_log_combined_locked()

    def log_d6t(self, frame):
        from protocol import D6TFrame
        if not isinstance(frame, D6TFrame):
            return
        with self._lock:
            self._latest_d6t = {
                "frame_id": int(frame.frame_id),
                "raw": float(frame.max_celsius),
                "calib": float(frame.calib_celsius),
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

        timestamp_s = time.time()
        ntc_ref_c = self._ntc_ref.latest(timestamp_s)
        if ntc_ref_c is None or not np.isfinite(ntc_ref_c):
            logger.warning("[CALIB LOG] NTC reference unavailable, row skipped")
            return

        mlx = self._latest_mlx640["max"]
        smh = self._latest_smh["max"]
        d6t_raw = self._latest_d6t["raw"]
        mlx_calib = calibrate("mlx90640", mlx, self._distance_cm, self._direction)
        smh_calib = calibrate("smh01b01", smh, self._distance_cm, self._direction)
        d6t_calib = calibrate("d6t", d6t_raw, self._distance_cm, self._direction)
        self._writer.writerow({
            "timestamp": iso_now_ms(),
            "reference_temp": f"{ntc_ref_c:.2f}",
            "mlx90640_max": f"{mlx:.2f}",
            "mlx90640_calib": f"{mlx_calib:.2f}",
            "smh01b01_max": f"{smh:.2f}",
            "smh01b01_calib": f"{smh_calib:.2f}",
            "d6t_raw": f"{d6t_raw:.2f}",
            "d6t_calib": f"{d6t_calib:.2f}",
        })
        self._file.flush()
        self._last_written_ids = ids
        self._last_written_d6t_id = self._latest_d6t["frame_id"]
        logger.info(
            "[CALIB] sensor=mlx90640 raw=%.2f calib=%.2f",
            mlx,
            mlx_calib,
        )
        logger.info(
            "[CALIB] sensor=smh01b01 raw=%.2f calib=%.2f",
            smh,
            smh_calib,
        )
        logger.info(
            "[CALIB] sensor=d6t raw=%.2f calib=%.2f",
            d6t_raw,
            d6t_calib,
        )
        logger.info(
            "[CALIB LOG] reference_temp=%.2f mlx=%.2f mlx_calib=%.2f "
            "smh=%.2f smh_calib=%.2f d6t_raw=%.2f d6t_calib=%.2f",
            ntc_ref_c,
            mlx,
            mlx_calib,
            smh,
            smh_calib,
            d6t_raw,
            d6t_calib,
        )

    def close(self):
        if self._file:
            self._file.close()


def main():
    ap = argparse.ArgumentParser(description="Thermal Node Receiver")
    ap.add_argument("--port",   required=True, help="Serial port (COM7, /dev/ttyUSB0)")
    ap.add_argument("--baud",   type=int, default=BAUD_DEFAULT)
    ap.add_argument("--eeprom", default=None,
                    help="EEPROM .bin file (832 words, little-endian uint16). "
                         "If omitted, temperature conversion is skipped.")
    ap.add_argument("--csv",    default=None, help="CSV output path")
    ap.add_argument(
        "--append-csv",
        "--append",
        dest="append_csv",
        action="store_true",
        help="Append CSV rows instead of overwriting the output file.",
    )
    ap.add_argument(
        "--distance-cm",
        type=int,
        choices=(5, 10, 15, 20, 25, 30, 35),
        default=None,
        help="Manual calibration distance in cm for CSV logging.",
    )
    ap.add_argument(
        "--d6t-calib-csv",
        default=None,
        help=(
            "Manual D6T calibration CSV with columns "
            "distance_cm,d6t_raw,reference_temp. Overrides builtin calibration "
            "for matching --distance-cm."
        ),
    )
    ap.add_argument(
        "--enable-gdm",
        action="store_true",
        help="Enable GDM-8342 reference temperature reads over Virtual COM Port.",
    )
    ap.add_argument(
        "--gdm-port",
        default="COM8",
        help="Serial port for GDM-8342 reference, e.g. COM8.",
    )
    ap.add_argument(
        "--gdm-baud",
        type=int,
        default=115200,
        help="Baud rate for GDM-8342 reference serial port.",
    )
    ap.add_argument(
        "--ntc-ref-port",
        default=None,
        help="Legacy alias for --gdm-port. Also enables GDM reference reads.",
    )
    ap.add_argument(
        "--ntc-ref-baud",
        type=int,
        default=None,
        help="Legacy alias for --gdm-baud.",
    )
    ap.add_argument(
        "--ntc-ref-query",
        default="READ?",
        help="SCPI query sent to GDM-8342. Use empty string to only read streaming lines.",
    )
    ap.add_argument(
        "--ntc-ref-csv",
        default=None,
        help=(
            "Reference CSV with columns timestamp,reference_temp "
            "(legacy ntc_ref_c is also accepted). Receiver uses nearest timestamp."
        ),
    )
    ap.add_argument(
        "--temp-min",
        type=float,
        default=0.0,
        help="Manual calibration temperature range minimum in deg C for CSV logging.",
    )
    ap.add_argument(
        "--temp-max",
        type=float,
        default=300.0,
        help="Manual calibration temperature range maximum in deg C for CSV logging.",
    )
    ap.add_argument(
        "--range-start-c",
        type=float,
        default=None,
        help="Manual test start temperature in deg C for CSV logging and automatic filename.",
    )
    ap.add_argument(
        "--range-end-c",
        type=float,
        default=None,
        help="Manual test end temperature in deg C for CSV logging and automatic filename.",
    )
    ap.add_argument("--no-gui", action="store_true", help="Headless mode")
    ap.add_argument("--debug",  action="store_true")
    ap.add_argument(
        "--mlx90640-correction-enable",
        action="store_true",
        help="Enable application-level MLX90640 offset correction after Melexis To calculation.",
    )
    ap.add_argument(
        "--mlx90640-offset-c",
        type=float,
        default=0.0,
        help="Application-level MLX90640 additive offset in deg C. Used only with --mlx90640-correction-enable.",
    )
    ap.add_argument(
        "--mlx90640-emissivity",
        type=float,
        default=1.0,
        help="MLX90640 emissivity used by Melexis CalculateTo. Default 1.0; use measured material emissivity when known.",
    )
    ap.add_argument(
        "--mlx90640-tr-offset-c",
        type=float,
        default=0.0,
        help="Reflected temperature offset: Tr = Ta + this value. Default 0.0.",
    )
    args = ap.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        d6t_manual_calib = load_d6t_manual_calibration(args.d6t_calib_csv)
    except (OSError, ValueError) as exc:
        logger.error("Could not load D6T calibration CSV: %s", exc)
        sys.exit(1)

    ntc_ref = None
    gdm_enabled = args.enable_gdm or bool(args.ntc_ref_port)
    gdm_port = args.ntc_ref_port or args.gdm_port
    gdm_baud = args.ntc_ref_baud if args.ntc_ref_baud is not None else args.gdm_baud
    if gdm_enabled and args.ntc_ref_csv:
        logger.error("Use only one reference source: --enable-gdm/--ntc-ref-port or --ntc-ref-csv")
        sys.exit(1)
    if args.ntc_ref_csv:
        try:
            ntc_ref = NTCReferenceCSV(args.ntc_ref_csv)
        except (OSError, ValueError) as exc:
            logger.error("Could not load NTC reference CSV: %s", exc)
            sys.exit(1)
    elif gdm_enabled:
        ntc_ref = GDM8342NTCReader(
            gdm_port,
            baud=gdm_baud,
            query=args.ntc_ref_query,
        )
        ntc_ref.start()

    # Temporarily enable detailed debug logging for thermography processing
    logging.getLogger('thermography').setLevel(logging.DEBUG)

    # ── Setup processor ───────────────────────────────────────
    processor = MLX90640Processor(
        emissivity=args.mlx90640_emissivity,
        app_correction=ApplicationCorrectionConfig(
            enabled=args.mlx90640_correction_enable,
            offset_c=args.mlx90640_offset_c,
        )
    )
    processor.DEFAULT_TR_OFFSET = args.mlx90640_tr_offset_c
    if args.eeprom:
        if not processor.load_eeprom_from_file(args.eeprom):
            logger.error("Could not load EEPROM. Temperatures will not be computed.")
    else:
        logger.warning(
            "No --eeprom provided. Raw frames will be received but not converted "
            "to temperatures. Run with --eeprom <file> for full processing.\n"
            "Dump EEPROM using the ATmega2560 EEPROM dump firmware and save it locally."
        )

    # ── Setup CSV logger ──────────────────────────────────────
    csv_logger = None
    range_label = ""
    if args.range_start_c is not None and args.range_end_c is not None:
        range_label = f"{_csv_label_value(args.range_start_c)}_to_{_csv_label_value(args.range_end_c)}"
    calib_direction = calibration_direction_from_range(args.range_start_c, args.range_end_c)

    csv_path = args.csv
    if csv_path is None and args.distance_cm is not None and range_label:
        csv_path = f"log_{args.distance_cm}cm_{range_label}.csv"
        logger.info("Auto CSV path selected: %s", csv_path)

    if csv_path:
        if args.append_csv:
            logger.debug("CSV append enabled")
        logger.info(
            "CSV config: append=%s path=%s",
            args.append_csv,
            csv_path,
        )
        if ntc_ref is not None:
            csv_logger = CalibrationCSVLogger(
                csv_path,
                ntc_ref,
                append=args.append_csv,
                distance_cm=args.distance_cm,
                direction=calib_direction,
            )
        else:
            csv_logger = CSVLogger(
                csv_path,
                append=args.append_csv,
            )
        csv_logger.open()
    elif ntc_ref is not None:
        logger.warning("[CALIB LOG] NTC reference enabled but no --csv output path was provided")

    if args.distance_cm is None:
        logger.info("[D6T] No --distance-cm provided, using raw value")
    elif args.distance_cm in d6t_manual_calib:
        logger.info("[D6T] Manual CSV calibration profile: CM%d", args.distance_cm)
    elif args.distance_cm in D6T_BUILTIN_CALIB_PROFILES:
        logger.info("[D6T] Builtin calibration profile: CM%d", args.distance_cm)
    elif args.distance_cm in D6T_DISABLED_BUILTIN_CALIB_PROFILES:
        logger.warning(
            "[D6T] Builtin profile CM%d is disabled, using raw value unless --d6t-calib-csv provides it",
            args.distance_cm,
        )
    else:
        logger.warning("[D6T] No calibration profile for %scm, using raw value", args.distance_cm)

    # ── Open serial port ──────────────────────────────────────
    try:
        ser = serial.Serial(
            port=args.port,
            baudrate=args.baud,
            timeout=0.05,
            write_timeout=1.0,
        )
        logger.info(f"Opened {args.port} @ {args.baud} baud")
    except serial.SerialException as e:
        logger.error(f"Cannot open serial port: {e}")
        sys.exit(1)

    # ── Queues ────────────────────────────────────────────────
    raw_queue    = queue.Queue(maxsize=32)
    result_queue = queue.Queue(maxsize=32)

    # ── Start threads ─────────────────────────────────────────
    reader = SerialReader(ser, raw_queue)
    worker = ProcessingThread(
        raw_queue,
        result_queue,
        processor,
        csv_logger,
        args.distance_cm,
        d6t_manual_calib,
        calib_direction,
    )
    reader.start()
    worker.start()

    logger.info("Waiting for sensor data...")

    try:
        if args.no_gui:
            headless_loop(result_queue)
        else:
            viz = ThermalVisualizer(result_queue, reference=ntc_ref)
            viz.start()   # blocks until window closed

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        reader.stop()
        worker.stop()
        ser.close()
        if csv_logger:
            csv_logger.close()
        if ntc_ref:
            ntc_ref.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
