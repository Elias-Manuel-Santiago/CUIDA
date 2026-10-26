// A bounded subset of SIMCom AT/HTTP behavior. No socket, radio, or server.
#include "wokwi-api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
  uart_dev_t uart;
  uint32_t connected;
  char command[512], output[512];
  unsigned used, remaining, payload_used;
  char payload[2048];
  bool initialized;
} chip_state_t;
static void reply(chip_state_t *s, const char *text) {
  snprintf(s->output, sizeof(s->output), "%s", text);
  if (!uart_write(s->uart, (uint8_t *)s->output, strlen(s->output)))
    printf("MODEM MODEL: response dropped while UART busy\n");
}
static void command(chip_state_t *s) {
  const char *c = s->command;
  if (!strcmp(c, "AT") || !strcmp(c, "ATE0") || !strcmp(c, "AT+CNMP=38")) reply(s, "\r\nOK\r\n");
  else if (!strcmp(c, "AT+CPIN?")) reply(s, "\r\n+CPIN: READY\r\n\r\nOK\r\n");
  else if (!strcmp(c, "AT+CEREG?")) reply(s, attr_read(s->connected) ? "\r\n+CEREG: 0,1\r\n\r\nOK\r\n" : "\r\n+CEREG: 0,2\r\n\r\nOK\r\n");
  else if (!strncmp(c, "AT+CGDCONT=", 11)) reply(s, "\r\nOK\r\n");
  else if (!strcmp(c, "AT+HTTPTERM")) { s->initialized = false; reply(s, "\r\nOK\r\n"); }
  else if (!strcmp(c, "AT+HTTPINIT")) { s->initialized = true; reply(s, "\r\nOK\r\n"); }
  else if (!s->initialized || !attr_read(s->connected)) reply(s, "\r\nERROR\r\n");
  else if (!strncmp(c, "AT+HTTPPARA=", 12)) reply(s, "\r\nOK\r\n");
  else if (!strncmp(c, "AT+HTTPDATA=", 12)) {
    int n = atoi(c + 12);
    if (n < 1 || n >= (int)sizeof(s->payload)) { reply(s, "\r\nERROR\r\n"); return; }
    s->remaining = n; s->payload_used = 0;
    reply(s, "\r\nDOWNLOAD\r\n");
  } else if (!strcmp(c, "AT+HTTPACTION=1")) {
    printf("SIMULATED RECEIVER (no internet): %s\n", s->payload);
    reply(s, "\r\nOK\r\n\r\n+HTTPACTION: 1,200,0\r\n");
  } else reply(s, "\r\nERROR\r\n");
}
static void rx(void *data, uint8_t byte) {
  chip_state_t *s = data;
  if (s->remaining) {
    s->payload[s->payload_used++] = byte;
    if (!--s->remaining) {
      s->payload[s->payload_used] = 0;
      reply(s, "\r\nOK\r\n");
    }
    return;
  }
  if (byte == '\r') return;
  if (byte == '\n') {
    s->command[s->used] = 0;
    if (s->used) command(s);
    s->used = 0;
  } else if (s->used < sizeof(s->command)-1) s->command[s->used++] = byte;
  else { s->used = 0; reply(s, "\r\nERROR\r\n"); }
}
void chip_init(void) {
  chip_state_t *s = calloc(1, sizeof(*s));
  s->connected = attr_init("connected", 1);
  const uart_config_t uart = {
    .tx = pin_init("TXD", INPUT_PULLUP), .rx = pin_init("RXD", INPUT),
    .baud_rate = 115200, .rx_data = rx, .user_data = s
  };
  s->uart = uart_init(&uart);
}
