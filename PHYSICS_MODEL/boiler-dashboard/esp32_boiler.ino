#include <Adafruit_MAX31865.h>
#include <Adafruit_ADS1X15.h>
#include <Wire.h>
#include <WebServer.h>
#include <WiFi.h>

// ================== WIFI CONFIG ==================
const char *ssid = "AryaniPhone";
const char *password = "38003800";

WebServer server(80);

// ================== PIN CONFIGURATION ==================
#define FLOW_PIN 4
#define FLOAT_LOW 27
#define FLOAT_HIGH 26

#define PUMP_RELAY 16
#define SSR_PIN 17

#define VALVE_OPEN 32
#define VALVE_CLOSE 33

#define EMERGENCY_PIN 25
#define MAX_CS 5

// ================== OBJECTS ==================
Adafruit_MAX31865 pt100 = Adafruit_MAX31865(MAX_CS);
Adafruit_ADS1115 ads;  // ADS1115 on default I2C address 0x48

// ================== GLOBAL VARIABLES ==================
volatile int flowPulse = 0;
float flowRate = 0;
float temperature = 0;
float pressure = 0;

bool pumpState = false;
bool valveOpenState = false;

// Float Switch States
bool floatLow = false;    // true = water IS at or above low mark
bool floatHigh = false;   // true = water IS at or above high mark
bool systemReady = false; // true = safe to run heater (water at high level)

// Manual Control State
bool heaterManual = false;
bool heaterManualState = false;

unsigned long lastFlowTime = 0;

const float PULSES_PER_LITER = 450.0;

// ================== SENSOR SMOOTHING (EMA) ==================
// Exponential Moving Average: filtered = α * raw + (1-α) * filtered_prev
// Lower α = smoother but slower response.  Higher α = faster but noisier.
const float EMA_ALPHA_TEMP     = 0.15;  // Temperature changes slowly — heavy smoothing
const float EMA_ALPHA_PRESSURE = 0.15;  // Pressure changes slowly — heavy smoothing
const float EMA_ALPHA_FLOW     = 0.25;  // Flow needs faster tracking

float ema_temperature = 0;
float ema_pressure    = 0;
float ema_flow        = 0;
bool  ema_initialized = false;  // First reading seeds the filter

// Number of ADC samples to average per pressure reading (reduces quantization noise)
const int PRESSURE_OVERSAMPLE = 4;

// ================== WIFI SETUP ==================
void setupWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // Print in the format the Python proxy auto-detects
  Serial.print("http://");
  Serial.print(WiFi.localIP());
  Serial.println("/data");
}

// ================== HTTP HANDLERS (Dashboard Control) ==================
void handleHeaterOn() {
  if (!systemReady) {
    server.send(403, "application/json",
                "{\"status\":\"DENIED\", \"reason\":\"Water level too low — "
                "fill to FLOAT_HIGH first\"}");
    Serial.println("SAFETY: Heater ON denied — water not ready");
    return;
  }
  heaterManual = true;
  heaterManualState = true;
  server.send(200, "application/json",
              "{\"status\":\"HEATER_ON\", \"mode\":\"MANUAL\"}");
  Serial.println("Heater: ON");
}

void handleHeaterOff() {
  heaterManual = true;
  heaterManualState = false;
  server.send(200, "application/json",
              "{\"status\":\"HEATER_OFF\", \"mode\":\"MANUAL\"}");
  Serial.println("Heater: OFF");
}

void handleHeaterAuto() {
  heaterManual = false;
  server.send(200, "application/json",
              "{\"status\":\"AUTO\", \"mode\":\"AUTO\"}");
  Serial.println("Mode: AUTO");
}

void handleValveOn() {
  if (!valveOpenState) {
    valveOpenCmd();  // Power OPEN relay, release CLOSE relay
    valveOpenState = true;
  }
  server.send(200, "application/json", "{\"status\":\"VALVE_OPEN\"}");
  Serial.println("Valve: OPEN");
}

void handleValveOff() {
  if (valveOpenState) {
    valveCloseCmd();  // Release OPEN relay, power CLOSE relay
    valveOpenState = false;
  }
  server.send(200, "application/json", "{\"status\":\"VALVE_CLOSED\"}");
  Serial.println("Valve: CLOSED");
}

