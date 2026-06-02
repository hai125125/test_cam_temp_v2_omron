Thermal Node Protocol Specification
=================================

Overview
--------
This document defines the binary UART protocol used by the Thermal Node (ATmega) to stream sensor data to the PC.

Framing
-------
- Header: 0x55 0xAA (2 bytes)
- Type:   1 byte
- Frame ID: 2 bytes (uint16 little-endian)
- Length: 2 bytes (uint16 little-endian) — payload length in bytes
- Payload: variable
- CRC8: 1 byte (covers Type + FrameID + Length + Payload)

CRC
---
- CRC-8 polynomial 0x07 (x^8 + x^2 + x + 1), initial 0x00. Same as `crc8` implemented in `protocol.py`.

Packet Types
------------
- 0x01 — MLX90640
- 0x02 — SMH-01B01
- 0x03 — MLX90614
- 0xFE — EEPROM block (special)

MLX90640 Payload Layouts
-------------------------
Two supported payload variants (receiver will accept either):

Simple (legacy):
- Payload length = 768 * 2 bytes
- Payload = 768 int16 pixels in row-major order (24 rows × 32 cols) little-endian

Extended (recommended):
- Payload length = 15 + 768 * 2 bytes
- Metadata (15 bytes, little-endian):
  - subpage: uint8
  - status_raw: uint16
  - ptat_art_raw: int16
  - ptat_raw: int16
  - vdd_raw: int16
  - gain_raw: int16
  - cp_sp0_raw: int16
  - cp_sp1_raw: int16
- Pixels: 768 int16 as above

Notes:
- The extended payload allows full PC-side reconstruction using the Melexis pipeline (Vdd, Ta, gain, CP, subpage).
- The EEPROM dump (see below) must be transferred once to the PC so the MLX90640 processor can ExtractParameters().

EEPROM Transfer
---------------
Use packet type 0xFE to send EEPROM blocks. Recommended approach:
- Send a header packet with total size and CRC/ID
- Then stream chunks of 256 bytes with sequential block IDs
- The PC reassembles into an 832-word (1664 bytes) little-endian uint16 file.

MLX90614 (MLX614) Payload
-------------------------
- Payload length = 4
- amb_raw:int16, obj_raw:int16 (little-endian)

SMH-01B01 Payload
-----------------
- Payload length = 64 * 2
- 64 uint16 values (little-endian). The firmware should send temperatures in tenths of °C (value=°C*10) or as float32 when bandwidth allows; include a version flag in `status` if format differs.

Timestamping
------------
- Optional: include a 4-byte UNIX timestamp (uint32) at the start of the payload if host-side time alignment is required. If used, document it in the status byte flags and adjust the payload length accordingly.

Frame ID and Ordering
---------------------
- Always include `frame_id` increasing modulo 65536.
- Receiver should detect missing frames and report drops.

Flow Control and Baud
---------------------
- Use hardware flow control (RTS/CTS) if available when baud > 115200.
- Recommended default baud: 921600 for high-throughput MLX90640 frames.
- If link reliability is low, reduce baud to 230400 and use larger UART buffers.

Error Handling
--------------
- Receiver must verify CRC8 for each packet and discard invalid packets.
- Include slow ASCII debug lines prefixed with '#' for human debugging — parser ignores them.

Design Rationale
----------------
- The extended MLX payload ensures PC has all measurements required by Melexis CalculateTo() and avoids any MCU-side approximations or normalisation.
- EEPROM transfer is separate to avoid repeated sends and to allow offline testing.

Example
-------
Header: 55 AA 01 34 12 02 00 ...payload... CRC

Implementation: See `protocol.py` which implements the binary parser and supports the extended MLX payload.
