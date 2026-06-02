#pragma once

#include <stdint.h>
#include <stdbool.h>

#define BINARY_STREAM_MODE 1

#if BINARY_STREAM_MODE
#define DBG(...)
#define DBGLN(...)
#else
#define DBG(...)    Serial.print(__VA_ARGS__)
#define DBGLN(...)  Serial.println(__VA_ARGS__)
#endif

// Unified Thermal Node binary transport protocol
// Packet format:
//   0x55, 0xAA, TYPE, FRAME_ID_LE, LENGTH_LE, PAYLOAD, CRC8
// CRC8 covers TYPE+FRAME_ID+LENGTH+PAYLOAD.
// Sensor types:
//   0x01 = MLX90640 frame: optional metadata + 768 int16 pixels
//   0x02 = SMH-01B01 raw frame (64 int16 pixels, unit = 0.1 deg C)
//   0x03 = Omron D6T 4x4 raw frame (16 uint16 x0.1C) + raw max x0.1C + max position
//   0x04 = Omron D6T status counters (6 uint32 values)
// MLX90640 extended metadata layout:
//   subpage: 1 byte
//   status_raw: 2 bytes
//   ptat_art_raw: 2 bytes
//   ptat_raw: 2 bytes
//   vdd_raw: 2 bytes
//   gain_raw: 2 bytes
//   cp_sp0_raw: 2 bytes
//   cp_sp1_raw: 2 bytes

#define PROTO_SYNC_0          0x55
#define PROTO_SYNC_1          0xAA

#define PROTO_TYPE_MLX90640   0x01
#define PROTO_TYPE_SMH01B01   0x02
#define PROTO_TYPE_D6T        0x03
#define PROTO_TYPE_D6T_STATUS 0x04

void protocolStartPacket(uint8_t type, uint16_t frame_id, uint16_t length);
void protocolWriteByte(uint8_t value);
void protocolWriteInt16(int16_t value);
void protocolWriteUInt16(uint16_t value);
void protocolWriteUInt32(uint32_t value);
void protocolWriteBytes(const uint8_t *data, uint16_t length);
void protocolFinishPacket(void);
