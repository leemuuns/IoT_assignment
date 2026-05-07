// ================================================================
// COM3505 – Internet of Things Assignment
// ESP32 Device: Button Sensor + LED Patterns + Flask Server
//
// Features:
//   1. Wi-Fi connection (Station mode) + IP print
//   2. Button sensor reading (GPIO input)
//   3. HTTP POST → Python Flask server every 3 seconds
//   4. LED patterns: Blink, Chase, Rainbow, Fire
//   5. Pattern control via Flask server (poll /command)
// ================================================================

#include <WiFi.h>
#include <WebServer.h>
#include <WiFiClient.h>
#include <HTTPClient.h>

// ================================================================
const char* wifiSsid     = "Lizzz";
const char* wifiPassword = "12345678";
const char* serverHost   = "172.20.10.2";
const int   serverPort   = 9000;
// ================================================================

// ── LED Pins ─────────────────────────────────────────────────────
#define LED_R   6    // Red    LED → GPIO6
#define LED_Y   9    // Yellow LED → GPIO9
#define LED_G   12   // Green  LED → GPIO12

const int NUM_LEDS = 3;
const int LED_PINS[NUM_LEDS] = { LED_R, LED_Y, LED_G };

// ── Button Pin ───────────────────────────────────────────────────
#define BUTTON_PIN 5   // Push button → GPIO5 (INPUT_PULLUP)

// ── Pattern IDs ──────────────────────────────────────────────────
#define PAT_BLINK    0
#define PAT_CHASE    1
#define PAT_RAINBOW  2
#define PAT_FIRE     3

// ── Global State ─────────────────────────────────────────────────
int  currentPattern   = PAT_BLINK;
int  buttonState      = 0;
int  buttonPressCount = 0;

unsigned long lastSendTime    = 0;
unsigned long lastPatternTime = 0;
unsigned long lastPollTime    = 0;

const unsigned long SEND_INTERVAL = 3000;  // POST every 3 s
const unsigned long POLL_INTERVAL = 2000;  // Poll command every 2 s

// Pattern animation state
int  chaseIndex   = 0;
int  rainbowIndex = 0;
bool blinkState   = false;

// ================================================================
// Wi-Fi Connection
// ================================================================
void connectWiFi() {
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(wifiSsid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid, wifiPassword);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - start > 40000) {
      Serial.println("\n[ERROR] Wi-Fi timeout – restarting");
      ESP.restart();
    }
  }

  Serial.println("\n✓ Wi-Fi Connected!");
  Serial.print("  Device IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("  MAC: ");
  Serial.println(WiFi.macAddress());
}

