#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <vector>
#include <map>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <BLEClient.h>
#include <BLERemoteService.h>
#include <BLERemoteCharacteristic.h>
#include "secrets.h"

#ifndef API_BASE_URL
#define API_BASE_URL "https://cardapiopastel-production.up.railway.app"
#endif
#ifndef PRINTER_NAME
#define PRINTER_NAME "KPrinter_a4f1"
#endif
#ifndef AGENT_ID
#define AGENT_ID "da-lanches-esp32-01"
#endif

static const uint32_t POLL_INTERVAL_MS = 3000;
static const uint32_t BLE_SCAN_SECONDS = 5;
static const size_t BLE_CHUNK_SIZE = 20;

static const char RAILWAY_ROOT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)EOF";

BLEClient* printerClient = nullptr;
BLERemoteCharacteristic* printerChannel = nullptr;

String jsonEscape(const String& input) {
  String out;
  for (size_t i = 0; i < input.length(); i++) {
    char c = input[i];
    if (c == '"' || c == '\\') { out += '\\'; out += c; }
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else if ((uint8_t)c >= 0x20) out += c;
  }
  return out;
}

bool connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando ao Wi-Fi");
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi conectado: ");
    Serial.println(WiFi.localIP());
    return true;
  }
  Serial.println("Falha ao conectar ao Wi-Fi.");
  return false;
}

bool httpRequest(const String& method, const String& path, const String& body, String& response) {
  if (!connectWifi()) return false;
  WiFiClientSecure client;
  client.setCACert(RAILWAY_ROOT_CA);
  HTTPClient http;
  String url = String(API_BASE_URL) + path;
  if (!http.begin(client, url)) return false;
  http.addHeader("X-Print-Agent-Token", PRINT_AGENT_TOKEN);
  http.addHeader("X-Print-Agent-Id", AGENT_ID);
  http.addHeader("Content-Type", "application/json");
  int code = method == "POST" ? http.POST(body) : http.GET();
  response = code > 0 ? http.getString() : "";
  bool ok = code >= 200 && code < 300;
  if (!ok) {
    Serial.printf("HTTP %s %s falhou: %d %s\n", method.c_str(), path.c_str(), code, response.c_str());
  }
  http.end();
  return ok;
}

bool findPrinterCharacteristic() {
  BLEScan* scan = BLEDevice::getScan();
  scan->setActiveScan(true);
  scan->setInterval(100);
  scan->setWindow(80);
  Serial.printf("Procurando impressora BLE: %s\n", PRINTER_NAME);
  BLEScanResults results = scan->start(BLE_SCAN_SECONDS, false);
  BLEAdvertisedDevice* target = nullptr;
  BLEAdvertisedDevice selected;
  for (int i = 0; i < results.getCount(); i++) {
    BLEAdvertisedDevice device = results.getDevice(i);
    String name = device.haveName() ? String(device.getName().c_str()) : "";
    Serial.printf("BLE encontrado: %s\n", name.c_str());
    if (name == PRINTER_NAME) {
      selected = device;
      target = &selected;
      break;
    }
  }
  if (!target) {
    scan->clearResults();
    Serial.println("Impressora não encontrada. Confira o nome e se ela está ligada.");
    return false;
  }

  if (printerClient && printerClient->isConnected()) printerClient->disconnect();
  if (!printerClient) printerClient = BLEDevice::createClient();
  if (!printerClient->connect(target)) {
    scan->clearResults();
    Serial.println("Falha ao conectar ao dispositivo BLE.");
    return false;
  }
  scan->clearResults();

  std::map<std::string, BLERemoteService*>* services = printerClient->getServices();
  if (!services) return false;
  for (auto serviceIt = services->begin(); serviceIt != services->end(); ++serviceIt) {
    std::map<std::string, BLERemoteCharacteristic*>* characteristics =
      serviceIt->second->getCharacteristics();
    if (!characteristics) continue;
    for (auto characteristicIt = characteristics->begin();
         characteristicIt != characteristics->end(); ++characteristicIt) {
      BLERemoteCharacteristic* candidate = characteristicIt->second;
      if (candidate->canWrite() || candidate->canWriteNoResponse()) {
        printerChannel = candidate;
        Serial.printf("Canal BLE gravável encontrado: %s\n",
                      characteristicIt->first.c_str());
        return true;
      }
    }
  }
  printerClient->disconnect();
  printerChannel = nullptr;
  Serial.println("Conectou por BLE, mas não encontrou característica gravável.");
  return false;
}