void handleStatus() {
  String json = "{";
  json += "\"temp\":" + String(temperature) + ",";
  json += "\"pressure\":" + String(pressure) + ",";
  json += "\"flow\":" + String(flowRate) + ",";
  json += "\"heater_manual\":" + String(heaterManual ? "true" : "false") + ",";
  json += "\"heater_state\":" +
          String(digitalRead(SSR_PIN) == HIGH ? "\"ON\"" : "\"OFF\"") + ",";
  json += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  json +=
      "\"valve\":" + String(valveOpenState ? "\"OPEN\"" : "\"CLOSED\"") + ",";
  json += "\"float_low\":" + String(floatLow ? "true" : "false") + ",";
  json += "\"float_high\":" + String(floatHigh ? "true" : "false") + ",";
  json += "\"ready\":" + String(systemReady ? "true" : "false");
  json += "}";
  server.send(200, "application/json", json);
}

// ================== INTERRUPTS & SENSORS ==================
void IRAM_ATTR flowISR() { flowPulse++; }

void readSensors() {
  // Flow Calculation
  if (millis() - lastFlowTime >= 1000) {
    float liters = flowPulse / PULSES_PER_LITER;
    float rawFlow = liters * 60.0;
    flowPulse = 0;
    lastFlowTime = millis();

    // EMA for flow
    if (!ema_initialized) {
      ema_flow = rawFlow;
    } else {
      ema_flow = EMA_ALPHA_FLOW * rawFlow + (1.0 - EMA_ALPHA_FLOW) * ema_flow;
    }
    flowRate = ema_flow;
  }

  // Temperature (PT100)
  float raw_temp = pt100.temperature(100, 430);
  // Calibration: If sensor returns raw high values, convert to Celsius
  if (raw_temp > 300) {
    raw_temp = (raw_temp - 500.0) / 10.0;
  }
  // EMA for temperature
  if (!ema_initialized) {
    ema_temperature = raw_temp;
  } else {
    ema_temperature = EMA_ALPHA_TEMP * raw_temp + (1.0 - EMA_ALPHA_TEMP) * ema_temperature;
  }
  temperature = ema_temperature;

  // Pressure Sensor via ADS1115 (16-bit ADC, I2C)
  // Sensor: 1.2 MPa (12 bar) G1/4" Stainless Steel Transducer
  // Output: 0.5V (0 bar) to 4.5V (12 bar), powered at 5V
  // ADS1115: Gain = TWOTHIRDS (±6.144V), resolution = 0.1875 mV/bit
  // Multi-sample averaging to reduce quantization noise
  long adcSum = 0;
  for (int i = 0; i < PRESSURE_OVERSAMPLE; i++) {
    adcSum += ads.readADC_SingleEnded(0);
  }
  float avgADC = (float)adcSum / (float)PRESSURE_OVERSAMPLE;
  float sensorVoltage = avgADC * 0.0001875;  // ADS1115 TWOTHIRDS gain: 0.1875 mV/bit
  const float PRESSURE_ZERO_V = 0.5;
  const float PRESSURE_SPAN_V = 4.0;
  const float PRESSURE_FULL_SCALE_MPA = 1.2; // 1.2 MPa = 12 bar gauge
  float rawPressure = (sensorVoltage - PRESSURE_ZERO_V) *
                      (PRESSURE_FULL_SCALE_MPA / PRESSURE_SPAN_V);
  if (rawPressure < 0) rawPressure = 0;
  if (rawPressure > 1.2) rawPressure = 1.2; // Clamp to sensor max

  // EMA for pressure
  if (!ema_initialized) {
    ema_pressure = rawPressure;
    ema_initialized = true;  // All channels seeded after first pass
  } else {
    ema_pressure = EMA_ALPHA_PRESSURE * rawPressure + (1.0 - EMA_ALPHA_PRESSURE) * ema_pressure;
  }
  pressure = ema_pressure;

  // Float Switches — Normally-Closed (NC) wiring with INPUT_PULLUP
  // No water → float hangs down → switch CLOSED → pin grounded → LOW
  // Water present → float rises → switch OPENS → pin pulled HIGH
  floatLow = (digitalRead(FLOAT_LOW) == HIGH); // HIGH = water at/above low mark
  floatHigh =
      (digitalRead(FLOAT_HIGH) == HIGH); // HIGH = water at/above high mark

  // System Ready = water has reached the high float level
  // Safe to operate the heater only when sufficient water is present
  systemReady = floatHigh;
}

