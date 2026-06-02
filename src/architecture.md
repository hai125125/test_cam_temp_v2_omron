# Thermal Node Architecture

## Tổng quan

```
┌─────────────────────────────────────────────────────────────────┐
│                        ATmega2560 (MCU)                         │
│                      "Acquisition Node"                         │
│                                                                 │
│  I2C Bus (shared)                                               │
│  ┌──────────────┐  400kHz   ┌─────────────────────────────┐    │
│  │  MLX90640    │ ────────► │  mlx_node.cpp               │    │
│  │  (0x33)      │           │  - Poll status register     │    │
│  └──────────────┘           │  - Read RAM 0x0400 in       │    │
│                             │    chunks of 16 words (32B) │    │
│  ┌──────────────┐  100kHz   │  - Stream binary packet     │    │
│  │  MLX90614    │ ────────► │    to Serial                │    │
│  │  (0x5A)      │           └─────────────────────────────┘    │
│  └──────────────┘                                               │
│                             ┌─────────────────────────────┐    │
│  ┌──────────────┐  100kHz   │  ASCII packets to Serial    │    │
│  │  SMH-01B01   │ ────────► │  SMH_FRAME / MLX614_FRAME   │    │
│  │  (0x0A)      │           └─────────────────────────────┘    │
│                                                                 │
│  SRAM usage: ~54 bytes (vs ~6KB for full Melexis processing)   │
└─────────────────────────┬───────────────────────────────────────┘
                          │ UART 921600 baud
                          │ ~12.5 KB/s per MLX90640 frame
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PC / Laptop (Python)                         │
│                   "Processing Engine"                           │
│                                                                 │
│  receiver.py                                                    │
│  ┌───────────────┐    ┌──────────────────┐    ┌─────────────┐  │
│  │ SerialReader  │───►│ ThermalNodeParser│───►│  raw_queue  │  │
│  │ (thread)      │    │ protocol.py      │    │             │  │
│  │               │    │ CRC validation   │    └──────┬──────┘  │
│  │               │    │ Frame sync       │           │         │
│  └───────────────┘    └──────────────────┘           ▼         │
│                                                ┌─────────────┐  │
│                                                │ Processing  │  │
│                                                │ Thread      │  │
│                                                │             │  │
│                                                │thermography │  │
│                                                │.py          │  │
│                                                │ - Vdd calc  │  │
│                                                │ - Ta calc   │  │
│                                                │ - To/pixel  │  │
│                                                │ - Bad pixel │  │
│                                                └──────┬──────┘  │
│                                                       │         │
│                                          ┌────────────▼──────┐  │
│                                          │   result_queue    │  │
│                                          └────────┬──────────┘  │
│                              ┌───────────────────►│             │
│                              │                    ▼             │
│                    ┌─────────┴──────┐   ┌──────────────────┐   │
│                    │   CSVLogger    │   │  ThermalVisualizer│   │
│                    │ visualizer.py  │   │  visualizer.py    │   │
│                    │               │   │  - Thermal image  │   │
│                    │ output.csv    │   │  - Time series    │   │
│                    └───────────────┘   │  - Sensor compare │   │
│                                        └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Binary Packet Protocol (MLX90640)

```
Byte offset  Size  Type      Field          Description
──────────────────────────────────────────────────────────────────
0            4     bytes     SYNC           0xAA 0x55 0xAA 0x55
──── CRC coverage starts here ────────────────────────────────────
4            2     uint16LE  FRAME_ID       rolling counter
6            1     uint8     SUBPAGE        0 or 1
7            2     int16LE   STATUS_RAW     register 0x8000
9            2     int16LE   PTAT_ART_RAW   RAM 0x0700
11           2     int16LE   PTAT_RAW       RAM 0x0720
13           2     int16LE   VDD_RAW        RAM 0x072A
15           2     int16LE   GAIN_RAW       RAM 0x070A
17           2     int16LE   CP_SP0_RAW     RAM 0x0708
19           2     int16LE   CP_SP1_RAW     RAM 0x0728
21           2     uint16LE  PIXEL_COUNT    always 768
23           1536  int16LE×768 PIXELS       row-major, row=0..23
──── CRC coverage ends here ──────────────────────────────────────
1559         2     uint16LE  CRC16-CCITT    poly=0x1021, init=0xFFFF
1561         2     bytes     END            0xBB 0x66
──────────────────────────────────────────────────────────────────
Total: 1563 bytes per frame
```

Pixel mapping per Melexis datasheet:
```
index = row * 32 + col      row ∈ [0,23],  col ∈ [0,31]
Numpy reshape: pixels.reshape(24, 32)
```

---

## ASCII Packets (SMH-01B01, MLX90614)

```
SMH_FRAME FRAME_ID:123 PIXELS:v0,v1,...,v63 END
  - 64 uint16 values, units = 0.1°C

