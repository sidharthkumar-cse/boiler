from flask import Flask, jsonify
import random

app = Flask(__name__)

@app.route('/data', methods=['GET'])
def get_sensor_data():
    # Simulate some variations in the sensor data
    return jsonify({
        "mw": 10.0 + random.uniform(-0.5, 0.5), # Feedwater around 10 kg/s
        "Q": 20e6 + random.uniform(-1e5, 1e5),    # Heat around 20 MW
        "Kv": 1.0 - random.uniform(0.0, 0.1)      # Valve near 1.0 (100%)
    })

if __name__ == '__main__':
    print("Starting Mock ESP32 Web Server on http://127.0.0.1:8080")
    print("Serving sensor data at http://127.0.0.1:8080/data")
    app.run(host='0.0.0.0', port=8080)
