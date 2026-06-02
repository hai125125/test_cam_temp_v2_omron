#include "OMRON_D6T.h"

#include <Arduino.h>
#include <SoftwareWire.h>

#if SOFTWAREWIRE_BUFSIZE < 35
#error "SoftwareWire RX buffer must be at least 35 bytes for Omron D6T"
#endif

#define D6T_ADDRESS 0x0A
#define D6T_CMD 0x4C
#define D6T_SDA_PIN 22
#define D6T_SCL_PIN 24
#define D6T_DEBUG 0
#define D6T_ENABLE_PEC_CHECK 0

static SoftwareWire d6tWire(D6T_SDA_PIN, D6T_SCL_PIN);

uint32_t d6t_read_attempt_count = 0;
uint32_t d6t_read_success_count = 0;
uint32_t d6t_read_fail_count = 0;
uint32_t d6t_pec_fail_count = 0;
uint32_t d6t_request_len_fail_count = 0;
uint32_t d6t_endtx_fail_count = 0;

#if D6T_DEBUG
static void D6T_debugHexByte(uint8_t value)
{
    if (value < 0x10)
    {
        Serial.print('0');
    }
    Serial.print(value, HEX);
}
#endif

#if D6T_ENABLE_PEC_CHECK
static uint8_t D6T_crc8Update(uint8_t crc, uint8_t data)
{
    crc ^= data;
    for (uint8_t i = 0; i < 8; i++)
    {
        crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
    return crc;
}

static bool D6T_checkPEC(const uint8_t *data, uint8_t len)
{
    if (len < 2)
    {
        return false;
    }

    uint8_t crc = 0;
    crc = D6T_crc8Update(crc, (uint8_t)((D6T_ADDRESS << 1) | 1));
    for (uint8_t i = 0; i < len - 1; i++)
    {
        crc = D6T_crc8Update(crc, data[i]);
    }
    return crc == data[len - 1];
}
#endif

void D6T_init(void)
{
    d6tWire.begin();
#if D6T_DEBUG
    Serial.print(F("[D6T] SoftI2C pins: SDA="));
    Serial.print(D6T_SDA_PIN);
    Serial.print(F(" SCL="));
    Serial.println(D6T_SCL_PIN);
#endif
    delay(100);
}

bool D6T_readall(uint16_t *temp_data)
{
    d6t_read_attempt_count++;

    for (int i = 0; i < 16; i++)
    {
        temp_data[i] = 0;
    }

    d6tWire.beginTransmission(D6T_ADDRESS); // I2C slave address
    d6tWire.write(D6T_CMD);                 // D6T register
    uint8_t tx_result = d6tWire.endTransmission();
#if D6T_DEBUG
    Serial.print(F("[D6T] endTransmission result = "));
    Serial.println(tx_result);
#endif
    if (tx_result != 0)
    {
#if D6T_DEBUG
        Serial.println(F("[D6T] write command failed"));
#endif
        d6t_endtx_fail_count++;
        d6t_read_fail_count++;
        return false;
    }
    delay(100);

    uint8_t received = d6tWire.requestFrom((uint8_t)D6T_ADDRESS, (uint8_t)35);
#if D6T_DEBUG
    Serial.print(F("[D6T] requestFrom bytes = "));
    Serial.print(received);
    Serial.print(F(" available = "));
    Serial.println(d6tWire.available());
#endif
    if (received != 35 || d6tWire.available() < 35)
    {
#if D6T_DEBUG
        Serial.println(F("[D6T] short read"));
#endif
        d6t_request_len_fail_count++;
        d6t_read_fail_count++;
        return false;
    }

    uint8_t buf[35];
    memset(buf, 0, 35);
    for (int i = 0; i < 35; i++)
    {
        buf[i] = d6tWire.read();
    }

#if D6T_DEBUG
    Serial.print(F("[D6T] raw bytes = "));
    for (int i = 0; i < 35; i++)
    {
        D6T_debugHexByte(buf[i]);
        if (i < 34)
        {
            Serial.print(' ');
        }
    }
    Serial.println();
#endif

#if D6T_ENABLE_PEC_CHECK
    if (!D6T_checkPEC(buf, 35))
    {
#if D6T_DEBUG
        Serial.print(F("[D6T] PEC mismatch, pec=0x"));
        D6T_debugHexByte(buf[34]);
        Serial.println();
#endif
        d6t_pec_fail_count++;
    }
#endif

    for (int i = 0; i < 16; i++)
    {
        temp_data[i] = (uint16_t)buf[2 + i * 2] | ((uint16_t)buf[3 + i * 2] << 8);
    }

#if D6T_DEBUG
    uint16_t min_raw = temp_data[0];
    uint16_t max_raw = temp_data[0];
    uint32_t total_raw = temp_data[0];
    uint8_t max_index = 0;

    Serial.print(F("[D6T] pixels raw x10 = "));
    Serial.print(temp_data[0]);
    for (int i = 1; i < 16; i++)
    {
        Serial.print(' ');
        Serial.print(temp_data[i]);
        if (temp_data[i] < min_raw)
        {
            min_raw = temp_data[i];
        }
        if (temp_data[i] > max_raw)
        {
            max_raw = temp_data[i];
            max_index = i;
        }
        total_raw += temp_data[i];
    }
    Serial.println();

    Serial.print(F("[D6T] max_raw="));
    Serial.print(max_raw);
    Serial.print(F(" max_c="));
    Serial.print(max_raw / 10.0f, 1);
    Serial.print(F(" min_c="));
    Serial.print(min_raw / 10.0f, 1);
    Serial.print(F(" avg_c="));
    Serial.print((total_raw / 16.0f) / 10.0f, 1);
    Serial.print(F(" pos=("));
    Serial.print(max_index % 4);
    Serial.print(',');
    Serial.print(max_index / 4);
    Serial.println(F(")"));
#endif

    d6t_read_success_count++;
    return true;
}

// uint8_t calc_crc(uint8_t data)
// {
//     uint8_t temp;
//     for (int i = 0; i < 8; i++)
//     {
//         temp = data;
//         data <<= 1;
//         if (temp & 0x80)
//         {
//             data ^= 0x07;
//         }
//     }
//     return data;
// }

// bool D6T_checkCRC(uint8_t *data, uint8_t len)
// {
//     uint8_t crc = calc_crc((D6T_ADDRESS << 1) | 1);
//     for (uint8_t i = 0; i < len - 1; i++)
//     {
//         crc = calc_crc(*(data + i) ^ crc);
//     }
//     return (crc == *(data + len - 1));
// }

// D6T D6T_readall(void)
// {
//     D6T sen;
//     uint8_t buflen;
//     uint8_t read_buf[35];

//     i2c_omron.beginTransmission(D6T_ADDRESS);
//     i2c_omron.write(D6T_CMD);

//     if (i2c_omron.endTransmission() != 0)
//     {
//         sen.max_temp = 10000;
//         return sen;
//     }

//     buflen = i2c_omron.requestFrom(D6T_ADDRESS, 35);

//     if (buflen != 35)
//     {
//         sen.max_temp = 10000;
//         return sen;
//     }

//     memset(read_buf, 0, buflen);

//     for (uint8_t i = 0; i < buflen; i++)
//     {
//         read_buf[i] = i2c_omron.read();
//     }

//     // Kiểm tra CRC
//     if (D6T_checkCRC(read_buf, 35))
//     {
//         sen.PTAT_temp = (256 * read_buf[1] + read_buf[0]) / 10;
//         sen.pix_temp[0] = (256 * read_buf[3] + read_buf[2]) / 10;
//         sen.min_temp = sen.pix_temp[0];
//         sen.max_temp = sen.pix_temp[0];
//         sen.average_temp = sen.pix_temp[0];

//         for (uint8_t i = 1; i < 16; i++)
//         {
//             sen.pix_temp[i] = (float)(256 * read_buf[2 * i + 3] + read_buf[2 * i + 2]) / 10;
//             if (sen.max_temp < sen.pix_temp[i])
//             {
//                 sen.max_temp = sen.pix_temp[i];
//                 sen.max_X = i / 4;
//                 sen.max_Y = i % 4;
//             }
//             if (sen.min_temp > sen.pix_temp[i])
//                 sen.min_temp = sen.pix_temp[i];
//             sen.average_temp += sen.pix_temp[i];
//         }
//         sen.average_temp /= 16;

//         if (sen.average_temp > 10)
//         {
//             sen.PEC = 0; // không có lỗi
//         }
//         else
//         {
//             sen.PEC = 2; // nhiệt độ không hợp lệ
//         }
//     }
//     else
//     {
//         sen.max_temp = 10001;
//         sen.PEC = 1;  // Lỗi CRC
//     }

//     return sen;
// }