// ================== HARDWARE CONTROL ==================
// Valve relay module: Active-HIGH → HIGH = relay ON, LOW = relay OFF
void valveOpenCmd() {
  digitalWrite(VALVE_CLOSE, LOW);   // Release CLOSE relay first
  digitalWrite(VALVE_OPEN, HIGH);   // Then power OPEN relay
}

void valveCloseCmd() {
  digitalWrite(VALVE_OPEN, LOW);    // Release OPEN relay first
  digitalWrite(VALVE_CLOSE, HIGH);  // Then power CLOSE relay
}

void valveStopCmd() {
  digitalWrite(VALVE_OPEN, LOW);    // Both relays OFF — no power to valve
  digitalWrite(VALVE_CLOSE, LOW);
}

void emergencyCheck() {
  if (digitalRead(EMERGENCY_PIN) == LOW) {
    digitalWrite(SSR_PIN, LOW);
    digitalWrite(PUMP_RELAY, LOW);
    valveStopCmd();  // Kill all valve power
  }
}

void pumpControl() {
  // Uses the already-read float states from readSensors()
  if (!floatHigh && !pumpState) {
    // Water dropped below high float → start pump
    digitalWrite(PUMP_RELAY, HIGH);
    pumpState = true;
    Serial.println("Pump: ON (water below high float)");
  }
  if (floatHigh && pumpState) {
    // Water reached high float → stop pump
    digitalWrite(PUMP_RELAY, LOW);
    pumpState = false;
    Serial.println("Pump: OFF (water at high float)");
  }
}

void heaterControl() {
  // CRITICAL SAFETY OVERRIDE 1: Temperature limit (145°C)
  if (temperature >= 145) {
    digitalWrite(SSR_PIN, LOW);
    if (millis() % 5000 < 100)
      Serial.println("CRITICAL: Overheat Safety Triggered!");
    return;
  }

  // CRITICAL SAFETY OVERRIDE 2: Water level check
  // Heater MUST NOT run if water level is below the high float
  if (!systemReady) {
    digitalWrite(SSR_PIN, LOW);
    if (millis() % 5000 < 100)
      Serial.println("SAFETY: Heater blocked — water level not ready");
    return;
  }

  if (heaterManual) {
    // Mode: Manual (Controlled by Dashboard)
    digitalWrite(SSR_PIN, heaterManualState ? HIGH : LOW);
  } else {
    // Mode: Auto (Controlled by Thermostat)
    if (temperature >= 130)
      digitalWrite(SSR_PIN, LOW);
    else if (temperature <= 100)
      digitalWrite(SSR_PIN, HIGH);
  }
}

// Valve: No auto-control needed.
// Relays hold their state continuously until the next explicit command.
// OPEN  → VALVE_OPEN relay stays energized, VALVE_CLOSE relay stays off.
// CLOSE → VALVE_CLOSE relay stays energized, VALVE_OPEN relay stays off.
// Idle  → Both relays stay in whatever state they were last commanded to.

// ================== SERIAL CMD PARSING ==================
void processSerialCommands() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "HEATER_ON") {
      if (!systemReady) {
        Serial.println("SAFETY: Heater ON denied — water not ready");
        return;
      }
      heaterManual = true;
      heaterManualState = true;
      Serial.println("Heater: ON");
    } else if (cmd == "HEATER_OFF") {
      heaterManual = true;
      heaterManualState = false;
      Serial.println("Heater: OFF");
    } else if (cmd == "HEATER_AUTO") {
      heaterManual = false;
      Serial.println("Mode: AUTO");
    } else if (cmd == "VALVE_ON") {
      if (!valveOpenState) {
        Serial.println("Valve: OPEN");
        valveOpenCmd();
        valveOpenState = true;
      } else {
        Serial.println("Valve: ALREADY OPEN");
      }
    } else if (cmd == "VALVE_OFF") {
      if (valveOpenState) {
        Serial.println("Valve: CLOSED");
        valveCloseCmd();
        valveOpenState = false;
      } else {
        Serial.println("Valve: ALREADY CLOSED");
      }
    }
  }
}

