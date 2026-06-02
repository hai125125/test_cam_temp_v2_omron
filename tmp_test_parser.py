import sys
sys.path.insert(0, "src")
from protocol import ThermalNodeParser, TYPE_SMH, crc8
import struct, numpy as np
# craft 64 uint16 values
vals = np.arange(64, dtype=np.uint16) + 2400
payload = vals.tobytes()
frame_id = 7
payload_length = len(payload)
header = bytes([0x55,0xAA, TYPE_SMH]) + struct.pack('<H', frame_id) + struct.pack('<H', payload_length) + payload
crc = crc8(header[2:])
packet = header + bytes([crc])
parser = ThermalNodeParser()
frames = parser.feed(packet)
print('parsed count:', len(frames))
if frames:
    f = frames[0]
    print('frame_id', f.frame_id)
    print('first8', f.pixels[:8])
    print('dtype', f.pixels.dtype)
