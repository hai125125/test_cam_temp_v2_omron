#include <Arduino.h>
#include <Wire.h>

// Lightweight MLX90640 EEPROM dump utility for ATmega2560.
// This firmware reads the sensor's factory calibration EEPROM and streams
// the 832 uint16 words over Serial at 921600 baud.
//
// Memory optimization:
//  - Uses a single fixed 32-byte raw buffer matching Wire's AVR buffer.
//  - No large arrays or dynamic allocations.
//  - Each word is printed immediately, so we do not store the full dump in SRAM.
//
// Why chunked reads?
//  - AVR Wire library on Arduino Mega has a 32-byte I2C buffer.
//  - MLX90640 EEPROM words are 2 bytes each, so 16 words = 32 bytes.
//  - Larger reads would overflow the buffer and fail on AVR.
//
// Why EEPROM is required:
//  - Each MLX90640 sensor has unique factory calibration values.
//  - The EEPROM parameters are needed to convert raw frame data into
//    accurate temperatures in PC-side thermography processing.

#define MLX90640_I2C_ADDR         0x33
#define MLX90640_EEPROM_START     0x2400
#define MLX90640_EEPROM_WORDS     832
#define MLX90640_CHUNK_WORDS      16
#define MLX90640_CHUNK_BYTES      (MLX90640_CHUNK_WORDS * 2)
#define SERIAL_BAUD               921600

static bool setEepromAddress(uint16_t address)
{
    Wire.beginTransmission(MLX90640_I2C_ADDR);
    Wire.write((uint8_t)(address >> 8));
    Wire.write((uint8_t)(address & 0xFF));
    return Wire.endTransmission(false) == 0;
}

static bool readEepromChunk(uint16_t address, uint16_t words)
{
    uint8_t buffer[MLX90640_CHUNK_BYTES];
    if (words > MLX90640_CHUNK_WORDS)
    {
        words = MLX90640_CHUNK_WORDS;
    }

    const uint8_t bytesToRead = (uint8_t)(words * 2);
    if (!setEepromAddress(address))
    {
        Serial.println(F("# EEPROM_ADDR_FAIL"));
        return false;
    }

    if (Wire.requestFrom((uint8_t)MLX90640_I2C_ADDR, bytesToRead) != bytesToRead)
    {
        Serial.println(F("# EEPROM_READ_FAIL"));
        return false;
    }

    for (uint8_t i = 0; i < bytesToRead; ++i)
    {
        if (!Wire.available())
        {
            Serial.println(F("# EEPROM_SHORT_READ"));
            return false;
        }
        buffer[i] = Wire.read();
    }

    for (uint16_t w = 0; w < words; ++w)
    {
        uint16_t value = (uint16_t)buffer[w * 2] | ((uint16_t)buffer[w * 2 + 1] << 8);
        Serial.println(value);
    }

    return true;
}

static bool dumpEeprom()
{
    Serial.println(F("<EEPROM_BEGIN>"));

    uint16_t address = MLX90640_EEPROM_START;
    uint16_t remaining = MLX90640_EEPROM_WORDS;

    while (remaining > 0)
    {
        uint16_t chunkWords = remaining > MLX90640_CHUNK_WORDS
            ? MLX90640_CHUNK_WORDS
            : remaining;

        if (!readEepromChunk(address, chunkWords))
        {
            Serial.println(F("# EEPROM_DUMP_ABORT"));
            return false;
        }

        address += chunkWords;
        remaining -= chunkWords;
    }

    Serial.println(F("<EEPROM_END>"));
    return true;
}

void setup()
{
    Serial.begin(SERIAL_BAUD);
    delay(250);

    Wire.begin();
    Wire.setClock(400000);

    Serial.println(F("# MLX90640 EEPROM DUMP UTILITY"));
    Serial.println(F("# I2C=0x33, EEPROM=0x2400..0x273F, 832 words"));

    if (!dumpEeprom())
    {
        Serial.println(F("# DUMP FAILED"));
    }
    else
    {
        Serial.println(F("# DUMP COMPLETE"));
    }
}

void loop()
{
    // Empty loop: dump is completed in setup().
}
