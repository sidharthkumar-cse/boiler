#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_MAX31865.h>
#include <Adafruit_ADS1X15.h>

// ================== WIFI CONFIG ==================
const char* ssid = "AryaniPhone";
const char* password = "38003800";

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
Adafruit_ADS1115 ads;

// ================== GLOBAL VARIABLES ==================
volatile int flowPulse = 0;
float flowRate = 0;
float temperature = 0;
float pressure = 0;
bool pumpState = false;
bool valveOpenState = false;

// Float Switch States
bool floatLow = false;     // true = water IS at or above low mark
bool floatHigh = false;    // true = water IS at or above high mark
bool systemReady = false;  // true = safe to run heater (water at high level)

// Manual Control State
bool heaterManual = false;
bool heaterManualState = false;

unsigned long lastFlowTime = 0;
unsigned long valveStartTime = 0;
bool valveRunning = false;

const float PULSES_PER_LITER = 450.0;
const int valveRunTime = 13000; // 13 seconds for full stroke

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
      "{\"status\":\"DENIED\", \"reason\":\"Water level too low — fill to FLOAT_HIGH first\"}");
    Serial.println("SAFETY: Heater ON denied — water not ready");
    return;
  }
  heaterManual = true;
  heaterManualState = true;
  server.send(200, "application/json", "{\"status\":\"HEATER_ON\", \"mode\":\"MANUAL\"}");
  Serial.println("Heater: ON");
}

void handleHeaterOff() {
  heaterManual = true;
  heaterManualState = false;
  server.send(200, "application/json", "{\"status\":\"HEATER_OFF\", \"mode\":\"MANUAL\"}");
  Serial.println("Heater: OFF");
}

void handleHeaterAuto() {
  heaterManual = false;
  server.send(200, "application/json", "{\"status\":\"AUTO\", \"mode\":\"AUTO\"}");
  Serial.println("Mode: AUTO");
}

void handleStatus() {
  String json = "{";
  json += "\"temp\":" + String(temperature) + ",";
  json += "\"pressure\":" + String(pressure) + ",";
  json += "\"flow\":" + String(flowRate) + ",";
  json += "\"heater_manual\":" + String(heaterManual ? "true" : "false") + ",";
  json += "\"heater_state\":" + String(digitalRead(SSR_PIN) == HIGH ? "\"ON\"" : "\"OFF\"") + ",";
  json += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  json += "\"valve\":" + String(valveOpenState ? "\"OPEN\"" : "\"CLOSED\"") + ",";
  json += "\"float_low\":" + String(floatLow ? "true" : "false") + ",";
  json += "\"float_high\":" + String(floatHigh ? "true" : "false") + ",";
  json += "\"ready\":" + String(systemReady ? "true" : "false");
  json += "}";
  server.send(200, "application/json", json);
}

// ================== INTERRUPTS & SENSORS ==================
void IRAM_ATTR flowISR() {
  flowPulse++;
}

void readSensors() {
  // Flow Calculation
  if (millis() - lastFlowTime >= 1000) {
    float liters = flowPulse / PULSES_PER_LITER;
    flowRate = liters * 60.0;
    flowPulse = 0;
    lastFlowTime = millis();
  }

  // Temperature (PT100)
  float raw_temp = pt100.temperature(100, 430);
  // Calibration: If sensor returns raw high values, convert to Celsius
  if (raw_temp > 300) {
    temperature = (raw_temp - 500.0) / 10.0;
  } else {
    temperature = raw_temp;
  }

  // Pressure Sensor via ADS1115
  // Sensor: 1.2 MPa (12 bar) gauge, 0.5V at 0 bar to 4.5V at 12 bar
  int16_t adc = ads.readADC_SingleEnded(0);
  float voltage = adc * 0.1875 / 1000.0;
  
  // Apply the physical zero-offset calibration (0.664V instead of 0.5V) 
  // so that it reads 0.0 at atmospheric pressure.
  const float PRESSURE_ZERO_V = 0.664; 
  const float PRESSURE_SPAN_V = 4.0;
  const float PRESSURE_FULL_SCALE_MPA = 1.2;
  
  pressure = (voltage - PRESSURE_ZERO_V) *
             (PRESSURE_FULL_SCALE_MPA / PRESSURE_SPAN_V);
             
  if (pressure < 0) pressure = 0;
  if (pressure > PRESSURE_FULL_SCALE_MPA) pressure = PRESSURE_FULL_SCALE_MPA;

  // Float Switches — Normally-Closed (NC) wiring with INPUT_PULLUP
  // No water → float hangs down → switch CLOSED → pin grounded → LOW
  // Water present → float rises → switch OPENS → pin pulled HIGH
  floatLow  = (digitalRead(FLOAT_LOW)  == HIGH);   // HIGH = water at/above low mark
  floatHigh = (digitalRead(FLOAT_HIGH) == HIGH);   // HIGH = water at/above high mark

  // System Ready = water has reached the high float level
  // Safe to operate the heater only when sufficient water is present
  systemReady = floatHigh;
}

