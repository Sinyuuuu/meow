#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <HX711.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <time.h>

#include "secrets.h"

// Wiring can be changed to match the actual board.
constexpr int HX711_DOUT_PIN = 19;
constexpr int HX711_SCK_PIN = 18;

// Replace this after calibration. It is counts per gram for this sketch.
constexpr float HX711_CALIBRATION_FACTOR = -7050.0F;
constexpr float STABLE_SPREAD_GRAMS = 1.0F;
constexpr int STABLE_SAMPLE_COUNT = 5;
constexpr uint32_t UPLOAD_INTERVAL_MS = 10000;
constexpr uint8_t MAX_HTTP_ATTEMPTS = 3;
constexpr char FIRMWARE_VERSION[] = "catsense-hx711-0.1.0";

HX711 scale;
Preferences preferences;
uint32_t lastUploadAt = 0;

struct WeightSample {
  long rawValue;
  float rawWeightGrams;
  float filteredWeightGrams;
  bool stable;
};

bool waitForClock() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  struct tm timeInfo;
  for (int attempt = 0; attempt < 20; ++attempt) {
    if (getLocalTime(&timeInfo, 1000)) {
      return true;
    }
    delay(250);
  }
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

bool connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int attempt = 0; attempt < 30; ++attempt) {
    if (WiFi.status() == WL_CONNECTED) {
      return true;
    }
    delay(500);
  }
  return false;
}

uint64_t nextSequenceNo() {
  // NVS persistence prevents sequence reuse after an ESP32 restart.
  uint64_t current = preferences.getULong64("sequence", 0);
  current += 1;
  preferences.putULong64("sequence", current);
  return current;
}

WeightSample readStableWeight() {
  float values[STABLE_SAMPLE_COUNT];
  float total = 0.0F;
  float minimum = 1000000.0F;
  float maximum = -1000000.0F;
  for (int index = 0; index < STABLE_SAMPLE_COUNT; ++index) {
    values[index] = scale.get_units(5);
    total += values[index];
    minimum = min(minimum, values[index]);
    maximum = max(maximum, values[index]);
    delay(60);
  }
  const float mean = total / STABLE_SAMPLE_COUNT;
  return {
      scale.read_average(10),
      values[STABLE_SAMPLE_COUNT - 1],
      mean,
      (maximum - minimum) <= STABLE_SPREAD_GRAMS,
  };
}

template <typename ClientType>
int postJson(ClientType &client, const String &url, const String &payload) {
  HTTPClient http;
  if (!http.begin(client, url)) {
    return -1;
  }
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", MEOW_DEVICE_KEY);
  const int status = http.POST(payload);
  http.end();
  return status;
}

int uploadPayload(const String &payload) {
  const String url = String(MEOW_API_BASE_URL) + "/api/ingest/measurements";
  if (url.startsWith("https://")) {
    if (strlen(MEOW_ROOT_CA_PEM) < 32) {
      Serial.println("HTTPS refused: configure MEOW_ROOT_CA_PEM; insecure TLS is disabled.");
      return -1;
    }
    WiFiClientSecure secureClient;
    secureClient.setCACert(MEOW_ROOT_CA_PEM);
    return postJson(secureClient, url, payload);
  }
  WiFiClient localClient;
  return postJson(localClient, url, payload);
}

bool uploadWithRetry(uint64_t sequenceNo, const String &payload) {
  for (uint8_t attempt = 1; attempt <= MAX_HTTP_ATTEMPTS; ++attempt) {
    if (!connectWifi()) {
      Serial.printf("event=%llu attempt=%u network=offline\n", sequenceNo, attempt);
    } else {
      const int status = uploadPayload(payload);
      Serial.printf("event=%llu attempt=%u http=%d\n", sequenceNo, attempt, status);
      if (status == 200 || status == 201) {
        return true;
      }
      // Authentication and validation errors need operator action, not retries.
      if (status == 400 || status == 401 || status == 403 || status == 404 ||
          status == 409 || status == 422) {
        return false;
      }
    }
    delay(500U * attempt);
  }
  return false;
}

String measurementJson(uint64_t sequenceNo, const WeightSample &sample,
                       const String &measuredAt) {
  StaticJsonDocument<512> document;
  document["device_uid"] = MEOW_DEVICE_UID;
  document["sequence_no"] = sequenceNo;
  document["measured_at"] = measuredAt;
  document["raw_value"] = sample.rawValue;
  document["raw_weight_grams"] = sample.rawWeightGrams;
  document["filtered_weight_grams"] = sample.filteredWeightGrams;
  document["quality"] = sample.stable ? "GOOD" : "UNSTABLE";
  document["firmware_version"] = FIRMWARE_VERSION;
  document["simulated"] = false;
  String payload;
  serializeJson(document, payload);
  return payload;
}

void setup() {
  Serial.begin(115200);
  preferences.begin("catsense", false);
  scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
  scale.set_scale(HX711_CALIBRATION_FACTOR);
  scale.tare(20);

  if (!connectWifi()) {
    Serial.println("Wi-Fi unavailable; loop will retry.");
  } else if (!waitForClock()) {
    Serial.println("NTP unavailable; uploads pause until timestamps are valid.");
  }
}

void loop() {
  if (millis() - lastUploadAt < UPLOAD_INTERVAL_MS) {
    delay(50);
    return;
  }
  lastUploadAt = millis();
  const String measuredAt = utcTimestamp();
  if (measuredAt.length() == 0) {
    Serial.println("No valid UTC time; measurement not uploaded.");
    return;
  }

  const WeightSample sample = readStableWeight();
  const uint64_t sequenceNo = nextSequenceNo();
  const String payload = measurementJson(sequenceNo, sample, measuredAt);
  const bool accepted = uploadWithRetry(sequenceNo, payload);
  Serial.printf("event=%llu accepted=%s stable=%s grams=%.2f\n", sequenceNo,
                accepted ? "true" : "false", sample.stable ? "true" : "false",
                sample.filteredWeightGrams);
}

