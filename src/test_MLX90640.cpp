/*
 * mlx_node.cpp — MLX90640 Acquisition Node
 *
 * ATmega2560 role: raw I2C acquisition → Serial UART stream
 * All thermography processing is done on PC (Python).
 *
 * RAM usage:
 *   s_chunk[16]  int16   32 B   (I2C read buffer, chunk at a time)
 *   s_crc        uint16   2 B
 *   misc                ~20 B
 *   ─────────────────────────────
 *   Total               ~54 B   (vs ~6KB for full processing)
 *
 * No float, no paramsMLX90640, no frame buffer.
 */

#include "test_MLX90640.h"
#include "protocol.h"
#include <Arduino.h>
#include <Wire.h>

// ============================================================
// Registers
// ============================================================
#define MLX_STATUS_REG   0x8000
#define MLX_CTRL_REG1    0x800D
#define MLX_RAM_BASE     0x0400   // pixel RAM start
#define MLX_RAM_PTAT_ART 0x0700
#define MLX_RAM_PTAT     0x0720
#define MLX_RAM_VDD      0x072A
#define MLX_RAM_GAIN     0x070A
#define MLX_RAM_CP_SP0   0x0708
#define MLX_RAM_CP_SP1   0x0728

// ============================================================
// I2C helpers
// ============================================================
static bool mlxSetPtr(uint8_t addr, uint16_t reg)
{
    Wire.beginTransmission(addr);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)(reg & 0xFF));
    return Wire.endTransmission(false) == 0;
}

static bool mlxReadReg(uint8_t addr, uint16_t reg, int16_t &val)
{
    if (!mlxSetPtr(addr, reg)) return false;
    if (Wire.requestFrom(addr, (uint8_t)2) < 2) return false;
    uint8_t hi = Wire.read();
    uint8_t lo = Wire.read();
    val = (int16_t)(((uint16_t)hi << 8) | lo);
    return true;
}

static bool mlxWriteReg(uint8_t addr, uint16_t reg, uint16_t val)
{
    Wire.beginTransmission(addr);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)(reg & 0xFF));
    Wire.write((uint8_t)(val >> 8));
    Wire.write((uint8_t)(val & 0xFF));
    return Wire.endTransmission() == 0;
}

// ============================================================
// mlxNodeSetup
// ============================================================
bool mlxNodeSetup(uint8_t addr)
{
    Wire.setClock(400000);

    Wire.beginTransmission(addr);
    if (Wire.endTransmission() != 0) {
        DBGLN(F("[NODE] MLX90640 not found"));
        return false;
    }

    int16_t ctrl = 0;
    if (!mlxReadReg(addr, MLX_CTRL_REG1, ctrl)) {
        DBGLN(F("[NODE] CR1 read fail"));
        return false;
    }

    uint16_t c = (uint16_t)ctrl;
    c = (c & ~(uint16_t)(0x03 << 10)) | (uint16_t)(0x03 << 10); // 19-bit ADC (max)
    c = (c & ~(uint16_t)(0x07 <<  7)) | (uint16_t)(0x02 <<  7); // 2 Hz
    c |= (uint16_t)(1 << 12);                                     // chess mode

    if (!mlxWriteReg(addr, MLX_CTRL_REG1, c)) {
        DBGLN(F("[NODE] CR1 write fail"));
        return false;
    }

    DBG(F("[NODE] MLX90640 ready, CR1=0x"));
    DBGLN(c, HEX);
    return true;
}

