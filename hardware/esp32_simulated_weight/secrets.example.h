#pragma once

// Copy to secrets.h and fill locally. Never commit or share secrets.h.
#define WIFI_SSID "YOUR_WIFI_OR_HOTSPOT_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define MEOW_DEVICE_KEY "YOUR_ISOLATED_TEST_DEVICE_KEY"
#define MEOW_DEVICE_UID "ESP32-SIM-A01"
#define MEOW_API_BASE_URL "http://172.20.10.5:8765"

// Required only after switching MEOW_API_BASE_URL to https://.
static const char MEOW_ROOT_CA_PEM[] = R"CERT(

)CERT";