// ================================================================
// HTTP POST /pattern -> Flask  (notify pattern change from button)
// Called when even press triggers auto pattern advance
// ================================================================
void postPatternUpdate(int newPattern) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = "http://" + String(serverHost) + ":" + String(serverPort) + "/pattern";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  String payload = "{\"pattern\":" + String(newPattern) + "}";
  int httpCode = http.POST(payload);

  if (httpCode > 0) {
    Serial.printf("[PATTERN] Notified Flask → pattern %d  HTTP %d\n", newPattern, httpCode);
  } else {
    Serial.printf("[PATTERN] Failed: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
}

// ================================================================
// Button Sensor Reading
// buttonState = 1 when pressed, 0 when released
//
// Auto pattern advance (optional feature):
// Every even press_count -> advance to next pattern
// Blink(0), Chase(1), Rainbow(2), Fire(3), Blink(0) ...
// ================================================================
void readSensor() {
  int raw = digitalRead(BUTTON_PIN);
  int newState = (raw == LOW) ? 1 : 0;  // INPUT_PULLUP: LOW = pressed

  if (newState == 1 && buttonState == 0) {
    buttonPressCount++;
    Serial.printf("[Sensor] Button pressed! Total presses: %d\n", buttonPressCount);

    // Even press -> advance to next pattern
    if (buttonPressCount % 2 == 0) {
      currentPattern = (currentPattern + 1) % 4;  // cycle 0->1->2->3->0
      resetPatternState();
      Serial.printf("[AUTO] Even press → Pattern advanced to %d\n", currentPattern);
      postPatternUpdate(currentPattern);  // notify Flask immediately
    }
  }
  buttonState = newState;
}

// ================================================================
// HTTP POST -> Flask
// JSON: { "button": 0, "press_count": 5, "pattern": 1 }
// ================================================================
void postSensorData() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = "http://" + String(serverHost) + ":" + String(serverPort) + "/data";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  String payload = "{";
  payload += "\"button\":"      + String(buttonState)      + ",";
  payload += "\"press_count\":" + String(buttonPressCount)  + ",";
  payload += "\"pattern\":"     + String(currentPattern);
  payload += "}";

  int httpCode = http.POST(payload);

  if (httpCode > 0) {
    Serial.printf("[POST] Sent → %s  HTTP %d\n", url.c_str(), httpCode);
  } else {
    Serial.printf("[POST] Failed: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
}

// ================================================================
// HTTP GET /command <- Flask  (pattern control from browser)
// Response: plain text "0"–"3"
// ================================================================
void pollCommand() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = "http://" + String(serverHost) + ":" + String(serverPort) + "/command";
  http.begin(url);

  int httpCode = http.GET();
  if (httpCode == 200) {
    String body = http.getString();
    body.trim();
    int newPattern = body.toInt();
    if (newPattern >= 0 && newPattern <= 3 && newPattern != currentPattern) {
      currentPattern = newPattern;
      Serial.printf("[CMD] Pattern changed to %d\n", currentPattern);
      resetPatternState();
    }
  }
  http.end();
}

// ================================================================
// Reset animation state when pattern switches
// ================================================================
void resetPatternState() {
  chaseIndex   = 0;
  rainbowIndex = 0;
  blinkState   = false;
  for (int i = 0; i < NUM_LEDS; i++) digitalWrite(LED_PINS[i], LOW);
}

// ================================================================
// LED Pattern Engine
// ================================================================

// ── BLINK: all LEDs toggle every 500 ms ─────────────────────────
void patternBlink() {
  unsigned long now = millis();
  if (now - lastPatternTime < 500) return;
  lastPatternTime = now;

  blinkState = !blinkState;
  for (int i = 0; i < NUM_LEDS; i++)
    digitalWrite(LED_PINS[i], blinkState ? HIGH : LOW);
}

// ── CHASE: one LED at a time, moves forward ──────────────────────
void patternChase() {
  unsigned long now = millis();
  if (now - lastPatternTime < 300) return;
  lastPatternTime = now;

  for (int i = 0; i < NUM_LEDS; i++)
    digitalWrite(LED_PINS[i], (i == chaseIndex) ? HIGH : LOW);

  chaseIndex = (chaseIndex + 1) % NUM_LEDS;
}

// ── RAINBOW: cycle R->Y->G->R repeatedly ───────────────────────────
void patternRainbow() {
  unsigned long now = millis();
  if (now - lastPatternTime < 400) return;
  lastPatternTime = now;

  const int seq[3][3] = {
    {1,0,0},  // R
    {0,1,0},  // Y
    {0,0,1},  // G
  };

  for (int i = 0; i < NUM_LEDS; i++)
    digitalWrite(LED_PINS[i], seq[rainbowIndex][i] ? HIGH : LOW);

  rainbowIndex = (rainbowIndex + 1) % 3;
}

// ── FIRE/FLAME: random flicker with warm-colour bias ─────────────
// Red flickers fast, Yellow flickers slower, Green stays off
void patternFire() {
  unsigned long now = millis();
  if (now - lastPatternTime < 80) return;
  lastPatternTime = now;

  // Weighted random for "warm" effect
  int r = random(0, 10);

  if (r < 6) {
    // 60%: Red on, Yellow random, Green off
    digitalWrite(LED_R, HIGH);
    digitalWrite(LED_Y, (random(0,2) == 0) ? HIGH : LOW);
    digitalWrite(LED_G, LOW);
  } else if (r < 9) {
    // 30%: Red only
    digitalWrite(LED_R, HIGH);
    digitalWrite(LED_Y, LOW);
    digitalWrite(LED_G, LOW);
  } else {
    // 10%: all off -> ember effect
    digitalWrite(LED_R, LOW);
    digitalWrite(LED_Y, LOW);
    digitalWrite(LED_G, LOW);
  }
}

// Dispatch to active pattern
void runPattern() {
  switch (currentPattern) {
    case PAT_BLINK:   patternBlink();   break;
    case PAT_CHASE:   patternChase();   break;
    case PAT_RAINBOW: patternRainbow(); break;
    case PAT_FIRE:    patternFire();    break;
    default:          patternBlink();   break;
  }
}

// ================================================================
// setup()
// ================================================================
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\n=== COM3505 IoT Assignment – ESP32 Start ===");

  // LED pins as OUTPUT
  for (int i = 0; i < NUM_LEDS; i++) {
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
  }

  // Button pin as INPUT with internal pull-up
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Connect to Wi-Fi
  connectWiFi();

  // Startup chase to confirm LEDs working
  for (int rep = 0; rep < 2; rep++) {
    for (int i = 0; i < NUM_LEDS; i++) {
      for (int j = 0; j < NUM_LEDS; j++)
        digitalWrite(LED_PINS[j], j == i ? HIGH : LOW);
      delay(200);
    }
  }
  for (int i = 0; i < NUM_LEDS; i++) digitalWrite(LED_PINS[i], LOW);

  Serial.println("=== Setup complete. Entering loop. ===\n");
}

// ================================================================
// loop()
// ================================================================
void loop() {
  unsigned long now = millis();

  // 1. Read button every loop
  readSensor();

  // 2. POST sensor data to Flask every 3 seconds
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;
    postSensorData();
  }

  // 3. Poll Flask for pattern command every 2 seconds
  if (now - lastPollTime >= POLL_INTERVAL) {
    lastPollTime = now;
    pollCommand();
  }

  // 4. Run active LED pattern
  runPattern();
}
