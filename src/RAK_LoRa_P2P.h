#ifndef _RAK_LORA_P2P_H_
#define _RAK_LORA_P2P_H_

#include <Arduino.h>

#define FREQUENCY 920600000
#define SPREADING_FACTOR 7
#define BANDWITH 125
#define CODE_RATE 1
#define PREAMBLE 8
#define TXPOWER 11

void P2P_TX_default_init(void);
void P2P_RX_default_init(service_lora_p2p_recv_cb_type rccb);

#endif  /* _RAK_LORA_P2P_H_ */
