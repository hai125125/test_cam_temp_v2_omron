"""
protocol.py — Unified binary packet parser for Thermal Node

This parser decodes the new unified transport protocol:
  Header:      0x55 0xAA
  Type:        1 byte
  Frame ID:    2 bytes little-endian
  Length:      2 bytes little-endian
  Payload:     variable bytes
  CRC8:        1 byte (covers type+frame_id+length+payload)

Sensor payload layouts:
  TYPE 0x01 (MLX90640): 768 int16 values (24×32 row-major)
  TYPE 0x02 (SMH-01B01): 64 int16 values, unit = 0.1 deg C
  TYPE 0x03 (D6T): 16 uint16 pixels (0.1 C), raw max x10 legacy field, max_x uint8, max_y uint8

Example:
    parser = ThermalNodeParser()
    frames = parser.feed(serial.read(1024))
    for frame in frames:
        if isinstance(frame, MLX640Frame):
            matrix = frame.pixels_raw.reshape(ROWS, COLS)

Legacy ASCII packets are still recognized for debug fallback.
"""

import struct
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# ── Protocol constants ────────────────────────────────────────
HEADER      = bytes([0x55, 0xAA])
TYPE_MLX90640 = 0x01
TYPE_SMH      = 0x02
TYPE_D6T      = 0x03
TYPE_D6T_STATUS = 0x04
PIXEL_COUNT = 768
ROWS, COLS  = 24, 32

FLOAT_RE = r"[-+]?\d+(?:\.\d+)?"
MLX90640_LEGACY_RE = re.compile(
    rf"\[MLX90640\].*?Min\s*:\s*(?P<min>{FLOAT_RE})\s*C.*?"
    rf"Avg\s*:\s*(?P<avg>{FLOAT_RE})\s*C.*?"
    rf"Ctr\s*:\s*(?P<ctr>{FLOAT_RE})\s*C.*?"
    rf"Max\s*:\s*(?P<max>{FLOAT_RE})\s*C.*?"
    rf"Ta\s*:\s*(?P<ta>{FLOAT_RE})\s*C",
    re.IGNORECASE,
)
SMH_LEGACY_RE = re.compile(
    rf"\[SMH01B01\].*?Min\s*:\s*(?P<min>{FLOAT_RE})\s*C.*?"
    rf"Avg\s*:\s*(?P<avg>{FLOAT_RE})\s*C.*?"
    rf"Ctr\s*:\s*(?P<ctr>{FLOAT_RE})\s*C.*?"
    rf"Max\s*:\s*(?P<max>{FLOAT_RE})\s*C",
    re.IGNORECASE,
)

@dataclass
class MLX640Frame:
    frame_id: int
    pixels_raw: np.ndarray   # shape (768,) int16
    crc_ok: bool = True
    subpage: int = 0
    status_raw: int = 0
    ptat_art_raw: int = 0
    ptat_raw: int = 0
    vdd_raw: int = 0
    gain_raw: int = 0
    cp_sp0_raw: int = 0
    cp_sp1_raw: int = 0

    @property
    def matrix(self) -> np.ndarray:
        return self.pixels_raw.reshape(ROWS, COLS)


@dataclass
class SMHFrame:
    frame_id: int
    pixels:   np.ndarray   # shape (64,) int16 raw or float32 deg C after receiver processing


@dataclass
class D6TFrame:
    frame_id: int
    pixels_raw: np.ndarray
    calib_x10: int
    max_x: int
    max_y: int
    payload: bytes = b""
    firmware_raw_max_x10: int = 0

    @property
    def pixels_celsius(self) -> np.ndarray:
        return self.pixels_raw.astype(np.float32) / 10.0

    @property
    def matrix_celsius(self) -> np.ndarray:
        return self.pixels_celsius.reshape(4, 4)

    @property
    def max_raw(self) -> int:
        return int(np.nanmax(self.pixels_raw)) if self.pixels_raw.size else 0

    @property
    def max_celsius(self) -> float:
        return self.max_raw / 10.0

    @property
    def calib_celsius(self) -> float:
        return self.calib_x10 / 10.0


@dataclass
class D6TStatusFrame:
    frame_id: int
    read_attempt_count: int
    read_success_count: int
    read_fail_count: int
    pec_fail_count: int
    request_len_fail_count: int
    endtx_fail_count: int


