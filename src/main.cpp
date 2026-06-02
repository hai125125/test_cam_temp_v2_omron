/*
 * ============================================================
 *  Multi-sensor Thermal Node — ATmega2560
 *  Shared I2C bus  (SDA=20, SCL=21)
 *
 *  Sensor        Addr    Speed    Driver
 *  SMH-01B01     0x0A   100kHz   SMH_01B01.cpp       (unchanged)
 *  MLX90640      0x33   400kHz   mlx_node.cpp        (acquisition node)
 *  D6T           0x0A   SoftI2C  OMRON_D6T.cpp
 *
 *  Architecture change vs previous version:
 *    BEFORE: MCU processes thermography → Serial ASCII results
 *    NOW:    MCU streams raw frames → Python does all processing
 *
 *  Serial: 921600 baud
 *    MLX90640 → unified binary packet
 *    SMH-01B01 → unified binary packet
 *    D6T       → unified binary packet
 * ============================================================
 */

#include <Arduino.h>
#include <Wire.h>

#include "SMH_01B01.h"
#include "test_MLX90640.h"
#include "OMRON_D6T.h"
#include "protocol.h"

// ── Địa chỉ I2C ─────────────────────────────────────────────
#define ADDR_SMH01B01  0x0A
#define ADDR_MLX90640  0x33
#define ADDR_D6T       0x0A

// ── Sensor flags ─────────────────────────────────────────────
static bool hasSMH01B01 = false;
static bool hasMLX90640 = false;
static bool hasD6T = true;

// ── SMH frame buffer (giữ nguyên như cũ) ────────────────────
static uint16_t smhTempData[64];
static uint16_t d6t_data[16];

// ── Frame counters cho ASCII packets ─────────────────────────
static uint16_t s_smhFrameId  = 0;
static uint16_t s_d6tFrameId  = 0;
static uint16_t s_d6tStatusFrameId = 0;

// ── Timers ───────────────────────────────────────────────────
static uint32_t s_lastSMH  = 0;
static uint32_t s_lastD6T  = 0;
static uint32_t s_lastD6TStatus = 0;

static void printHex8(uint8_t v)
{
    DBG(F("0x"));
    if (v < 0x10) DBG('0');
    DBG(v, HEX);
}

// ============================================================
// Scan I2C bus (giữ nguyên hoàn toàn)
// ============================================================

static void scanI2C()
{
    int found = 0;
    hasSMH01B01 = hasMLX90640 = false;
    hasD6T = true;

    DBGLN();
    DBGLN(F("I2C Scan (0x01-0x7F)"));
    DBGLN(F("---------------------"));

    Wire.setClock(100000);

    for (uint8_t addr = 0x01; addr <= 0x7F; addr++)
    {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() != 0) continue;

        DBG(F("  ["));
        printHex8(addr);
        DBG(F("] "));

        if      (addr == ADDR_SMH01B01) { hasSMH01B01 = true; }
        else if (addr == ADDR_MLX90640) { hasMLX90640 = true; }

        if      (addr == ADDR_SMH01B01) { DBG(F("SMH-01B01")); }
        else if (addr == ADDR_MLX90640) { DBG(F("MLX90640")); }
        else                             { DBG(F("Unknown")); }
        DBGLN();

        found++;
    }

    DBGLN(F("---------------------"));
    if (found == 0)
    {
        DBGLN(F("  No devices found!"));
        DBGLN(F("  Check wiring & pull-ups."));
    }
    else
    {
        DBG(F("  Total: "));
        DBG(found);
        DBGLN(F(" device(s)"));
    }
    DBGLN(F("====================="));
}

// ============================================================
// SMH-01B01
// Thay đổi: thay vì in Min/Avg/Ctr/Max → gửi ASCII packet
// để Python xử lý. Logic đọc SMH_readall() giữ nguyên.
// ============================================================

static void readSMH01B01()
{
    Wire.setClock(100000);

    Wire.beginTransmission(ADDR_SMH01B01);
    if (Wire.endTransmission() != 0)
    {
        DBGLN(F("# SMH_LOST"));
        hasSMH01B01 = false;
        return;
    }

    memset(smhTempData, 0, sizeof(smhTempData));
    if (!SMH_readall(smhTempData))
    {
        DBGLN(F("# SMH_READ_FAIL"));
        return;
    }

    protocolStartPacket(PROTO_TYPE_SMH01B01, s_smhFrameId++, 64 * 2);
    for (uint8_t i = 0; i < 64; i++)
    {
        protocolWriteUInt16(smhTempData[i]);
    }
    protocolFinishPacket();
}

