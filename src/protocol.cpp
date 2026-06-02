#include "protocol.h"
#include <Arduino.h>

static uint8_t s_crc8 = 0;

static uint8_t crc8_update(uint8_t crc, uint8_t byte)
{
    crc ^= byte;
    for (uint8_t i = 0; i < 8; i++) {
        crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
    return crc;
}

void protocolStartPacket(uint8_t type, uint16_t frame_id, uint16_t length)
{
    Serial.write(PROTO_SYNC_0);
    Serial.write(PROTO_SYNC_1);

    s_crc8 = 0;
    protocolWriteByte(type);
    protocolWriteUInt16(frame_id);
    protocolWriteUInt16(length);
}

void protocolWriteByte(uint8_t value)
{
    Serial.write(value);
    s_crc8 = crc8_update(s_crc8, value);
}

void protocolWriteInt16(int16_t value)
{
    protocolWriteByte((uint8_t)(value & 0xFF));
    protocolWriteByte((uint8_t)((value >> 8) & 0xFF));
}

void protocolWriteUInt16(uint16_t value)
{
    protocolWriteByte((uint8_t)(value & 0xFF));
    protocolWriteByte((uint8_t)((value >> 8) & 0xFF));
}

void protocolWriteUInt32(uint32_t value)
{
    protocolWriteByte((uint8_t)(value & 0xFF));
    protocolWriteByte((uint8_t)((value >> 8) & 0xFF));
    protocolWriteByte((uint8_t)((value >> 16) & 0xFF));
    protocolWriteByte((uint8_t)((value >> 24) & 0xFF));
}

void protocolWriteBytes(const uint8_t *data, uint16_t length)
{
    for (uint16_t i = 0; i < length; i++) {
        protocolWriteByte(data[i]);
    }
}

void protocolFinishPacket(void)
{
    Serial.write(s_crc8);
}
