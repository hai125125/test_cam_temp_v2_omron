#ifndef _OMRON_D6T_H_
#define _OMRON_D6T_H_

#include "stdint.h"
#include "stdbool.h"

// typedef struct
// {
//     float PTAT_temp;
//     float pix_temp[16];
//     float min_temp;
//     float max_temp;
//     float average_temp;
//     uint8_t max_X;
//     uint8_t max_Y;
//     uint8_t PEC;
// } D6T;

void D6T_init(void);
bool D6T_readall(uint16_t* temp_data);

extern uint32_t d6t_read_attempt_count;
extern uint32_t d6t_read_success_count;
extern uint32_t d6t_read_fail_count;
extern uint32_t d6t_pec_fail_count;
extern uint32_t d6t_request_len_fail_count;
extern uint32_t d6t_endtx_fail_count;

#endif // _OMRON_D6T_H_
