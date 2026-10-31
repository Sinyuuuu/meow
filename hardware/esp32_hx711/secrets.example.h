#pragma once

// Copy this file to secrets.h. Never commit or share secrets.h.
#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define MEOW_DEVICE_KEY "YOUR_DEVICE_KEY"
#define MEOW_DEVICE_UID "ESP32-HX711-A01"

// Local test example: http://192.168.1.100:8000
// Production example: https://your-api.example.com
#define MEOW_API_BASE_URL "http://192.168.1.100:8000"

// For HTTPS, paste the API server's trusted root CA certificate here.
// The sketch deliberately refuses HTTPS when this is empty.
static const char MEOW_ROOT_CA_PEM[] = R"CERT(

)CERT";

