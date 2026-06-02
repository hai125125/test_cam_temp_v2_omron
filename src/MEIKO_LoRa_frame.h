#include <stdint.h>

typedef struct
{
    float value;
    uint8_t loc_x;
    uint8_t loc_y;
} temperature_camera;

void LoRa_frame_init(void);
void NTC_framing(float* send_value, uint8_t* framed_data);
void Temperature_Camera_framing(temperature_camera sen, uint8_t* framed_data);
void Info_framing(float mcu_temp, float f_vcc, uint8_t* framed_data);

bool get_send_info_flag(void);
