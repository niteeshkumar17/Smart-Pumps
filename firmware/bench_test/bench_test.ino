// NK Smart Pumps controller PCB - first bench test.
// USB only. Nothing connected to MAINS IN, SELECTOR, KM COIL or LAMP.
// Clicks the relay 2 s on / 2 s off and prints the sensor distance at 115200 baud.

#define RELAY_PIN 32
#define SENSOR_RX 16
#define SENSOR_TX 17

int readFrame() {
  uint8_t b[4];
  int mm = -1;
  while (Serial2.available() >= 4) {
    if (Serial2.peek() != 0xFF) { Serial2.read(); continue; }
    Serial2.readBytes(b, 4);
    if (((b[0] + b[1] + b[2]) & 0xFF) == b[3]) mm = (b[1] << 8) | b[2];
  }
  return mm;
}

void setup() {
  digitalWrite(RELAY_PIN, LOW);
  pinMode(RELAY_PIN, OUTPUT);
  Serial.begin(115200);
  Serial2.begin(9600, SERIAL_8N1, SENSOR_RX, SENSOR_TX);
  Serial.println("bench test: relay on GPIO32, sensor on GPIO16");
}

void loop() {
  static bool on = false;
  static unsigned long lastToggle = 0;
  static unsigned long lastFrame = 0;

  if (millis() - lastToggle >= 2000) {
    lastToggle = millis();
    on = !on;
    digitalWrite(RELAY_PIN, on ? HIGH : LOW);
    Serial.println(on ? "relay ON  (should click, RELAY LED lit)" : "relay OFF (RELAY LED dark)");
  }

  int mm = readFrame();
  if (mm >= 0) {
    lastFrame = millis();
    Serial.print("sensor ");
    Serial.print(mm);
    Serial.println(" mm");
  } else if (millis() - lastFrame > 3000) {
    lastFrame = millis();
    Serial.println("sensor: no data");
  }
  delay(100);
}
