import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

ROWS, COLS = 24, 32
PIXEL_COUNT = ROWS * COLS
SCALE_ALPHA = 0.000001


@dataclass
class ThermalResult:
    frame_id: int
    subpage: int
    Ta: float
    Vdd: float
    temperatures: np.ndarray
    hotspot_idx: tuple
    center_temp: float
    min_temp: float
    max_temp: float
    avg_temp: float
    bad_pixels: list = field(default_factory=list)


@dataclass
class ApplicationCorrectionConfig:
    """Optional display/application correction applied after Melexis To."""
    enabled: bool = False
    offset_c: float = 0.0


def _s8(v: int) -> int:
    v &= 0xFF
    return v - 256 if v > 127 else v


def _s4(v: int) -> int:
    v &= 0x0F
    return v - 16 if v > 7 else v


def _s6(v: int) -> int:
    v &= 0x3F
    return v - 64 if v > 31 else v


def _s10(v: int) -> int:
    v &= 0x03FF
    return v - 1024 if v > 511 else v


def _s16(v: int) -> int:
    v &= 0xFFFF
    return v - 65536 if v > 32767 else v


def _u16(v: int) -> np.uint16:
    return np.uint16(int(v) & 0xFFFF)


class MLX90640Processor:
    """PC-side MLX90640 temperature reconstruction, ported from Melexis API."""

    EMISSIVITY = 1.0
    DEFAULT_TR_OFFSET = 0.0

    def __init__(
        self,
        emissivity: float = EMISSIVITY,
        app_correction: Optional[ApplicationCorrectionConfig] = None,
    ):
        self.emissivity = float(emissivity)
        self.app_correction = app_correction or ApplicationCorrectionConfig()
        self._params = None
        self._ready = False
        self._last_temperatures = np.full(PIXEL_COUNT, np.nan, dtype=np.float32)
        self._subpage_cache = {
            0: {"temps": None, "valid": None, "frame_id": None, "Ta": None, "Vdd": None},
            1: {"temps": None, "valid": None, "frame_id": None, "Ta": None, "Vdd": None},
        }

    def load_eeprom_from_file(self, path: str) -> bool:
        try:
            with open(path, "rb") as f:
                raw = f.read()

            ee = np.frombuffer(raw, dtype="<u2")
            logger.info("EEPROM file loaded: bytes=%d words=%d", len(raw), ee.size)
            if ee.size < 832:
                raise ValueError(f"EEPROM too short: {ee.size} words")

            self._params = self._extract_params_autodetect_endian(ee[:832].astype(np.uint16, copy=True))
            self._ready = True
            logger.info("EEPROM loaded and MLX90640 parameters extracted")
            self._log_param_summary(self._params)
            return True
        except Exception as e:
            logger.error(f"EEPROM load error: {e}", exc_info=True)
            return False

    def load_params_dict(self, params: dict):
        self._params = params
        self._ready = True

    def set_application_correction(self, enabled: bool, offset_c: float = 0.0):
        self.app_correction = ApplicationCorrectionConfig(
            enabled=bool(enabled),
            offset_c=float(offset_c),
        )
        logger.info(
            "MLX90640 application correction: enabled=%s offset_c=%.3f",
            self.app_correction.enabled,
            self.app_correction.offset_c,
        )

    def process(self, frame) -> Optional[ThermalResult]:
        if self._params is None:
            logger.error("No EEPROM params loaded")
            return None
        if frame.pixels_raw is None:
            return None

        raw_pixels = np.asarray(frame.pixels_raw, dtype=np.int16)
        if raw_pixels.size != PIXEL_COUNT:
            logger.warning("Bad MLX90640 pixel count: %d", raw_pixels.size)
            return None

        frame_data = self._build_frame_data(frame, raw_pixels)
        p = self._params
        vdd = self._get_vdd(frame_data, p)
        ta = self._get_ta(frame_data, p, vdd)
        gain = self._get_gain(frame_data, p)
        tr = ta + self.DEFAULT_TR_OFFSET

        logger.debug(
            "MLX90640 runtime F%d subpage=%d status=0x%04X raw: vdd=%d ptat=%d ptat_art=%d "
            "gain_raw=%d gain=%.6f cp0=%d cp1=%d emissivity=%.3f tr=%.2f",
            frame.frame_id,
            int(frame.subpage) & 0x01,
            int(frame.status_raw) & 0xFFFF,
            int(frame.vdd_raw),
            int(frame.ptat_raw),
            int(frame.ptat_art_raw),
            int(frame.gain_raw),
            gain,
            int(frame.cp_sp0_raw),
            int(frame.cp_sp1_raw),
            self.emissivity,
            tr,
        )

        temps = self._calculate_to(frame_data, p, self.emissivity, tr, ta, vdd)
        temps = self._bad_pixels_correction(temps, p, mode=(frame_data[832] & 0x1000) >> 12)

        valid = np.isfinite(temps) & (temps > -80.0) & (temps < 300.0)
        if not np.any(valid):
            logger.warning(
                "All pixels invalid after MLX90640 CalculateTo: "
                "Ta=%.2f Vdd=%.3f subpage=%d raw_min=%d raw_max=%d",
                ta, vdd, frame.subpage, int(raw_pixels.min()), int(raw_pixels.max())
            )
            return None

        subpage = int(frame.subpage) & 0x01
        self._subpage_cache[subpage] = {
            "temps": temps.astype(np.float64, copy=True),
            "valid": valid.astype(bool, copy=True),
            "frame_id": int(frame.frame_id),
            "Ta": float(ta),
            "Vdd": float(vdd),
        }

        logger.debug(
            "MLX90640 subpage F%d subpage=%d Ta=%.2f Vdd=%.3f min=%.2f max=%.2f mean=%.2f bad=%d",
            frame.frame_id, subpage, ta, vdd,
            float(np.nanmin(temps[valid])), float(np.nanmax(temps[valid])), float(np.nanmean(temps[valid])),
            int((~valid).sum()),
        )

        merged = self._merge_subpages()
        if merged is None:
            logger.debug("MLX90640 waiting for both subpages before emitting full frame")
            return None

        merged_temps_raw, merged_valid, merged_ta, merged_vdd = merged
        raw_vals = merged_temps_raw[merged_valid]
        merged_temps = self._apply_application_correction(merged_temps_raw, merged_valid)
        corrected_vals = merged_temps[merged_valid]

        logger.debug(
            "MLX90640 merged To raw F%d min=%.2f max=%.2f mean=%.2f; corrected min=%.2f max=%.2f mean=%.2f",
            frame.frame_id,
            float(np.nanmin(raw_vals)), float(np.nanmax(raw_vals)), float(np.nanmean(raw_vals)),
            float(np.nanmin(corrected_vals)), float(np.nanmax(corrected_vals)), float(np.nanmean(corrected_vals)),
        )

        self._last_temperatures = merged_temps.astype(np.float32, copy=True)
        temps_2d = merged_temps.reshape((ROWS, COLS)).astype(np.float32)
        valid_2d = merged_valid.reshape((ROWS, COLS))
        vals = temps_2d[valid_2d]

        hotspot = np.unravel_index(np.nanargmax(np.where(valid_2d, temps_2d, np.nan)), temps_2d.shape)
        center = temps_2d[10:13, 14:18]
        center_temp = float(np.nanmean(center))

        logger.debug(
            "MLX90640 merged F%d subpages=(%s,%s) Ta=%.2f Vdd=%.3f min=%.2f max=%.2f mean=%.2f bad=%d",
            frame.frame_id,
            self._subpage_cache[0]["frame_id"], self._subpage_cache[1]["frame_id"],
            merged_ta, merged_vdd,
            float(np.nanmin(vals)), float(np.nanmax(vals)), float(np.nanmean(vals)),
            int((~merged_valid).sum()),
        )

        return ThermalResult(
            frame_id=frame.frame_id,
            subpage=subpage,
            Ta=float(merged_ta),
            Vdd=float(merged_vdd),
            temperatures=temps_2d,
            hotspot_idx=hotspot,
            center_temp=center_temp,
            min_temp=float(np.nanmin(vals)),
            max_temp=float(np.nanmax(vals)),
            avg_temp=float(np.nanmean(vals)),
            bad_pixels=list(zip(*np.where(~valid_2d))),
        )

    def _apply_application_correction(self, temps: np.ndarray, valid: np.ndarray) -> np.ndarray:
        corrected = temps.astype(np.float64, copy=True)
        cfg = self.app_correction
        if not cfg.enabled:
            return corrected
        corrected[valid] = corrected[valid] + cfg.offset_c
        logger.debug("Applied MLX90640 application offset correction: %.3f C", cfg.offset_c)
        return corrected

    def _merge_subpages(self):
        sp0 = self._subpage_cache[0]
        sp1 = self._subpage_cache[1]
        if sp0["temps"] is None or sp1["temps"] is None:
            return None

        merged_valid = sp0["valid"] | sp1["valid"]
        merged_temps = np.full(PIXEL_COUNT, np.nan, dtype=np.float64)
        merged_temps[sp0["valid"]] = sp0["temps"][sp0["valid"]]
        merged_temps[sp1["valid"]] = sp1["temps"][sp1["valid"]]

        if not np.any(merged_valid):
            return None

        ta_values = [v for v in (sp0["Ta"], sp1["Ta"]) if v is not None and np.isfinite(v)]
        vdd_values = [v for v in (sp0["Vdd"], sp1["Vdd"]) if v is not None and np.isfinite(v)]
        merged_ta = float(np.mean(ta_values)) if ta_values else float("nan")
        merged_vdd = float(np.mean(vdd_values)) if vdd_values else float("nan")
        return merged_temps, merged_valid, merged_ta, merged_vdd

    def _build_frame_data(self, frame, pixels: np.ndarray) -> np.ndarray:
        fd = np.zeros(834, dtype=np.uint16)
        fd[:PIXEL_COUNT] = pixels.view(np.uint16)
        fd[768] = _u16(frame.ptat_art_raw)
        fd[776] = _u16(frame.cp_sp0_raw)
        fd[778] = _u16(frame.gain_raw)
        fd[800] = _u16(frame.ptat_raw)
        fd[808] = _u16(frame.cp_sp1_raw)
        fd[810] = _u16(frame.vdd_raw)

        # Firmware configures 19-bit ADC and chess mode. If control register is
        # not transported, synthesize the fields used by the Melexis equations.
        ctrl = 0x1000 | (0x03 << 10)
        fd[832] = _u16(ctrl)
        fd[833] = _u16(int(frame.subpage) & 0x01)
        return fd

    def _get_vdd(self, fd: np.ndarray, p: dict) -> float:
        vdd_raw = _s16(int(fd[810]))
        resolution_ram = (int(fd[832]) & 0x0C00) >> 10
        resolution_correction = (2.0 ** p["resolutionEE"]) / (2.0 ** resolution_ram)
        return (resolution_correction * vdd_raw - p["vdd25"]) / p["kVdd"] + 3.3

    def _get_ta(self, fd: np.ndarray, p: dict, vdd: float) -> float:
        ptat = _s16(int(fd[800]))
        ptat_art_raw = _s16(int(fd[768]))
        denom = ptat * p["alphaPTAT"] + ptat_art_raw
        if abs(denom) < 1e-9:
            return float("nan")
        ptat_art = (ptat / denom) * (2.0 ** 18)
        return (ptat_art / (1.0 + p["KvPTAT"] * (vdd - 3.3)) - p["vPTAT25"]) / p["KtPTAT"] + 25.0

    def _get_gain(self, fd: np.ndarray, p: dict) -> float:
        gain_raw = _s16(int(fd[778]))
        if gain_raw == 0:
            return float("nan")
        return p["gainEE"] / gain_raw

    def _calculate_to(self, fd: np.ndarray, p: dict, emissivity: float, tr: float, ta: float, vdd: float) -> np.ndarray:
        result = np.full(PIXEL_COUNT, np.nan, dtype=np.float64)

        ta4 = (ta + 273.15) ** 4
        tr4 = (tr + 273.15) ** 4
        ta_tr = tr4 - (tr4 - ta4) / emissivity

        alpha_corr_r = np.empty(4, dtype=np.float64)
        alpha_corr_r[0] = 1.0 / (1.0 + p["ksTo"][0] * 40.0)
        alpha_corr_r[1] = 1.0
        alpha_corr_r[2] = 1.0 + p["ksTo"][1] * p["ct"][2]
        alpha_corr_r[3] = alpha_corr_r[2] * (1.0 + p["ksTo"][2] * (p["ct"][3] - p["ct"][2]))

        gain_raw = _s16(int(fd[778]))
        if gain_raw == 0:
            logger.warning("MLX90640 gain_raw is zero")
            return result
        gain = self._get_gain(fd, p)

        mode = (int(fd[832]) & 0x1000) >> 5
        subpage = int(fd[833]) & 0x01

        ir_data_cp = np.array([_s16(int(fd[776])), _s16(int(fd[808]))], dtype=np.float64) * gain
        ir_data_cp[0] -= p["cpOffset"][0] * (1.0 + p["cpKta"] * (ta - 25.0)) * (1.0 + p["cpKv"] * (vdd - 3.3))
        if mode == p["calibrationModeEE"]:
            ir_data_cp[1] -= p["cpOffset"][1] * (1.0 + p["cpKta"] * (ta - 25.0)) * (1.0 + p["cpKv"] * (vdd - 3.3))
        else:
            ir_data_cp[1] -= (p["cpOffset"][1] + p["ilChessC"][0]) * (1.0 + p["cpKta"] * (ta - 25.0)) * (1.0 + p["cpKv"] * (vdd - 3.3))
        logger.debug(
            "MLX90640 CalculateTo: mode=%d subpage=%d calibModeEE=%d alphaCorrR=%s irDataCP=%s",
            mode,
            subpage,
            p["calibrationModeEE"],
            np.array2string(alpha_corr_r, precision=6),
            np.array2string(ir_data_cp, precision=3),
        )

        for pixel in range(PIXEL_COUNT):
            row = pixel // 32
            col = pixel % 32
            il_pattern = row & 1
            chess_pattern = il_pattern ^ (col & 1)
            conversion_pattern = ((pixel + 2) // 4 - (pixel + 3) // 4 + (pixel + 1) // 4 - pixel // 4) * (1 - 2 * il_pattern)
            pattern = il_pattern if mode == 0 else chess_pattern

            if pattern != subpage:
                continue

            ir_data = _s16(int(fd[pixel])) * gain
            ir_data -= p["offset"][pixel] * (1.0 + p["kta"][pixel] * (ta - 25.0)) * (1.0 + p["kv"][pixel] * (vdd - 3.3))
            if mode != p["calibrationModeEE"]:
                ir_data += p["ilChessC"][2] * (2 * il_pattern - 1) - p["ilChessC"][1] * conversion_pattern

            ir_data -= p["tgc"] * ir_data_cp[subpage]
            ir_data /= emissivity

            alpha_comp = p["alpha"][pixel]
            alpha_comp *= 1.0 + p["KsTa"] * (ta - 25.0)
            if alpha_comp <= 0:
                continue

            sx_arg = (alpha_comp ** 3) * (ir_data + alpha_comp * ta_tr)
            if sx_arg < 0:
                continue
            sx = math.sqrt(math.sqrt(sx_arg)) * p["ksTo"][1]

            denom = alpha_comp * (1.0 - p["ksTo"][1] * 273.15) + sx
            first_arg = ir_data / denom + ta_tr if abs(denom) > 1e-18 else -1.0
            if first_arg < 0:
                continue
            to_est = math.sqrt(math.sqrt(first_arg)) - 273.15

            if to_est < p["ct"][1]:
                temp_range = 0
            elif to_est < p["ct"][2]:
                temp_range = 1
            elif to_est < p["ct"][3]:
                temp_range = 2
            else:
                temp_range = 3

            denom = alpha_comp * alpha_corr_r[temp_range] * (1.0 + p["ksTo"][temp_range] * (to_est - p["ct"][temp_range]))
            final_arg = ir_data / denom + ta_tr if abs(denom) > 1e-18 else -1.0
            if final_arg >= 0:
                result[pixel] = math.sqrt(math.sqrt(final_arg)) - 273.15

        return result

    def _extract_params(self, ee: np.ndarray) -> dict:
        if int(ee[10]) & 0x0040:
            raise ValueError("EEPROM deviceSelect bit indicates invalid MLX90640 EEPROM")

        p = {}
        p["kVdd"] = _s8(int(ee[51]) >> 8) * 32
        p["vdd25"] = (((int(ee[51]) & 0x00FF) - 256) << 5) - 8192
        p["KvPTAT"] = _s6((int(ee[50]) & 0xFC00) >> 10) / 4096.0
        p["KtPTAT"] = _s10(int(ee[50]) & 0x03FF) / 8.0
        p["vPTAT25"] = int(ee[49])
        p["alphaPTAT"] = ((int(ee[16]) & 0xF000) >> 14) + 8
        p["gainEE"] = _s16(int(ee[48]))
        p["tgc"] = _s8(int(ee[60]) & 0x00FF) / 32.0
        p["resolutionEE"] = (int(ee[56]) & 0x3000) >> 12
        p["calibrationModeEE"] = ((int(ee[10]) & 0x0800) >> 4) ^ 0x80
        p["KsTa"] = _s8((int(ee[60]) & 0xFF00) >> 8) / 8192.0

        self._extract_ks_to(ee, p)
        self._extract_cp(ee, p)
        self._extract_alpha(ee, p)
        self._extract_offset(ee, p)
        self._extract_kta(ee, p)
        self._extract_kv(ee, p)
        self._extract_cilc(ee, p)
        self._extract_deviating_pixels(ee, p)
        return p

    def _extract_params_autodetect_endian(self, ee: np.ndarray) -> dict:
        candidates = []
        for name, data in (("native", ee), ("byteswap", ee.byteswap())):
            try:
                params = self._extract_params(data.astype(np.uint16, copy=True))
                score = self._score_params(params)
                candidates.append((score, name, params))
                logger.debug("EEPROM endian candidate %s score=%.1f", name, score)
            except Exception as exc:
                logger.debug("EEPROM endian candidate %s rejected: %s", name, exc)

        if not candidates:
            raise ValueError("Could not extract MLX90640 parameters from EEPROM")

        candidates.sort(key=lambda item: item[0], reverse=True)
        score, name, params = candidates[0]
        params["eepromEndian"] = name
        if name != "native":
            logger.warning("EEPROM word byte order appears swapped; using byteswapped calibration words")
        if score < 20.0:
            logger.warning("EEPROM parameter sanity score is low: %.1f", score)
        return params

    def _score_params(self, p: dict) -> float:
        score = 0.0
        alpha = np.asarray(p["alpha"])
        offset = np.asarray(p["offset"])
        bad_count = len(p.get("brokenPixels", [])) + len(p.get("outlierPixels", []))

        if np.all(np.isfinite(alpha)) and 1e-9 < float(np.nanmin(alpha)) < float(np.nanmax(alpha)) < 1e-6:
            score += 30.0
        if np.all(np.isfinite(offset)) and -2000.0 < float(np.nanmin(offset)) < float(np.nanmax(offset)) < 2000.0:
            score += 20.0
        if -20000 < p["gainEE"] < 20000 and p["gainEE"] != 0:
            score += 10.0
        if p["kVdd"] != 0 and -10000 < p["kVdd"] < 10000:
            score += 10.0
        if 0.0 < p["KtPTAT"] < 200.0:
            score += 10.0
        if bad_count <= 4:
            score += 20.0
        else:
            score -= min(40.0, bad_count)
        return score

    def _extract_ks_to(self, ee: np.ndarray, p: dict):
        step = ((int(ee[63]) & 0x3000) >> 12) * 10
        ct = np.array([-40, 0, (int(ee[63]) & 0x00F0) >> 4, (int(ee[63]) & 0x0F00) >> 8], dtype=np.int16)
        ct[2] = ct[2] * step
        ct[3] = ct[2] + ct[3] * step
        scale = 1 << ((int(ee[63]) & 0x000F) + 8)
        ks_to = np.array([
            _s8(int(ee[61]) & 0x00FF),
            _s8((int(ee[61]) & 0xFF00) >> 8),
            _s8(int(ee[62]) & 0x00FF),
            _s8((int(ee[62]) & 0xFF00) >> 8),
        ], dtype=np.float64) / scale
        p["ct"] = ct
        p["ksTo"] = ks_to

    def _extract_alpha(self, ee: np.ndarray, p: dict):
        acc_rem_scale = int(ee[32]) & 0x000F
        acc_col_scale = (int(ee[32]) & 0x00F0) >> 4
        acc_row_scale = (int(ee[32]) & 0x0F00) >> 8
        alpha_scale = ((int(ee[32]) & 0xF000) >> 12) + 30
        alpha_ref = int(ee[33])

        acc_row = np.zeros(24, dtype=np.int16)
        for i in range(6):
            w = int(ee[34 + i])
            for k in range(4):
                acc_row[i * 4 + k] = _s4(w >> (4 * k))

        acc_col = np.zeros(32, dtype=np.int16)
        for i in range(8):
            w = int(ee[40 + i])
            for k in range(4):
                acc_col[i * 4 + k] = _s4(w >> (4 * k))

        alpha = np.zeros(PIXEL_COUNT, dtype=np.float64)
        for row in range(24):
            for col in range(32):
                idx = row * 32 + col
                rem = _s6((int(ee[64 + idx]) & 0x03F0) >> 4) * (1 << acc_rem_scale)
                alpha[idx] = (alpha_ref + (int(acc_row[row]) << acc_row_scale) + (int(acc_col[col]) << acc_col_scale) + rem)
                alpha[idx] /= 2.0 ** alpha_scale
                alpha[idx] -= p["tgc"] * (p["cpAlpha"][0] + p["cpAlpha"][1]) / 2.0
        p["alpha"] = alpha

    def _extract_offset(self, ee: np.ndarray, p: dict):
        occ_rem_scale = int(ee[16]) & 0x000F
        occ_col_scale = (int(ee[16]) & 0x00F0) >> 4
        occ_row_scale = (int(ee[16]) & 0x0F00) >> 8
        offset_ref = _s16(int(ee[17]))

        occ_row = np.zeros(24, dtype=np.int16)
        for i in range(6):
            w = int(ee[18 + i])
            for k in range(4):
                occ_row[i * 4 + k] = _s4(w >> (4 * k))

        occ_col = np.zeros(32, dtype=np.int16)
        for i in range(8):
            w = int(ee[24 + i])
            for k in range(4):
                occ_col[i * 4 + k] = _s4(w >> (4 * k))

        offset = np.zeros(PIXEL_COUNT, dtype=np.float64)
        for row in range(24):
            for col in range(32):
                idx = row * 32 + col
                rem = _s6((int(ee[64 + idx]) & 0xFC00) >> 10) * (1 << occ_rem_scale)
                offset[idx] = offset_ref + (int(occ_row[row]) << occ_row_scale) + (int(occ_col[col]) << occ_col_scale) + rem
        p["offset"] = offset

    def _extract_kta(self, ee: np.ndarray, p: dict):
        kta_rc = np.array([
            _s8((int(ee[54]) & 0xFF00) >> 8),
            _s8((int(ee[55]) & 0xFF00) >> 8),
            _s8(int(ee[54]) & 0x00FF),
            _s8(int(ee[55]) & 0x00FF),
        ], dtype=np.float64)
        kta_scale1 = ((int(ee[56]) & 0x00F0) >> 4) + 8
        kta_scale2 = int(ee[56]) & 0x000F

        kta = np.zeros(PIXEL_COUNT, dtype=np.float64)
        for row in range(24):
            for col in range(32):
                idx = row * 32 + col
                split = 2 * (row & 1) + (col & 1)
                rem = ((int(ee[64 + idx]) & 0x000E) >> 1)
                rem = rem - 8 if rem > 3 else rem
                kta[idx] = (kta_rc[split] + rem * (1 << kta_scale2)) / (2.0 ** kta_scale1)
        p["kta"] = kta

    def _extract_kv(self, ee: np.ndarray, p: dict):
        kv_t = np.array([
            _s4((int(ee[52]) & 0xF000) >> 12),
            _s4((int(ee[52]) & 0x00F0) >> 4),
            _s4((int(ee[52]) & 0x0F00) >> 8),
            _s4(int(ee[52]) & 0x000F),
        ], dtype=np.float64)
        kv_scale = (int(ee[56]) & 0x0F00) >> 8
        kv = np.zeros(PIXEL_COUNT, dtype=np.float64)
        for row in range(24):
            for col in range(32):
                idx = row * 32 + col
                split = 2 * (row & 1) + (col & 1)
                kv[idx] = kv_t[split] / (2.0 ** kv_scale)
        p["kv"] = kv

    def _extract_cp(self, ee: np.ndarray, p: dict):
        alpha_scale = ((int(ee[32]) & 0xF000) >> 12) + 27
        kta_scale1 = ((int(ee[56]) & 0x00F0) >> 4) + 8
        kv_scale = (int(ee[56]) & 0x0F00) >> 8

        cp_alpha_0 = ((int(ee[57]) & 0x03FF))
        if cp_alpha_0 > 511:
            cp_alpha_0 -= 1024
        cp_alpha_0 = cp_alpha_0 / (2.0 ** alpha_scale)

        cp_alpha_1 = ((int(ee[57]) & 0xFC00) >> 10)
        if cp_alpha_1 > 31:
            cp_alpha_1 -= 64
        cp_alpha_1 = (1.0 + cp_alpha_1 / 128.0) * cp_alpha_0

        cp_offset_0 = _s10(int(ee[58]) & 0x03FF)
        cp_offset_1 = ((int(ee[58]) & 0xFC00) >> 10)
        if cp_offset_1 > 31:
            cp_offset_1 -= 64
        cp_offset_1 = cp_offset_1 + cp_offset_0

        cp_kta = _s8(int(ee[59]) & 0x00FF) / (2.0 ** kta_scale1)
        cp_kv = _s8((int(ee[59]) & 0xFF00) >> 8) / (2.0 ** kv_scale)

        p["cpAlpha"] = np.array([cp_alpha_0, cp_alpha_1], dtype=np.float64)
        p["cpOffset"] = np.array([cp_offset_0, cp_offset_1], dtype=np.float64)
        p["cpKta"] = float(cp_kta)
        p["cpKv"] = float(cp_kv)

    def _extract_cilc(self, ee: np.ndarray, p: dict):
        il_chess_c = np.zeros(3, dtype=np.float64)
        il_chess_0 = int(ee[53]) & 0x003F
        if il_chess_0 > 31:
            il_chess_0 -= 64
        il_chess_c[0] = il_chess_0 / 16.0

        il_chess_1 = (int(ee[53]) & 0x07C0) >> 6
        if il_chess_1 > 15:
            il_chess_1 -= 32
        il_chess_c[1] = il_chess_1 / 2.0

        il_chess_2 = (int(ee[53]) & 0xF800) >> 11
        if il_chess_2 > 15:
            il_chess_2 -= 32
        il_chess_c[2] = il_chess_2 / 8.0
        p["ilChessC"] = il_chess_c

    def _extract_deviating_pixels(self, ee: np.ndarray, p: dict):
        broken = []
        outlier = []
        for pix in range(PIXEL_COUNT):
            word = int(ee[64 + pix])
            if word == 0:
                broken.append(pix)
            elif (word & 0x0001) != 0:
                outlier.append(pix)
        p["brokenPixels"] = broken[:5]
        p["outlierPixels"] = outlier[:5]
        p["badPixelWarning"] = len(broken) > 4 or len(outlier) > 4 or (len(broken) + len(outlier) > 4)
        for a in p["brokenPixels"] + p["outlierPixels"]:
            for b in p["brokenPixels"] + p["outlierPixels"]:
                if a != b and abs(a - b) in (1, 31, 32, 33):
                    p["badPixelWarning"] = True

    def _bad_pixels_correction(self, temps: np.ndarray, p: dict, mode: int) -> np.ndarray:
        corrected = temps.astype(np.float64, copy=True)
        for pix in p.get("brokenPixels", []) + p.get("outlierPixels", []):
            if pix < PIXEL_COUNT:
                corrected[pix] = self._interpolate_bad_pixel(corrected, pix, mode)
        return corrected

    def _interpolate_bad_pixel(self, values: np.ndarray, pix: int, mode: int) -> float:
        row, col = divmod(pix, 32)
        candidates = []
        if mode == 1:
            offsets = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        else:
            offsets = [(-2, 0), (2, 0), (0, -2), (0, 2)]
        for dr, dc in offsets:
            rr, cc = row + dr, col + dc
            if 0 <= rr < 24 and 0 <= cc < 32:
                v = values[rr * 32 + cc]
                if np.isfinite(v):
                    candidates.append(float(v))
        return float(np.mean(candidates)) if candidates else float("nan")

    def _log_param_summary(self, p: dict):
        logger.info(
            "MLX90640 params: gainEE=%d kVdd=%d vdd25=%d KvPTAT=%.6f KtPTAT=%.3f "
            "alpha=[%.3e..%.3e] offset=[%.1f..%.1f] kta=[%.6f..%.6f] kv=[%.6f..%.6f] bad=%d",
            p["gainEE"], p["kVdd"], p["vdd25"], p["KvPTAT"], p["KtPTAT"],
            float(np.nanmin(p["alpha"])), float(np.nanmax(p["alpha"])),
            float(np.nanmin(p["offset"])), float(np.nanmax(p["offset"])),
            float(np.nanmin(p["kta"])), float(np.nanmax(p["kta"])),
            float(np.nanmin(p["kv"])), float(np.nanmax(p["kv"])),
            len(p.get("brokenPixels", [])) + len(p.get("outlierPixels", [])),
        )
        logger.info(
            "MLX90640 CP/thermal params: cpAlpha=%s cpOffset=%s cpKta=%.6f cpKv=%.6f "
            "tgc=%.6f KsTa=%.6f ksTo=%s ct=%s calibrationModeEE=%s",
            np.array2string(p["cpAlpha"], precision=6),
            np.array2string(p["cpOffset"], precision=3),
            p["cpKta"],
            p["cpKv"],
            p["tgc"],
            p["KsTa"],
            np.array2string(p["ksTo"], precision=6),
            np.array2string(p["ct"]),
            p["calibrationModeEE"],
        )
        if p.get("badPixelWarning"):
            logger.warning(
                "EEPROM bad-pixel map needs attention: broken=%s outlier=%s",
                p.get("brokenPixels", []), p.get("outlierPixels", []),
            )