bool writePrinterBytes(const std::vector<uint8_t>& bytes) {
  if (!printerClient || !printerClient->isConnected() || !printerChannel) {
    if (!findPrinterCharacteristic()) return false;
  }
  const bool response = printerChannel->canWrite();
  for (size_t offset = 0; offset < bytes.size(); offset += BLE_CHUNK_SIZE) {
    size_t length = min(BLE_CHUNK_SIZE, bytes.size() - offset);
    if (!printerClient->isConnected() ||
        !printerChannel->writeValue((uint8_t*)bytes.data() + offset, length, response)) {
      Serial.println("Falha ao enviar bytes para a impressora.");
      printerClient->disconnect();
      printerChannel = nullptr;
      return false;
    }
    delay(response ? 5 : 25);
  }
  return true;
}

void appendText(std::vector<uint8_t>& out, const String& value) {
  for (size_t i = 0; i < value.length(); i++) {
    uint8_t c = (uint8_t)value[i];
    out.push_back(c >= 32 && c <= 126 ? c : (c == '\n' ? 10 : '?'));
  }
}

std::vector<uint8_t> makeReceipt(JsonObject payload) {
  std::vector<uint8_t> out = {0x1B, 0x40, 0x1B, 0x61, 0x01};
  appendText(out, "D&A LANCHE'S\n");
  out.push_back(0x1B); out.push_back(0x61); out.push_back(0x01);
  String order = "PEDIDO #" + String((int)payload["pedido_id"]);
  appendText(out, order + "\n");
  out.push_back(0x1B); out.push_back(0x61); out.push_back(0x00);
  appendText(out, "--------------------------------\n");
  appendText(out, "Local: " + String(payload["mesa"] | "") + "\n");
  appendText(out, String(payload["criado_em"] | "") + "\n");
  appendText(out, "--------------------------------\n");
  JsonArray items = payload["itens"].as<JsonArray>();
  for (JsonObject item : items) {
    String line = String((int)item["quantidade"]) + "x " +
                  String(item["nome"] | "");
    appendText(out, line + "\n");
  }
  String note = String(payload["observacao"] | "");
  if (note.length()) appendText(out, "Obs: " + note + "\n");
  appendText(out, "--------------------------------\nObrigado!\n\n\n");
  return out;
}

void reportResult(int jobId, bool success, const String& error) {
  String response;
  String body = "{\"station_id\":\"" + String(STATION_ID) +
                "\",\"success\":" + String(success ? "true" : "false") +
                ",\"error\":\"" + jsonEscape(error) + "\"}";
  httpRequest("POST", "/api/print-agent/jobs/" + String(jobId) + "/result", body, response);
}

void processOneJob() {
  // Não reserva pedidos enquanto a impressora estiver desligada ou fora de alcance.
  if (!printerClient || !printerClient->isConnected() || !printerChannel) {
    if (!findPrinterCharacteristic()) return;
  }

  String response;
  String path = "/api/print-agent/jobs/next?station_id=" + String(STATION_ID);
  if (!httpRequest("GET", path, "", response)) return;

  JsonDocument doc;
  DeserializationError parseError = deserializeJson(doc, response);
  if (parseError) {
    Serial.printf("Resposta inválida da fila: %s\n", parseError.c_str());
    return;
  }
  if (doc["job"].isNull()) return;

  int jobId = doc["job"]["id"] | 0;
  JsonObject payload = doc["job"]["payload"].as<JsonObject>();
  Serial.printf("Recebido pedido %d (trabalho %d)\n",
                (int)(payload["pedido_id"] | 0), jobId);
  if (!jobId || payload.isNull()) return;

  std::vector<uint8_t> receipt = makeReceipt(payload);
  bool ok = writePrinterBytes(receipt);
  String error = ok ? "" : "A conexão BLE caiu durante o envio dos dados.";
  reportResult(jobId, ok, error);
  if (ok) Serial.println("Bytes enviados. Confirme fisicamente a saída do papel.");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nD&A - Ponte de impressão ESP32");
  BLEDevice::init(AGENT_ID);
  connectWifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  if (WiFi.status() == WL_CONNECTED) processOneJob();
  delay(POLL_INTERVAL_MS);
}
