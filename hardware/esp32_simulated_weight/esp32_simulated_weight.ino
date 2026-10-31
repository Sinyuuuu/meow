#include <Arduino.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <time.h>

#include "secrets.h"

constexpr float TEST_WEIGHTS_GRAMS[] = {120.0F, 119.0F, 117.0F, 115.0F, 110.0F};
constexpr size_t TEST_WEIGHT_COUNT =
    sizeof(TEST_WEIGHTS_GRAMS) / sizeof(TEST_WEIGHTS_GRAMS[0]);
constexpr uint32_t SEND_INTERVAL_MS = 2500;
constexpr uint8_t MAX_HTTP_ATTEMPTS = 3;
constexpr char FIRMWARE_VERSION[] = "catsense-esp32-sim-1.0.0";

Preferences preferences;
size_t weightIndex = 0;
bool pending = false;
bool completionPrinted = false;
uint64_t pendingSequence = 0;
String pendingPayload;
uint32_t lastAttemptAt = 0;

String jsonEscape(const String &value) {
  String escaped;
  escaped.reserve(value.length() + 8);
  for (size_t index = 0; index < value.length(); ++index) {
    const char character = value[index];
    if (character == '\\' || character == '"') {
      escaped += '\\';
    }
    escaped += character;
  }
  return escaped;
}

bool connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting Wi-Fi");
  for (int attempt = 0; attempt < 30; ++attempt) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println();
      Serial.print("Wi-Fi connected, IP: ");
      Serial.println(WiFi.localIP());
      return true;
    }
    Serial.print('.');
    delay(500);
  }
  Serial.println(" timeout");
  return false;
}

bool syncClock() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  struct tm timeInfo;
  for (int attempt = 0; attempt < 20; ++attempt) {
    if (getLocalTime(&timeInfo, 1000)) {
      Serial.println("NTP clock ready");
      return true;
    }
    delay(250);
  }
  Serial.println("NTP clock unavailable");
  return false;
}

String utcTimestamp() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 1000)) {
    return String();
  }
  char value[25];
  strftime(value, sizeof(value), "%Y-%m-%dT%H:%M:%SZ", &timeInfo);
  return String(value);
}

uint64_t nextSequenceNo() {
  uint64_t value = preferences.getULong64("sequence", 0) + 1;
  preferences.putULong64("sequence", value);
  return value;
}

String buildPayload(uint64_t sequenceNo, const String &measuredAt, float grams) {
  const long rawValue = lroundf(grams * 1000.0F);
  char sequenceText[24];
  snprintf(sequenceText, sizeof(sequenceText), "%llu",
           static_cast<unsigned long long>(sequenceNo));
  String payload;
  payload.reserve(384);
  payload += "{\"device_uid\":\"" + jsonEscape(MEOW_DEVICE_UID) + "\",";
  payload += "\"sequence_no\":" + String(sequenceText) + ",";
  payload += "\"measured_at\":\"" + measuredAt + "\",";
  payload += "\"raw_value\":" + String(rawValue) + ",";
  payload += "\"raw_weight_grams\":" + String(grams, 1) + ",";
  payload += "\"filtered_weight_grams\":" + String(grams, 1) + ",";
  payload += "\"quality\":\"GOOD\",";
  payload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\",";
  payload += "\"simulated\":true}";
  return payload;
}

template <typename ClientType>
int postJson(ClientType &client, const String &url, const String &payload,
             String &responseBody) {
  HTTPClient http;
  if (!http.begin(client, url)) {
    return -1;
  }
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", MEOW_DEVICE_KEY);
  const int status = http.POST(payload);
  if (status > 0) {
    responseBody = http.getString();
  }
  http.end();
  return status;
}

int sendPayload(const String &payload, String &responseBody) {
  const String url = String(MEOW_API_BASE_URL) + "/api/ingest/measurements";
  if (url.startsWith("https://")) {
    if (strlen(MEOW_ROOT_CA_PEM) < 32) {
      Serial.println("HTTPS refused: configure a trusted root CA.");
      return -1;
    }
    WiFiClientSecure client;
    client.setCACert(MEOW_ROOT_CA_PEM);
    return postJson(client, url, payload, responseBody);
  }
  WiFiClient client;
  return postJson(client, url, payload, responseBody);
}

bool uploadPending() {
  for (uint8_t attempt = 1; attempt <= MAX_HTTP_ATTEMPTS; ++attempt) {
    if (!connectWifi()) {
      Serial.printf("sequence=%llu attempt=%u network=offline\n",
                    static_cast<unsigned long long>(pendingSequence), attempt);
    } else {
      String responseBody;
      const int status = sendPayload(pendingPayload, responseBody);
      Serial.printf("sequence=%llu grams=%.1f attempt=%u http=%d\n",
                    static_cast<unsigned long long>(pendingSequence),
                    TEST_WEIGHTS_GRAMS[weightIndex], attempt, status);
      if (status == 200 || status == 201) {
        Serial.print("response=");
        Serial.println(responseBody);
        return true;
      }
      if (status == 400 || status == 401 || status == 403 || status == 404 ||
          status == 409 || status == 422) {
        Serial.println("Request rejected; check UID, key, time and JSON fields.");
        return false;
      }
    }
    delay(500U * attempt);
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("CatSense isolated simulated-weight test");
  preferences.begin("catsense-sim", false);
  connectWifi();
  syncClock();
}

void loop() {
  if (weightIndex >= TEST_WEIGHT_COUNT) {
    if (!completionPrinted) {
      Serial.println("TEST COMPLETE: 5 simulated weights sent.");
      completionPrinted = true;
    }
    delay(1000);
    return;
  }
  if (millis() - lastAttemptAt < SEND_INTERVAL_MS) {
    delay(50);
    return;
  }
  lastAttemptAt = millis();

  if (!pending) {
    const String measuredAt = utcTimestamp();
    if (measuredAt.length() == 0) {
      Serial.println("No UTC timestamp; waiting for NTP before upload.");
      syncClock();
      return;
    }
    pendingSequence = nextSequenceNo();
    pendingPayload =
        buildPayload(pendingSequence, measuredAt, TEST_WEIGHTS_GRAMS[weightIndex]);
    pending = true;
  }

  if (uploadPending()) {
    pending = false;
    pendingPayload = String();
    ++weightIndex;
  } else {
    Serial.println("Pending payload retained for the next loop retry.");
  }
}

