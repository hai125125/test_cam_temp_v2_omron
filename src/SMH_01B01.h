#ifndef _SMH_01B01_H_
#define _SMH_01B01_H_

#include "stdint.h"
#include "stdbool.h"

bool SMH_init(void);
bool SMH_readAmbient(float* tempC);
bool SMH_readall(uint16_t* temp_data);

#endif // _SMH_01B01_H_