// ================== MAIN SETUP & LOOP ==================
void setup() {
  Serial.begin(115200);
  setupWiFi();

  // WebServer Routes
  server.on("/heater/on", handleHeaterOn);
  server.on("/heater/off", handleHeaterOff);
  server.on("/heater/auto", handleHeaterAuto);
  server.on("/valve/on", handleValveOn);
  server.on("/valve/off", handleValveOff);
  server.on("/data", handleStatus);
  server.begin();

  // ADS1115 Pressure ADC — I2C on SDA=21, SCL=22
  Wire.begin(21, 22);
  ads.setGain(GAIN_TWOTHIRDS);  // ±6.144V range — covers 0–4.5V sensor output
  if (!ads.begin()) {
    Serial.println("ERROR: ADS1115 not found! Check I2C wiring.");
  } else {
    Serial.println("ADS1115 initialized on I2C (0x48)");
  }

  pinMode(FLOW_PIN, INPUT_PULLUP);
  pinMode(FLOAT_LOW, INPUT_PULLUP);
  pinMode(FLOAT_HIGH, INPUT_PULLUP);
  pinMode(EMERGENCY_PIN, INPUT_PULLUP);
  pinMode(PUMP_RELAY, OUTPUT);
  pinMode(SSR_PIN, OUTPUT);

  // Valve relay pins — Active-HIGH module: LOW = OFF on boot
  pinMode(VALVE_OPEN, OUTPUT);
  pinMode(VALVE_CLOSE, OUTPUT);
  digitalWrite(VALVE_OPEN, LOW);   // OFF — no power to valve on startup
  digitalWrite(VALVE_CLOSE, LOW);  // OFF — no power to valve on startup

  attachInterrupt(digitalPinToInterrupt(FLOW_PIN), flowISR, RISING);
  pt100.begin(MAX31865_3WIRE);
  Serial.println("System Initialized...");
}

void loop() {
  server.handleClient();
  processSerialCommands();

  readSensors();
  emergencyCheck();
  pumpControl();
  heaterControl();

  // Periodic Telemetry to Serial (for Python Proxy)
  // Format MUST match what serial_proxy.py parses
  static unsigned long lastLog = 0;
  if (millis() - lastLog >= 1000) {
    Serial.println("------");
    Serial.print("Temp: ");
    Serial.println(temperature);
    Serial.print("Pressure: ");
    Serial.println(pressure);
    Serial.print("P_ADC: ");
    Serial.println(ads.readADC_SingleEnded(0)); // raw ADS1115 counts
    Serial.print("P_Volts: ");
    Serial.println(ads.computeVolts(ads.readADC_SingleEnded(0)),
                   4); // sensor voltage from ADS1115
    Serial.print("Flow: ");
    Serial.println(flowRate);
    Serial.print("Pump: ");
    Serial.println(pumpState ? "1" : "0");
    Serial.print("Heater: ");
    Serial.println(digitalRead(SSR_PIN) == HIGH ? "ON" : "OFF");
    Serial.print("Mode: ");
    Serial.println(heaterManual ? "MANUAL" : "AUTO");
    Serial.print("Valve: ");
    Serial.println(valveOpenState ? "OPEN" : "CLOSED");

    Serial.print("FloatLow: ");
    Serial.println(floatLow ? "1" : "0");
    Serial.print("FloatHigh: ");
    Serial.println(floatHigh ? "1" : "0");
    Serial.print("Ready: ");
    Serial.println(systemReady ? "1" : "0");

    // IP auto-detection line for the Python proxy
    Serial.print("http://");
    Serial.print(WiFi.localIP());
    Serial.println("/data");

    lastLog = millis();
  }
}