// ============================================================
// sendFrame
// Streams one complete packet to Serial.
// Uses only a small read buffer — no full frame buffer.
// ============================================================
static void sendFrame(uint8_t addr, uint16_t frameId)
{
    int16_t statusRaw = 0;
    int16_t ptatArt   = 0;
    int16_t ptatRaw   = 0;
    int16_t vddRaw    = 0;
    int16_t gainRaw   = 0;
    int16_t cpSp0Raw  = 0;
    int16_t cpSp1Raw  = 0;
    uint8_t subpage   = 0;

    // Read required telemetry registers for PC-side reconstruction
    if (!mlxReadReg(addr, MLX_STATUS_REG, statusRaw)) {
        statusRaw = 0;
    }
    if (!mlxReadReg(addr, MLX_RAM_PTAT_ART, ptatArt)) {
        ptatArt = 0;
    }
    if (!mlxReadReg(addr, MLX_RAM_PTAT, ptatRaw)) {
        ptatRaw = 0;
    }
    if (!mlxReadReg(addr, MLX_RAM_VDD, vddRaw)) {
        vddRaw = 0;
    }
    if (!mlxReadReg(addr, MLX_RAM_GAIN, gainRaw)) {
        gainRaw = 0;
    }
    if (!mlxReadReg(addr, MLX_RAM_CP_SP0, cpSp0Raw)) {
        cpSp0Raw = 0;
    }
    if (!mlxReadReg(addr, MLX_RAM_CP_SP1, cpSp1Raw)) {
        cpSp1Raw = 0;
    }

    // MLX90640 subpage bit is encoded in the status register.
    // Use the LSB as the subpage indicator (0 or 1).
    subpage = (uint8_t)(statusRaw & 0x0001);

    const uint16_t metadataLen = 15;
    protocolStartPacket(PROTO_TYPE_MLX90640,
                        frameId,
                        metadataLen + NODE_PIXEL_COUNT * 2);

    protocolWriteByte(subpage);
    protocolWriteUInt16((uint16_t)statusRaw);
    protocolWriteInt16(ptatArt);
    protocolWriteInt16(ptatRaw);
    protocolWriteInt16(vddRaw);
    protocolWriteInt16(gainRaw);
    protocolWriteInt16(cpSp0Raw);
    protocolWriteInt16(cpSp1Raw);

    const uint8_t CHUNK = 16;

    if (!mlxSetPtr(addr, MLX_RAM_BASE)) {
        for (uint16_t i = 0; i < NODE_PIXEL_COUNT; i++) {
            protocolWriteInt16(0x7FFF);
        }
    } else {
        for (uint16_t offset = 0; offset < NODE_PIXEL_COUNT; offset += CHUNK)
        {
            uint8_t n = ((NODE_PIXEL_COUNT - offset) > CHUNK)
                        ? CHUNK
                        : (uint8_t)(NODE_PIXEL_COUNT - offset);

            if (offset > 0) {
                if (!mlxSetPtr(addr, MLX_RAM_BASE + offset)) {
                    for (uint16_t r = offset; r < NODE_PIXEL_COUNT; r++) {
                        protocolWriteInt16(0x7FFF);
                    }
                    goto send_crc;
                }
            }

            uint8_t got = Wire.requestFrom(addr, (uint8_t)(n * 2));
            if (got < (uint8_t)(n * 2)) {
                uint8_t received = got / 2;
                for (uint8_t i = 0; i < received; i++) {
                    uint8_t hi = Wire.read();
                    uint8_t lo = Wire.read();
                    protocolWriteInt16((int16_t)(((uint16_t)hi << 8) | lo));
                }
                for (uint16_t r = offset + received; r < NODE_PIXEL_COUNT; r++) {
                    protocolWriteInt16(0x7FFF);
                }
                goto send_crc;
            }

            for (uint8_t i = 0; i < n; i++) {
                uint8_t hi = Wire.read();
                uint8_t lo = Wire.read();
                protocolWriteInt16((int16_t)(((uint16_t)hi << 8) | lo));
            }
        }
    }

send_crc:
    protocolFinishPacket();
}

// ============================================================
// mlxNodeLoop
// ============================================================
static uint16_t s_frameId = 0;
static uint32_t s_lastSend = 0;
static bool     s_nodeReady = false;

void mlxNodeLoop(uint8_t addr)
{
    if (!s_nodeReady) return;

    Wire.setClock(400000);

    // ---- Wait for new frame (status bit 3) ------------------
    int16_t st = 0;
    if (!mlxReadReg(addr, MLX_STATUS_REG, st)) {
        DBGLN(F("[NODE] Lost"));
        s_nodeReady = false;
        return;
    }

    if (!(st & 0x0008)) return;  // not ready yet

    // Clear data-ready bit
    uint16_t stClear = (uint16_t)st & ~(uint16_t)0x0008;
    mlxWriteReg(addr, MLX_STATUS_REG, stClear);

    // ---- Send frame -----------------------------------------
    sendFrame(addr, s_frameId++);
    s_lastSend = millis();
}

// Allow main setup() to set ready flag
void mlxNodeSetReady(bool ready) { s_nodeReady = ready; }