// ================== HARDWARE CONTROL ==================
void setValveRelays(bool openCmd, bool closeCmd) {
  // High-Impedance protection for 5V signals on standard relays
  pinMode(VALVE_OPEN, INPUT);
  pinMode(VALVE_CLOSE, INPUT);
  delay(100);

  if (openCmd) {
    pinMode(VALVE_OPEN, OUTPUT);
    digitalWrite(VALVE_OPEN, LOW);
  }
  if (closeCmd) {
    pinMode(VALVE_CLOSE, OUTPUT);
    digitalWrite(VALVE_CLOSE, LOW);
  }
}

void emergencyCheck() {
  if (digitalRead(EMERGENCY_PIN) == LOW) {
    digitalWrite(SSR_PIN, LOW);
    digitalWrite(PUMP_RELAY, LOW);
    setValveRelays(false, false);
  }
}

void pumpControl() {
  // Uses the already-read float states from readSensors()
  // Pump starts when water drops below HIGH float → keeps boiler always full
  if (!floatHigh && !pumpState) {
    // Water below high float → start pump to refill
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
    if (millis() % 5000 < 100) Serial.println("CRITICAL: Overheat Safety Triggered!");
    return;
  }

  // CRITICAL SAFETY OVERRIDE 2: Water level check
  // Heater MUST NOT run if water level is below the high float
  if (!systemReady) {
    digitalWrite(SSR_PIN, LOW);
    if (millis() % 5000 < 100) Serial.println("SAFETY: Heater blocked — water level not ready");
    return;
  }

  if (heaterManual) {
    // Mode: Manual (Controlled by Dashboard)
    digitalWrite(SSR_PIN, heaterManualState ? HIGH : LOW);
  } else {
    // Mode: Auto (Controlled by Thermostat)
    if (temperature >= 130) digitalWrite(SSR_PIN, LOW);
    else if (temperature <= 100) digitalWrite(SSR_PIN, HIGH);
  }
}

void valveControl() {
  if (valveRunning) {
    if (millis() - valveStartTime >= valveRunTime) {
      setValveRelays(false, false);
      valveRunning = false;
      Serial.println("Valve: STOP");
    }
    return;
  }

  // Automatic Valve Protection
  if (temperature >= 85 && !valveOpenState) {
    Serial.println("Valve: OPEN START");
    setValveRelays(true, false);
    valveStartTime = millis();
    valveRunning = true;
    valveOpenState = true;
  }

  if (temperature <= 80 && valveOpenState) {
    Serial.println("Valve: CLOSE START");
    setValveRelays(false, true);
    valveStartTime = millis();
    valveRunning = true;
    valveOpenState = false;
  }
}

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
    }
    else if (cmd == "HEATER_OFF") {
      heaterManual = true;
      heaterManualState = false;
      Serial.println("Heater: OFF");
    }
    else if (cmd == "HEATER_AUTO") {
      heaterManual = false;
      Serial.println("Mode: AUTO");
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
  server.on("/data", handleStatus);
  server.begin();

  Wire.begin(21, 22);
  ads.setGain(GAIN_TWOTHIRDS);  // +/-6.144V range, 0.1875 mV/bit
  if (!ads.begin()) {
    Serial.println("ADS1115 FAIL");
    while(1);
  }

  pinMode(FLOW_PIN, INPUT_PULLUP);
  pinMode(FLOAT_LOW, INPUT_PULLUP);
  pinMode(FLOAT_HIGH, INPUT_PULLUP);
  pinMode(EMERGENCY_PIN, INPUT_PULLUP);
  pinMode(PUMP_RELAY, OUTPUT);
  pinMode(SSR_PIN, OUTPUT);

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
  valveControl();

  // Periodic Telemetry to Serial (for Python Proxy)
  // Format MUST match what serial_proxy.py parses
  static unsigned long lastLog = 0;
  if (millis() - lastLog >= 1000) {
    Serial.println("------");
    Serial.print("Temp: ");      Serial.println(temperature);
    Serial.print("Pressure: ");  Serial.println(pressure, 4); // Send in MPa
    Serial.print("Flow: ");      Serial.println(flowRate);
    Serial.print("Pump: ");      Serial.println(pumpState ? "1" : "0");
    Serial.print("Heater: ");    Serial.println(digitalRead(SSR_PIN) == HIGH ? "ON" : "OFF");
    Serial.print("Mode: ");      Serial.println(heaterManual ? "MANUAL" : "AUTO");
    Serial.print("Valve: ");     Serial.println(valveOpenState ? "OPEN" : "CLOSED");
    Serial.print("FloatLow: ");  Serial.println(floatLow ? "1" : "0");
    Serial.print("FloatHigh: "); Serial.println(floatHigh ? "1" : "0");
    Serial.print("Ready: ");     Serial.println(systemReady ? "1" : "0");

    // IP auto-detection line for the Python proxy
    Serial.print("http://");
    Serial.print(WiFi.localIP());
    Serial.println("/data");

    lastLog = millis();
  }
}
