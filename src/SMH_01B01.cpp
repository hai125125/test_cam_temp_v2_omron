#include "SMH_01B01.h"

#include "protocol.h"
#include <Arduino.h>
#include <Wire.h>
#include <string.h>

#define SMH_ADDRESS 0x0A

#define SMH_CMD_START 0x01
#define SMH_CMD_READ_IR 0x02
#define SMH_CMD_CONFIG 0xF7
#define SMH_CONFIG_VALUE 0x9A

#define SMH_MAX_BAD_PIXELS 10
#define SMH_MAX_RETRY 3
#define SMH_FRAME_BYTES 128

static bool SMH_writeConfig(uint8_t value)
{
    Wire.beginTransmission(SMH_ADDRESS);
    Wire.write(SMH_CMD_CONFIG);
    Wire.write(value);
    return Wire.endTransmission() == 0;
}

static bool SMH_readConfig(uint8_t *value)
{
    Wire.beginTransmission(SMH_ADDRESS);
    Wire.write(SMH_CMD_CONFIG);
    if (Wire.endTransmission() != 0)
    {
        return false;
    }

    if (Wire.requestFrom((uint8_t)SMH_ADDRESS, (uint8_t)1) != 1)
    {
        return false;
    }

    *value = Wire.read();
    return true;
}

bool SMH_init(void)
{
    Wire.setClock(100000);
    Wire.begin();
    delay(100);

    return true;
}

bool SMH_readAmbient(float* tempC)
{
    Wire.beginTransmission(SMH_ADDRESS);
    Wire.write(0x03); // Ambient temperature command
    if (Wire.endTransmission() != 0)
    {
        return false;
    }

    delay(50);
    if (Wire.requestFrom((uint8_t)SMH_ADDRESS, (uint8_t)2) != 2)
    {
        return false;
    }

    uint8_t lo = Wire.read();
    uint8_t hi = Wire.read();
    int16_t raw = (int16_t)((hi << 8) | lo);
    *tempC = raw / 10.0f;
    return true;
}

static bool SMH_read_raw(uint8_t *buf)
{
    while (Wire.available())
    {
        Wire.read();
    }

    if (!SMH_writeConfig(SMH_CONFIG_VALUE))
    {
        DBGLN("[SMH-01B01] config write failed");
        return false;
    }
    delay(100);

    uint8_t cfg = 0;
    if (!SMH_readConfig(&cfg))
    {
        DBGLN("[SMH-01B01] config readback failed");
        return false;
    }

    DBG("[SMH-01B01] config F7=0x");
    DBG(cfg, HEX);
    DBGLN(cfg == SMH_CONFIG_VALUE ? " (OK)" : " (UNEXPECTED)");

    if (cfg != SMH_CONFIG_VALUE)
    {
        return false;
    }

    delay(500);

    Wire.beginTransmission(SMH_ADDRESS);
    Wire.write(SMH_CMD_READ_IR);
    if (Wire.endTransmission() != 0)
    {
        DBGLN("[SMH-01B01] command 0x02 failed");
        return false;
    }
    delay(100);

    uint8_t received = Wire.requestFrom((uint8_t)SMH_ADDRESS, (uint8_t)SMH_FRAME_BYTES);

    DBG("[SMH-01B01] frame received ");
    DBG(received);
    DBGLN(" byte");

    if (received != SMH_FRAME_BYTES)
    {
        DBG("[SMH-01B01] SHORT frame - received ");
        DBG(received);
        DBG("/");
        DBG(SMH_FRAME_BYTES);
        DBGLN(" byte");
        return false;
    }

    uint32_t timeout = millis();
    while (Wire.available() < SMH_FRAME_BYTES)
    {
        if (millis() - timeout > 500)
        {
            DBG("[SMH-01B01] TIMEOUT frame - ");
            DBG(Wire.available());
            DBG("/");
            DBG(SMH_FRAME_BYTES);
            DBGLN(" byte");
            return false;
        }
    }

    for (uint8_t i = 0; i < SMH_FRAME_BYTES; i++)
    {
        buf[i] = Wire.read();
    }

    return true;
}

bool SMH_readall(uint16_t *temp_data)
{
    memset(temp_data, 0, 64 * sizeof(uint16_t));

    uint8_t buf[128];
    for (uint8_t attempt = 0; attempt < SMH_MAX_RETRY; attempt++)
    {
        memset(buf, 0, sizeof(buf));

        if (!SMH_read_raw(buf)) return false;

        for (uint8_t i = 0; i < 64; i++)
        {
            int16_t rawSigned = (int16_t)((buf[i * 2 + 1] << 8) | buf[i * 2]);
            temp_data[i] = (uint16_t)rawSigned;
        }

        return true;
    }

    return false;
}
