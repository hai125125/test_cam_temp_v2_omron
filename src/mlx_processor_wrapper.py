"""mlx_processor_wrapper.py

Convenience wrapper around `thermography.MLX90640Processor`.
Use this when you want to load EEPROM once and process frames emitted by `protocol.ThermalNodeParser`.
"""
from thermography import MLX90640Processor, ThermalResult
from protocol import MLX640Frame
import logging

logger = logging.getLogger(__name__)


class MLXProcessorWrapper:
    def __init__(self, eeprom_path: str = None):
        self.proc = MLX90640Processor()
        if eeprom_path:
            ok = self.proc.load_eeprom_from_file(eeprom_path)
            if not ok:
                logger.error("Failed to load EEPROM — processor not ready")

    def process_frame(self, frame: MLX640Frame) -> ThermalResult:
        """Process a `MLX640Frame` and return `ThermalResult` or None."""
        return self.proc.process(frame)


def example_usage():
    """Example showing how to use the wrapper with a parsed frame.
    Replace with actual serial-parsed frames from `protocol.ThermalNodeParser`.
    """
    import numpy as np
    # fake frame for demo
    fake_pixels = np.zeros(24*32, dtype=np.int16)
    frame = MLX640Frame(frame_id=1, pixels_raw=fake_pixels, crc_ok=True)
    w = MLXProcessorWrapper(eeprom_path="eeprom.bin")
    res = w.process_frame(frame)
    if res:
        print("Center temp:", res.center_temp)
    else:
        print("No result — check EEPROM or frame metadata")


if __name__ == "__main__":
    example_usage()