MLX614_FRAME FRAME_ID:456 AMB_RAW:12345 OBJ_RAW:13456 END
  - Raw 16-bit Kelvin×50 values (same as MLX90614 register)
  - Convert: T_celsius = raw * 0.02 - 273.15
```

---

## RAM Budget: MCU vs full Melexis library

```
                         Before (full Melexis)    After (node)
─────────────────────────────────────────────────────────────
paramsMLX90640 struct       ~2500 B                 0 B
float frame[768]             3072 B                 0 B
int16_t frame[768]           1536 B                 0 B
s_eeprom[832]                1664 B                 0 B
Chunk buffer s_chunk[16]        0 B                32 B
CRC + misc                      0 B                22 B
─────────────────────────────────────────────────────────────
TOTAL MCU                   ~8772 B              ~54 B
Over 8KB limit?                YES                  NO
─────────────────────────────────────────────────────────────
```

---

## Error Recovery

### MCU side
- Short I2C read → fill remaining pixels with sentinel `0x7FFF`
- Lost connection → flag `s_ready = false`, print `# MLX_LOST`
- Frame timeout (1500ms) → skip frame, print `# MLX_TIMEOUT`

### Python side
- CRC mismatch → log warning, process frame anyway (data still usable)
- Missing SYNC → scanner skips bytes until next SYNC
- Buffer overflow (>8KB) → reset parser buffer, log warning
- Sentinel pixels (`0x7FFF`) → flagged as bad, interpolated from neighbors
- Serial disconnect → SerialException caught, thread exits cleanly

---

## Multi-sensor future: TCA9548A I2C multiplexer

```
ATmega2560
    │
    │ I2C
    ▼
TCA9548A (0x70)
├── Ch0 → MLX90640 #1 (0x33)   sensor_id=0
├── Ch1 → MLX90640 #2 (0x33)   sensor_id=1
├── Ch2 → SMH-01B01  (0x0A)
└── Ch3 → MLX90614   (0x5A)
```

To enable: `mlxNodeLoop(addr, sensor_id)` — FRAME_ID encodes sensor_id
in upper 4 bits: `frame_id = (sensor_id << 12) | rolling_counter`

Python parser differentiates frames by sensor_id field in packet header.

---

## EEPROM — First-time setup

MLX90640 calibration EEPROM (832 words) must be read **once** and saved locally.
Use the AVR EEPROM dump firmware on the ATmega2560 to dump the EEPROM to a binary file.

```bash
# Build and upload the EEPROM dump firmware environment:
platformio run -e megaatmega2560_dump
platformio run -e megaatmega2560_dump --target upload --upload-port COM7

# Then capture the eeprom output to a file from Serial at 921600 baud.
# Example PC-side command on Windows PowerShell:
#   python - <<'PY'
#   import serial
#   with serial.Serial('COM7', 921600, timeout=5) as ser, open('eeprom.bin', 'wb') as f:
#       while True:
#           line = ser.readline()
#           if not line:
#               break
#           if line.strip() == b'<EEPROM_BEGIN>':
#               continue
#           if line.strip() == b'<EEPROM_END>':
#               break
#           f.write(int(line.strip()).to_bytes(2, 'little'))
#   PY

# Run receiver with EEPROM:
python receiver.py --port COM7 --eeprom eeprom.bin --csv log.csv
```

---

## Throughput

```
At 921600 baud:
  Frame size    : 1563 bytes
  Serial rate   : ~92160 bytes/s
  Frame time    : 1563 / 92160 ≈ 17ms per frame (serial only)
  Sensor rate   : 2 Hz (MLX90640 @ 2Hz refresh)
  Duty cycle    : 17ms / 500ms = 3.4%  ← plenty of headroom

At 4Hz (MLX90640 max stable on ATmega):
  Frame time    : 17ms / 250ms = 6.8%  ← still fine
```

---

## File structure

```
thermal_node/
├── firmware/
│   ├── main.cpp           — ATmega2560 entry point
│   ├── test_MLX90640.h         — Protocol constants + API
│   ├── test_MLX90640.cpp       — Acquisition loop + packet sender
│   ├── SMH_01B01.h/.cpp   — SMH driver (unchanged)
│   └── test_MLX90614.h/.cpp — MLX90614 raw SMBus driver
│
└── python/
    ├── receiver.py        — Entry point, threads, CLI
    ├── protocol.py        — Binary/ASCII parser, CRC
    ├── thermography.py    — Melexis To calculation, EEPROM
    └── visualizer.py      — Matplotlib dashboard + CSV
```
