// Wokwi custom chip: DFRobot A02YYUW ultrasonic level sensor looking down into a water tank.
// TX sends the sensor's frames (0xFF, distance high byte, low byte, checksum) at 9600 baud every 100 ms.
// RX is the sensor's mode pin (tied to GND for real-time output, as on the PCB).
// PUMP is HIGH while the contactor is pulled in. With simulate = 1 the water rises at fillRate while
// PUMP is HIGH and falls at useRate otherwise; with simulate = 0 the distance slider is sent as is.
// Display: the tank, the firmware's 20 % (yellow) and 95 % (orange) levels, pump running (top left,
// green) and the fault switches (top right: red = sensorFault, orange = dryRun).
#include "wokwi-api.h"
#include <stdlib.h>

#define TANK_MM 1600   // sensor to tank bottom
#define TOP_MM   250   // sensor to the highest possible water level (overflow)
#define ON_MM   1260   // firmware 20 % with D_EMPTY_MM 1500, D_FULL_MM 300
#define OFF_MM   360   // firmware 95 %

typedef struct {
  uart_dev_t uart;
  pin_t pump;
  uint32_t a_distance, a_simulate, a_fill, a_use, a_dry, a_fault;
  float dist;
  bool was_sim;
  buffer_t fb;
  uint32_t w, h;
  uint32_t *px;
} chip_state_t;

static uint32_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return 0xFF000000u | ((uint32_t)b << 16) | ((uint32_t)g << 8) | r;
}

static void rect(chip_state_t *c, int x0, int y0, int x1, int y1, uint32_t col) {
  for (int y = y0; y <= y1; y++)
    for (int x = x0; x <= x1; x++)
      if (x >= 0 && y >= 0 && x < (int)c->w && y < (int)c->h) c->px[y * c->w + x] = col;
}

static int level_y(float d) {
  return 15 + (int)((d - TOP_MM) * 99 / (TANK_MM - TOP_MM));
}

static void draw(chip_state_t *c, bool pump) {
  rect(c, 0, 0, c->w - 1, c->h - 1, rgb(18, 22, 28));
  rect(c, 10, 14, 69, 115, rgb(150, 160, 170));
  rect(c, 11, 15, 68, 114, rgb(30, 36, 44));
  rect(c, 11, level_y(c->dist), 68, 114, rgb(40, 120, 220));
  for (int x = 11; x <= 68; x += 4) {
    rect(c, x, level_y(ON_MM), x + 1, level_y(ON_MM), rgb(250, 210, 40));
    rect(c, x, level_y(OFF_MM), x + 1, level_y(OFF_MM), rgb(250, 120, 40));
  }
  rect(c, 34, 6, 45, 13, rgb(200, 200, 200));
  rect(c, 1, 1, 8, 8, pump ? rgb(40, 200, 80) : rgb(60, 66, 74));
  rect(c, 71, 1, 78, 8, attr_read(c->a_fault) ? rgb(230, 40, 40)
                        : attr_read(c->a_dry) ? rgb(250, 140, 30) : rgb(60, 66, 74));
  buffer_write(c->fb, 0, (uint8_t *)c->px, c->w * c->h * 4);
}

static void tick(void *user_data) {
  chip_state_t *c = user_data;
  bool sim = attr_read(c->a_simulate) != 0;
  bool pump = pin_read(c->pump) == HIGH;

  if (!sim || !c->was_sim) c->dist = (float)attr_read(c->a_distance);
  if (sim) {
    if (pump && !attr_read(c->a_dry)) c->dist -= attr_read(c->a_fill) * 0.1f;
    else c->dist += attr_read(c->a_use) * 0.1f;
    if (c->dist < TOP_MM) c->dist = TOP_MM;
    if (c->dist > TANK_MM) c->dist = TANK_MM;
  }
  c->was_sim = sim;

  if (!attr_read(c->a_fault)) {
    uint16_t mm = (uint16_t)c->dist;
    uint8_t f[4] = {0xFF, (uint8_t)(mm >> 8), (uint8_t)(mm & 0xFF), 0};
    f[3] = (uint8_t)(f[0] + f[1] + f[2]);
    uart_write(c->uart, f, 4);
  }
  draw(c, pump);
}

static void ignore_rx(void *user_data, uint8_t byte) {
  (void)user_data;
  (void)byte;
}

void chip_init(void) {
  chip_state_t *c = calloc(1, sizeof(chip_state_t));

  c->a_distance = attr_init("distance", 1300);
  c->a_simulate = attr_init("simulate", 1);
  c->a_fill = attr_init("fillRate", 15);
  c->a_use = attr_init("useRate", 4);
  c->a_dry = attr_init("dryRun", 0);
  c->a_fault = attr_init("sensorFault", 0);

  pin_init("VCC", INPUT);
  pin_init("GND", INPUT);
  c->pump = pin_init("PUMP", INPUT_PULLDOWN);

  const uart_config_t uart = {                // Wokwi's uart_init stalls the chip if rx is NO_PIN
    .user_data = c,
    .rx = pin_init("RX", INPUT),
    .rx_data = ignore_rx,
    .tx = pin_init("TX", INPUT_PULLUP),
    .baud_rate = 9600,
  };
  c->uart = uart_init(&uart);

  c->fb = framebuffer_init(&c->w, &c->h);
  c->px = malloc(c->w * c->h * 4);

  const timer_config_t timer = { .user_data = c, .callback = tick };
  timer_start(timer_init(&timer), 100000, true);
}
