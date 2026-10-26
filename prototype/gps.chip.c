// UART behavior model, not an RF/GNSS receiver simulation.
#include "wokwi-api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
  uart_dev_t uart;
  uint32_t speed, valid, seconds;
  double latitude;
  char output[160];
} chip_state_t;
static void tick(void *data) {
  chip_state_t *s = data;
  s->seconds++;
  double speed = attr_read_float(s->speed);
  // Synthetic northbound path; no claim of alignment with actual roads.
  s->latitude += speed / 3.6 / 111320.0;
  double absolute = -s->latitude;
  int degrees = (int)absolute;
  double minutes = (absolute - degrees) * 60.0;
  char body[128];
  unsigned t = s->seconds % 86400;
  snprintf(body, sizeof(body), "GPRMC,%02u%02u%02u.00,%c,%02d%07.4f,S,05822.8960,W,%.2f,000.0,251026,,,A",
    t/3600, (t/60)%60, t%60, attr_read(s->valid) ? 'A' : 'V', degrees, minutes, speed/1.852);
  unsigned checksum = 0;
  for (unsigned i = 0; body[i]; i++) checksum ^= (unsigned char)body[i];
  snprintf(s->output, sizeof(s->output), "$%s*%02X\r\n", body, checksum);
  uart_write(s->uart, (uint8_t *)s->output, strlen(s->output));
}
void chip_init(void) {
  chip_state_t *s = calloc(1, sizeof(*s));
  s->latitude = -34.6037;
  s->speed = attr_init_float("speedKmh", 32);
  s->valid = attr_init("fixValid", 1);
  const uart_config_t uart = {
    .tx = pin_init("TX", INPUT_PULLUP), .rx = pin_init("RX", INPUT),
    .baud_rate = 9600, .user_data = s
  };
  s->uart = uart_init(&uart);
  const timer_config_t timer = {.callback = tick, .user_data = s};
  timer_t id = timer_init(&timer);
  timer_start(id, 1000000, true);
}
