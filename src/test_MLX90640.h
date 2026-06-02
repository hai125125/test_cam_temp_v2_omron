#pragma once

/*
 * mlx_node.h — MLX90640 Acquisition Node Protocol
 *
 * Architecture:
 *   ATmega2560 = raw acquisition only
 *   PC/Python   = full Melexis thermography processing
 *
 * Serial packet format (binary-safe unified protocol):
 *
 *   HEADER      : 0x55 0xAA
 *   TYPE        : 1 byte  (0x01 = MLX90640)
 *   FRAME_ID    : 2 bytes little-endian
 *   LENGTH      : 2 bytes little-endian
 *   PAYLOAD     : variable
 *   CRC8        : 1 byte covering TYPE+FRAME_ID+LENGTH+PAYLOAD
 *
 * MLX90640 payload layout:
 *   subpage:      1 byte
 *   status_raw:   2 bytes int16_t  (status register 0x8000)
 *   ptat_art_raw: 2 bytes int16_t  (RAM 0x0700)
 *   ptat_raw:     2 bytes int16_t  (RAM 0x0720)
 *   vdd_raw:      2 bytes int16_t  (RAM 0x072A)
 *   gain_raw:     2 bytes int16_t  (RAM 0x070A)
 *   cp_sp0_raw:   2 bytes int16_t  (RAM 0x0708)
 *   cp_sp1_raw:   2 bytes int16_t  (RAM 0x0728)
 *   PIXELS:       1536 bytes (768 × int16_t, little-endian, row-major)
 *
 * Pixel mapping: index = row*32 + col  (row 0..23, col 0..31)
 */

#include <stdint.h>
#include <stdbool.h>

// Protocol constants
#define NODE_SYNC_0      0xAA
#define NODE_SYNC_1      0x55
#define NODE_SYNC_2      0xAA
#define NODE_SYNC_3      0x55
#define NODE_END_0       0xBB
#define NODE_END_1       0x66

#define NODE_PIXEL_COUNT 768
#define NODE_PACKET_PAYLOAD_START 2  // bytes after SYNC before CRC starts

// Sensor address (can be overridden for multi-sensor via TCA9548A)
#define MLX_DEFAULT_ADDR 0x33

bool mlxNodeSetup(uint8_t addr = MLX_DEFAULT_ADDR);
void mlxNodeLoop(uint8_t addr  = MLX_DEFAULT_ADDR);
void mlxNodeSetReady(bool ready);