@dataclass
class MLX90640LegacyFrame:
    frame_id: int
    min_c: float
    avg_c: float
    center_c: float
    max_c: float
    ta_c: float


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) if (crc & 0x80) else (crc << 1)
            crc &= 0xFF
    return crc


class ThermalNodeParser:
    """
    Stateful parser for the unified binary Thermal Node stream.
    """

    MAX_BUFFER = 8192

    def __init__(self):
        self._buf = bytearray()
        self._frames_parsed = 0
        self._crc_errors = 0
        self._sync_misses = 0
        self._legacy_mlx640_id = 0
        self._legacy_smh_id = 0

    def feed(self, data: bytes) -> list:
        self._buf.extend(data)
        results = []

        while True:
            idx = self._buf.find(HEADER)
            ascii_idx = self._find_ascii_packet()

            if idx == -1 and ascii_idx == -1:
                self._buf = self._buf[-1:]
                break

            if idx == -1:
                idx = len(self._buf) + 1
            if ascii_idx == -1:
                ascii_idx = len(self._buf) + 1

            if idx < ascii_idx:
                if idx > 0:
                    self._sync_misses += idx
                    logger.debug(f"Skipped {idx} bytes before HEADER")
                    self._buf = self._buf[idx:]

                if len(self._buf) < 7:
                    break

                payload_length = struct.unpack_from("<H", self._buf, 5)[0]
                packet_length = 2 + 1 + 2 + 2 + payload_length + 1

                if len(self._buf) < packet_length:
                    break

                frame = self._parse_binary(packet_length)
                if frame is not None:
                    results.append(frame)
                    self._frames_parsed += 1
                else:
                    self._buf = self._buf[2:]
            else:
                frame = self._parse_ascii_at(ascii_idx)
                if frame is not None:
                    results.append(frame)

        if len(self._buf) > self.MAX_BUFFER:
            logger.warning(f"Buffer overflow ({len(self._buf)}B), resetting")
            self._buf = bytearray()

        return results

    @property
    def stats(self) -> dict:
        return {
            "frames_parsed": self._frames_parsed,
            "crc_errors":    self._crc_errors,
            "sync_misses":   self._sync_misses,
            "buffer_len":    len(self._buf),
        }

    def _parse_binary(self, packet_length: int) -> Optional[object]:
        if self._buf[:2] != HEADER:
            return None

        if len(self._buf) < packet_length:
            return None

        packet_type = self._buf[2]
        frame_id = struct.unpack_from("<H", self._buf, 3)[0]
        payload_length = struct.unpack_from("<H", self._buf, 5)[0]
        payload_start = 7
        payload_end = payload_start + payload_length
        payload = bytes(self._buf[payload_start:payload_end])
        crc_received = self._buf[payload_end]

        crc_data = bytes(self._buf[2:payload_end])
        crc_ok = crc8(crc_data) == crc_received
        # Log basic packet detection
        logger.debug(f"Packet detected: type=0x{packet_type:02X} frame_id={frame_id} payload_len={payload_length} crc_ok={crc_ok}")

        if not crc_ok:
            self._crc_errors += 1
            logger.warning(
                f"CRC error: type=0x{packet_type:02X} id={frame_id} expected=0x{crc8(crc_data):02X}, got=0x{crc_received:02X}"
            )
            # advance past sync to attempt resync
            self._buf = self._buf[2:]
            return None

        if packet_type == TYPE_MLX90640:
            logger.debug(
                f"MLX RAW frame={frame_id} "
                f"payload_len={payload_length} "
                f"first8={list(np.frombuffer(payload[:16], dtype='<i2'))}"
            )
            pixels_dbg = np.frombuffer(payload[-PIXEL_COUNT*2:], dtype="<i2")
            logger.debug(f"MLX RAW pixels min={pixels_dbg.min()} max={pixels_dbg.max()}")
            # Support two MLX90640 payload variants:
            #  A) Simple: pixels only (768 * int16)
            #  B) Extended: metadata header + pixels
            #
            # Firmware writes:
            #   subpage, status, ptat_art, ptat, vdd, gain, cp_sp0, cp_sp1
            # Keep this order exact. Swapping vdd/ptat_art breaks Ta/Vdd.
            METADATA_LEN = 15
            if payload_length == PIXEL_COUNT * 2:
                pixels_raw = np.frombuffer(payload, dtype="<i2").copy()
                logger.info(f"MLX90640 frame parsed (simple): frame_id={frame_id} pixels={pixels_raw.size}")
                frame = MLX640Frame(frame_id=frame_id, pixels_raw=pixels_raw, crc_ok=crc_ok)
            elif payload_length == PIXEL_COUNT * 2 + METADATA_LEN:
                # parse metadata then pixel data
                try:
                    meta = struct.unpack_from('<BHhhhhhh', payload, 0)
                    subpage = int(meta[0])
                    status_raw = int(meta[1])
                    ptat_art_raw, ptat_raw, vdd_raw, gain_raw, cp_sp0_raw, cp_sp1_raw = map(int, meta[2:])
                    pix_bytes = payload[METADATA_LEN:]
                    pixels_raw = np.frombuffer(pix_bytes, dtype="<i2").copy()
                    logger.info(
                        f"MLX90640 frame parsed (extended): id={frame_id} pixels={pixels_raw.size} "
                        f"subpage={subpage} vdd={vdd_raw} ptat={ptat_raw} gain={gain_raw}"
                    )
                    logger.debug(
                        "MLX90640 metadata signed decode: "
                        f"status=0x{status_raw:04X} ptat_art={ptat_art_raw} ptat={ptat_raw} "
                        f"vdd={vdd_raw} gain={gain_raw} cp0={cp_sp0_raw} cp1={cp_sp1_raw}"
                    )
                    frame = MLX640Frame(
                        frame_id=frame_id,
                        pixels_raw=pixels_raw,
                        crc_ok=crc_ok,
                        subpage=subpage,
                        status_raw=status_raw,
                        ptat_art_raw=ptat_art_raw,
                        ptat_raw=ptat_raw,
                        vdd_raw=vdd_raw,
                        gain_raw=gain_raw,
                        cp_sp0_raw=cp_sp0_raw,
                        cp_sp1_raw=cp_sp1_raw,
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse extended MLX payload: {e}")
                    self._buf = self._buf[packet_length:]
                    return None
            else:
                logger.warning(f"Invalid MLX90640 payload size: got={payload_length} expected={PIXEL_COUNT*2} or {PIXEL_COUNT*2 + METADATA_LEN}")
                self._buf = self._buf[packet_length:]
                return None
        elif packet_type == TYPE_SMH:
            expected = 64 * 2
            if payload_length != expected:
                logger.warning(f"Invalid SMH payload size: got={payload_length} expected={expected} type=0x{packet_type:02X} id={frame_id}")
                self._buf = self._buf[packet_length:]
                return None
            pixels = np.frombuffer(payload, dtype="<i2").copy()
            try:
                logger.debug(
                    f"SMH binary parse: id={frame_id} payload_len={payload_length} "
                    f"count={pixels.size} dtype={pixels.dtype} min={int(pixels.min())} "
                    f"max={int(pixels.max())} first8={pixels.ravel()[:8].tolist()}"
                )
            except Exception:
                logger.debug("SMH binary parse: could not compute stats")
            logger.info(f"SMH frame parsed: pixels={pixels.size} frame_id={frame_id}")
            frame = SMHFrame(frame_id=frame_id, pixels=pixels)
        elif packet_type == TYPE_D6T:
            expected = 16 * 2 + 4
            if payload_length != expected:
                logger.warning("Invalid D6T payload size")
                self._buf = self._buf[packet_length:]
                return None
            logger.debug("[D6T RX] payload_len=%d", payload_length)
            logger.debug("[D6T RX] payload_hex=%s", payload.hex(" "))
            pixels_raw = np.frombuffer(payload[:32], dtype="<u2").copy()
            raw_max_field_x10, max_x, max_y = struct.unpack_from("<HBB", payload, 32)
            logger.debug(
                "D6T parse: id=%d pixels=%d raw_max=%d raw=%.2fC raw_max_field=%.2fC max=(%d,%d)",
                frame_id,
                pixels_raw.size,
                int(np.nanmax(pixels_raw)),
                float(np.nanmax(pixels_raw)) / 10.0,
                raw_max_field_x10 / 10.0,
                max_x,
                max_y,
            )
            frame = D6TFrame(
                frame_id=frame_id,
                pixels_raw=pixels_raw,
                calib_x10=raw_max_field_x10,
                max_x=max_x,
                max_y=max_y,
                payload=payload,
                firmware_raw_max_x10=raw_max_field_x10,
            )
        elif packet_type == TYPE_D6T_STATUS:
            expected = 6 * 4
            if payload_length != expected:
                logger.warning(
                    "Invalid D6T status payload size: got=%d expected=%d",
                    payload_length,
                    expected,
                )
                self._buf = self._buf[packet_length:]
                return None
            counters = struct.unpack_from("<6I", payload, 0)
            frame = D6TStatusFrame(
                frame_id=frame_id,
                read_attempt_count=counters[0],
                read_success_count=counters[1],
                read_fail_count=counters[2],
                pec_fail_count=counters[3],
                request_len_fail_count=counters[4],
                endtx_fail_count=counters[5],
            )
            logger.debug(
                "[D6T STATUS] attempts=%d success=%d fail=%d pec_fail=%d "
                "request_len_fail=%d endtx_fail=%d",
                frame.read_attempt_count,
                frame.read_success_count,
                frame.read_fail_count,
                frame.pec_fail_count,
                frame.request_len_fail_count,
                frame.endtx_fail_count,
            )
        else:
            logger.warning(f"Unknown packet type: 0x{packet_type:02X} frame_id={frame_id} payload_len={payload_length}")
            self._buf = self._buf[packet_length:]
            return None

        self._buf = self._buf[packet_length:]
        return frame

    def _find_ascii_packet(self) -> int:
        for marker in [b"SMH_FRAME", b"[SMH01B01]", b"[MLX90640]"]:
            idx = self._buf.find(marker)
            if idx != -1:
                return idx
        return -1

    def _parse_ascii_at(self, start: int) -> Optional[object]:
        end = self._buf.find(b"\n", start)
        if end == -1:
            return None

        line = self._buf[start: end + 1].decode("ascii", errors="replace").strip()
        self._buf = self._buf[end + 1:]

        if line.startswith("SMH_FRAME"):
            return self._parse_smh(line)
        elif line.startswith("[SMH01B01]"):
            return self._parse_smh_legacy(line)
        elif line.startswith("[MLX90640]"):
            return self._parse_mlx90640_legacy(line)
        return None

    def _parse_smh(self, line: str) -> Optional[SMHFrame]:
        try:
            parts = dict(p.split(":", 1) for p in line.split() if ":" in p)
            frame_id = int(parts["FRAME_ID"])
            pixels = np.array(list(map(int, parts["PIXELS"].split(","))), dtype=np.uint16)
            return SMHFrame(frame_id=frame_id, pixels=pixels)
        except Exception as e:
            logger.warning(f"SMH parse error: {e}")
            return None

    def _parse_smh_legacy(self, line: str) -> Optional[SMHFrame]:
        try:
            m = SMH_LEGACY_RE.search(line)
            if not m:
                return None
            frame_id = self._legacy_smh_id
            self._legacy_smh_id += 1
            avg_c = float(m.group("avg"))
            pixels = np.full(64, int(round(avg_c * 10.0)), dtype=np.uint16)
            return SMHFrame(frame_id=frame_id, pixels=pixels)
        except Exception as e:
            logger.warning(f"SMH legacy parse error: {e}")
            return None

    def _parse_mlx90640_legacy(self, line: str) -> Optional[MLX90640LegacyFrame]:
        try:
            m = MLX90640_LEGACY_RE.search(line)
            if not m:
                return None
            frame_id = self._legacy_mlx640_id
            self._legacy_mlx640_id += 1
            return MLX90640LegacyFrame(
                frame_id=frame_id,
                min_c=float(m.group("min")),
                avg_c=float(m.group("avg")),
                center_c=float(m.group("ctr")),
                max_c=float(m.group("max")),
                ta_c=float(m.group("ta")),
            )
        except Exception as e:
            logger.warning(f"MLX90640 legacy parse error: {e}")
            return None