static void readD6T()
{
    bool d6t_ok = D6T_readall(d6t_data);
    if (!d6t_ok)
    {
        DBGLN(F("# D6T_READ_FAIL"));
        return;
    }

    uint16_t max_raw = d6t_data[0];
    uint8_t max_index = 0;
    for (uint8_t i = 1; i < 16; i++)
    {
        if (d6t_data[i] > max_raw)
        {
            max_raw = d6t_data[i];
            max_index = i;
        }
    }

    uint8_t max_x = max_index % 4;
    uint8_t max_y = max_index / 4;
    uint16_t d6t_raw_max_x10 = max_raw;

    protocolStartPacket(PROTO_TYPE_D6T, s_d6tFrameId++, 16 * 2 + 4);
    for (uint8_t i = 0; i < 16; i++)
    {
        protocolWriteUInt16(d6t_data[i]);
    }
    protocolWriteUInt16(d6t_raw_max_x10);
    protocolWriteByte(max_x);
    protocolWriteByte(max_y);
    protocolFinishPacket();
}

static void sendD6TStatus()
{
    protocolStartPacket(PROTO_TYPE_D6T_STATUS, s_d6tStatusFrameId++, 6 * 4);
    protocolWriteUInt32(d6t_read_attempt_count);
    protocolWriteUInt32(d6t_read_success_count);
    protocolWriteUInt32(d6t_read_fail_count);
    protocolWriteUInt32(d6t_pec_fail_count);
    protocolWriteUInt32(d6t_request_len_fail_count);
    protocolWriteUInt32(d6t_endtx_fail_count);
    protocolFinishPacket();
}

// ============================================================
// Init sensors (cấu trúc giữ nguyên, chỉ đổi setupMLX90640)
// ============================================================

static bool initSensors()
{
    if (hasSMH01B01)
    {
        DBGLN(F("\n[INIT] SMH-01B01..."));
        Wire.setClock(100000);
        hasSMH01B01 = SMH_init();
        DBGLN(hasSMH01B01 ? F("  [OK]") : F("  [FAIL]"));
    }

    if (hasMLX90640)
    {
        DBGLN(F("\n[INIT] MLX90640..."));
        // mlxNodeSetup() tự setClock(400000) bên trong — giống cũ
        hasMLX90640 = mlxNodeSetup(ADDR_MLX90640);
        mlxNodeSetReady(hasMLX90640);   // enable polling loop
        DBGLN(hasMLX90640 ? F("  [OK]") : F("  [FAIL]"));
    }

    if (hasD6T)
    {
        DBGLN(F("\n[INIT] Omron D6T..."));
        D6T_init();
        DBGLN(F("  [OK]"));
    }

    return hasSMH01B01 || hasMLX90640 || hasD6T;
}

// ============================================================
// setup()
// Thay đổi duy nhất: Serial.begin(921600) thay vì 115200
// Lý do: MLX90640 frame = 1563 bytes, 2Hz → cần ≥50KB/s
//        921600 baud ≈ 92KB/s — đủ dư cho cả 3 sensor
// ============================================================

void setup()
{
    Serial.begin(921600);   // ← đổi từ 115200
    delay(1000);

    DBGLN(F("\n=== Thermal Node - ATmega2560 ==="));
    DBGLN(F("SDA=20  SCL=21  BAUD:921600"));
    DBGLN(F("# PROTOCOL: UNIFIED BINARY"));

    Wire.begin();
    Wire.setClock(100000);

    scanI2C();

    if (!initSensors())
    {
        DBGLN(F("\n[ERROR] No sensor found. Halting."));
        while (1) delay(1000);
    }

    DBGLN(F("\n# NODE_READY"));
}

// ============================================================
// loop()
// Thay đổi:
//   - MLX90640: mlxNodeLoop() thay readMLX90640()
//     → không blocking, poll data-ready flag
//   - SMH + D6T: có timer riêng, không dùng delay(1000)
//     → delay(1000) cũ bị xóa để mlxNodeLoop() không bị chặn
// ============================================================

void loop()
{
    // MLX90640: non-blocking, tự poll data-ready bên trong
    // Gửi binary packet khi có frame mới (~2Hz)
    if (hasMLX90640)
    {
        mlxNodeLoop(ADDR_MLX90640);
    }

    // Omron D6T: poll every 100ms.
    if (hasD6T && (millis() - s_lastD6T >= 100))
    {
        readD6T();
        s_lastD6T = millis();
    }

    // D6T debug counters are sent as binary status packets, not ASCII.
    if (hasD6T && (millis() - s_lastD6TStatus >= 1000))
    {
        sendD6TStatus();
        s_lastD6TStatus = millis();
    }

    // SMH-01B01: protocol ~1Hz — poll mỗi 1000ms
    if (hasSMH01B01 && (millis() - s_lastSMH >= 1000))
    {
        readSMH01B01();
        s_lastSMH = millis();
    }

    // Không có delay() cố định ở đây —
    // mlxNodeLoop() tự wait data-ready với timeout 1500ms
    // nên loop() không bao giờ spin quá nhanh
}
