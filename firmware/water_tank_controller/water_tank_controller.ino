/*
  Smart Water Tank Controller v2
  ESP32 + DFRobot A02YYUW (UART) + relay module -> 230 V contactor -> pump

  Arduino IDE, board package "esp32" by Espressif (2.x or 3.x)
  Library: PubSubClient by Nick O'Leary

  Wiring (guide, Fig. 3):
    Sensor red    -> 3V3          Sensor white  -> GPIO16 (RX2)
    Sensor black  -> GND          Sensor yellow -> GND (real-time output mode)
    Relay IN      -> GPIO23       Relay VCC -> 3V3, JD-VCC -> 5V, jumper removed
  Controller PCB (CONTROLLER_PCB 1): all of this is on the board, relay driver on GPIO32
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <esp_task_wdt.h>

// ===================== USER SETTINGS =====================
const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

#define USE_TLS 1                        // 1: HiveMQ Cloud on 8883   0: local Mosquitto on 1883
const char* MQTT_HOST = "your-cluster-id.s1.eu.hivemq.cloud";
const int   MQTT_PORT = 8883;
const char* MQTT_USER = "tank-device";
const char* MQTT_PASS = "CHANGE_ME";
const char* DEVICE_ID = "tank-esp32-CHANGE_ME";   // must be unique on the broker
#define TOPIC "home/CHANGE_ME/tank/"             // prefix of every topic

#define CONTROLLER_PCB 1                 // 1: custom controller PCB (transistor driver)  0: separate relay module
#define MONO_PCB 0                       // 1: monoblock board (door switch is read and published)
#if CONTROLLER_PCB
#define RELAY_PIN 32                     // PCB socket pin 10 of the VIN row
#define RELAY_ON  HIGH                   // PCB: driver on, pulldown keeps the relay off during boot
#define RELAY_OFF LOW
#else
#define RELAY_PIN 23
#define RELAY_ON  LOW                    // opto relay modules are usually active-LOW
#define RELAY_OFF HIGH
#endif
#define SENSOR_RX 16                     // ESP32 RX2 <- sensor WHITE wire
#define SENSOR_TX 17                     // unused: sensor YELLOW wire is tied to GND
#if MONO_PCB
#define SEL_AUTO_PIN 33                  // VIN-side pin 9. Door AUTO ties this to GND
#define SEL_MAN_PIN  25                  // VIN-side pin 8. Door MAN ties this to GND
#endif

const float D_EMPTY_MM = 1500;           // sensor reading at your 0 % level
const float D_FULL_MM  = 300;            // sensor reading at your 100 % level
const float ON_BELOW   = 20;             // auto mode starts the pump at or below this %
const float OFF_ABOVE  = 95;             // pump always stops at or above this %

const unsigned long MAX_RUN_MS     = 45UL * 60 * 1000;  // about 1.5x a normal 20 -> 95 % fill
const unsigned long RISE_WINDOW_MS = 5UL * 60 * 1000;   // dry-run check window
const float         MIN_RISE       = 2.0;               // % the level must rise in each window
const unsigned long MIN_OFF_MS     = 60UL * 1000;       // rest between starts, also after boot
const int           WDT_TIMEOUT_S  = 30;
// =========================================================

#if USE_TLS
WiFiClientSecure net;
#else
WiFiClient net;
#endif
PubSubClient mqtt(net);
Preferences prefs;

enum Latched { FAULT_NONE, FAULT_MAX_RUN, FAULT_DRY_RUN };
Latched latched = FAULT_NONE;            // cleared only by the reset command

bool autoMode = true, manualReq = false, pumpOn = false, sensorOk = false;
#if MONO_PCB
bool doorManual = false;
#endif
float level = -1, distanceMm = -1, riseRef = 0;
unsigned long pumpStart = 0, pumpStop = 0, riseRefAt = 0;
unsigned long lastPublish = 0, lastWifiTry = 0, lastMqttTry = 0;

void setPump(bool on) {
  if (on == pumpOn) return;
  if (on && millis() - pumpStop < MIN_OFF_MS) return;
  pumpOn = on;
  digitalWrite(RELAY_PIN, on ? RELAY_ON : RELAY_OFF);
  if (on) { pumpStart = riseRefAt = millis(); riseRef = level; }
  else pumpStop = millis();
  lastPublish = 0;
}

int readFrame() {                        // newest valid frame in the UART buffer, or -1
  uint8_t b[4];
  int mm = -1;
  while (Serial2.available() >= 4) {
    if (Serial2.peek() != 0xFF) { Serial2.read(); continue; }
    Serial2.readBytes(b, 4);
    if (((b[0] + b[1] + b[2]) & 0xFF) == b[3]) mm = (b[1] << 8) | b[2];
  }
  return mm;
}

float medianDistance() {                 // up to 9 readings within 2.5 s, median of the valid ones
  int v[9], n = 0;
  unsigned long t0 = millis();
  while (n < 9 && millis() - t0 < 2500) {
    int d = readFrame();
    if (d > 30 && d < 4500) v[n++] = d;
    delay(20);
    esp_task_wdt_reset();
    mqtt.loop();
  }
  if (n < 5) return -1;
  for (int i = 0; i < n - 1; i++)
    for (int j = i + 1; j < n; j++)
      if (v[j] < v[i]) { int t = v[i]; v[i] = v[j]; v[j] = t; }
  return v[n / 2];
}

const char* faultName() {
  if (latched == FAULT_MAX_RUN) return "max_run";
  if (latched == FAULT_DRY_RUN) return "dry_run";
  if (!sensorOk) return "sensor";
  return "none";
}

bool wantPump() {
  if (!sensorOk || latched != FAULT_NONE) return false;
  if (level >= OFF_ABOVE) { manualReq = false; return false; }
  if (manualReq) return true;
  return autoMode && (pumpOn || level <= ON_BELOW);
}

#if MONO_PCB
const char* doorPosition() {
  bool man = digitalRead(SEL_MAN_PIN) == LOW;
  bool aut = digitalRead(SEL_AUTO_PIN) == LOW;
  if (man && aut) return "INVALID";
  if (man) return "MANUAL";
  if (aut) return "AUTO";
  return "OFF";
}

void applyDoor() {
  const char* sel = doorPosition();
  if (strcmp(sel, "MANUAL") == 0) {
    digitalWrite(RELAY_PIN, RELAY_OFF);   // the door switch itself holds the coil on
    if (!pumpOn) { pumpOn = true; pumpStart = riseRefAt = millis(); riseRef = level; }
    doorManual = true;
    return;
  }
  if (strcmp(sel, "AUTO") != 0) {          // OFF or a wiring fault: coil supply is open
    digitalWrite(RELAY_PIN, RELAY_OFF);
    if (pumpOn) { pumpOn = false; pumpStop = millis(); }
    doorManual = false;
    return;
  }
  if (doorManual) {                        // just left MAN: rest the motor before AUTO may start it
    doorManual = false;
    if (pumpOn) { pumpOn = false; pumpStop = millis(); }
  }
  setPump(wantPump());
}
#endif

void checkRunTimers() {
  if (!pumpOn || !sensorOk) return;
  unsigned long now = millis();
  if (now - pumpStart > MAX_RUN_MS) {
    latched = FAULT_MAX_RUN;
  } else if (now - riseRefAt > RISE_WINDOW_MS) {
    if (level - riseRef < MIN_RISE) latched = FAULT_DRY_RUN;
    riseRef = level;
    riseRefAt = now;
  }
}

void onMessage(char* topic, byte* payload, unsigned int len) {
  String t = topic, m;
  for (unsigned int i = 0; i < len; i++) m += (char)payload[i];
  m.trim();
  m.toUpperCase();
  if (m.length() == 0) return;

  if (t == TOPIC "pump/set") {
    manualReq = (m == "ON");
    if (!manualReq) setPump(false);
  } else if (t == TOPIC "auto/set") {
    bool a = (m == "ON");
    if (a != autoMode) { autoMode = a; prefs.putBool("auto", autoMode); }
  } else if (t == TOPIC "reset") {
    latched = FAULT_NONE;
  }
  lastPublish = 0;
}

void publishState() {
  String lv = sensorOk ? String(level, 1) : String("-1");
  String dv = sensorOk ? String((int)distanceMm) : String("-1");
  mqtt.publish(TOPIC "level", lv.c_str(), true);
  mqtt.publish(TOPIC "distance", dv.c_str(), true);
  mqtt.publish(TOPIC "pump", pumpOn ? "ON" : "OFF", true);
  mqtt.publish(TOPIC "auto", autoMode ? "ON" : "OFF", true);
  mqtt.publish(TOPIC "fault", faultName(), true);
#if MONO_PCB
  mqtt.publish(TOPIC "selector", doorPosition(), true);
#endif
}

void maintainNetwork() {
  unsigned long now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastWifiTry > 30000) {
      lastWifiTry = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
    return;
  }
  if (mqtt.connected() || now - lastMqttTry < 5000) return;
  lastMqttTry = now;
  esp_task_wdt_reset();
  if (!mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS, TOPIC "status", 1, true, "offline")) return;

  mqtt.publish(TOPIC "status", "online", true);
  // Commands must never be retained, or the pump would restart on every reconnect.
  mqtt.publish(TOPIC "pump/set", "", true);
  mqtt.publish(TOPIC "auto/set", "", true);
  mqtt.publish(TOPIC "reset", "", true);
  mqtt.subscribe(TOPIC "pump/set");
  mqtt.subscribe(TOPIC "auto/set");
  mqtt.subscribe(TOPIC "reset");
  lastPublish = 0;
}

void setup() {
  digitalWrite(RELAY_PIN, RELAY_OFF);    // set the level first so the pin never drives the ON level
  pinMode(RELAY_PIN, OUTPUT);
#if MONO_PCB
  pinMode(SEL_AUTO_PIN, INPUT_PULLUP);
  pinMode(SEL_MAN_PIN, INPUT_PULLUP);
#endif
  Serial.begin(115200);
  Serial2.begin(9600, SERIAL_8N1, SENSOR_RX, SENSOR_TX);

  prefs.begin("tank", false);
  autoMode = prefs.getBool("auto", true);

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt = { .timeout_ms = WDT_TIMEOUT_S * 1000, .idle_core_mask = 0, .trigger_panic = true };
  esp_task_wdt_reconfigure(&wdt);
#else
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
#endif
  esp_task_wdt_add(NULL);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  lastWifiTry = millis();

#if USE_TLS
  net.setInsecure();                     // encrypted, but the broker certificate is not verified
  net.setHandshakeTimeout(8);
#endif
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(5);
}

void loop() {
  esp_task_wdt_reset();

  distanceMm = medianDistance();
  sensorOk = distanceMm > 0;
  if (sensorOk) {
    level = (D_EMPTY_MM - distanceMm) / (D_EMPTY_MM - D_FULL_MM) * 100.0;
    if (level < 0) level = 0;
    if (level > 100) level = 100;
  } else {
    level = -1;
  }

  checkRunTimers();
  if (latched != FAULT_NONE || !mqtt.connected()) manualReq = false;
#if MONO_PCB
  applyDoor();
#else
  setPump(wantPump());
#endif

  maintainNetwork();
  mqtt.loop();
  if (mqtt.connected() && millis() - lastPublish > 3000) {
    lastPublish = millis();
    publishState();
  }

#if MONO_PCB
  Serial.printf("dist=%d mm  level=%.1f %%  pump=%s  auto=%s  door=%s  fault=%s  wifi=%d  mqtt=%d\n",
                (int)distanceMm, level, pumpOn ? "ON" : "OFF", autoMode ? "ON" : "OFF",
                doorPosition(), faultName(), WiFi.status() == WL_CONNECTED, mqtt.connected());
#else
  Serial.printf("dist=%d mm  level=%.1f %%  pump=%s  auto=%s  fault=%s  wifi=%d  mqtt=%d\n",
                (int)distanceMm, level, pumpOn ? "ON" : "OFF", autoMode ? "ON" : "OFF",
                faultName(), WiFi.status() == WL_CONNECTED, mqtt.connected());
#endif
}
