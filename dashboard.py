from flask import Flask, render_template, send_from_directory, jsonify, request
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import threading
import time
import os
import re
import sqlite3
from datetime import datetime
import geocoder
import requests
import pandas as pd
import joblib


def parse_config_h(path):
    """Parse active (non-commented) #define values from a config.h file."""
    defines = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#define"):
                    match = re.match(r'#define\s+(\w+)\s+"?([^"\s]+)"?', line)
                    if match:
                        defines[match.group(1)] = match.group(2)
    except FileNotFoundError:
        print(f"Warning: config.h not found at {path}, falling back to defaults")
    return defines


_CONFIG_H_PATH = os.path.join(
    os.path.dirname(__file__), "Sync_Guard_Sketch", "config.h"
)
_config = parse_config_h(_CONFIG_H_PATH)

# Load ML model
_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "Training_Data", "Model_V6_1.6.pkl"
)
try:
    ai_model = joblib.load(_MODEL_PATH)
    print(f"ML model loaded: {_MODEL_PATH}")
except Exception as _e:
    ai_model = None
    print(f"Warning: Could not load ML model: {_e}")

app = Flask(__name__)
app.config["SECRET_KEY"] = "sync-guard-secret-2026"
socketio = SocketIO(app, cors_allowed_origins="*")

# MQTT Configuration — sourced from Sync_Guard_Sketch/config.h
MQTT_BROKER = _config.get("MQTT_SERVER", "172.20.10.3")
MQTT_PORT = int(_config.get("MQTT_PORT", 1883))
WIFI_SSID = _config.get("WIFI_SSID", "Unknown")

# ===== MQTT Topics =====
# --- RECEIVED from ESP32 (syncguard → dashboard) ---
TOPIC_STATUS = "syncguard/status"
TOPIC_HEARTBEAT = "syncguard/heartbeat"
TOPIC_TEMPERATURE = "syncguard/temperature"
TOPIC_PRESSURE = "syncguard/pressure"
TOPIC_HUMIDITY = "syncguard/humidity"
TOPIC_RAIN = "syncguard/rain"
TOPIC_RAIN_ANALOG = "syncguard/rain_analog"
TOPIC_SERVO_STATE = "syncguard/servo/state"

# --- SENT to ESP32 (dashboard → syncguard) ---
TOPIC_SERVO_CMD = "syncguard/servo/change-state"
TOPIC_SERVO_ACK = "syncguard/servo/ack"  # ACK from ESP32 after servo moves
TOPIC_LED_WARNING = "syncguard/led/warning"  # "on" = dismissed warning (yellow LED)

MQTT_TOPICS = [
    (TOPIC_STATUS, 0),
    (TOPIC_HEARTBEAT, 0),
    (TOPIC_TEMPERATURE, 0),
    (TOPIC_PRESSURE, 0),
    (TOPIC_HUMIDITY, 0),
    (TOPIC_RAIN, 0),
    (TOPIC_RAIN_ANALOG, 0),
    (TOPIC_SERVO_STATE, 0),
    (TOPIC_SERVO_ACK, 0),
]

# Heartbeat watchdog — mark ESP offline if no heartbeat within this many seconds
HEARTBEAT_TIMEOUT = 15

# OpenWeather API Configuration
OPENWEATHER_API_KEY = "120d0873a392ff37d15d9562aa258a4f"  # Replace with your API key
WEATHER_UPDATE_INTERVAL = 300  # Update every 5 minutes (300 seconds)

# Global state
esp32_status = {
    "online": False,
    "last_seen": None,
    "last_heartbeat": None,
    "uptime": None,
    "heartbeat_count": None,
    "sensor_data": None,
}

# Browser geolocation (more accurate than IP-based)
browser_location = {
    "lat": None,
    "lon": None,
    "source": None,  # "browser" or "ip"
}

# ===== Sensor Readings (all ESP32 sensor values stored here) =====
sensor_readings = {
    "temperature": None,  # °C — from BME280
    "pressure": None,  # hPa — from BME280
    "humidity": None,  # % — from DHT22
    "rain": None,  # 1 = raining, 0 = dry — rain sensor digital
    "rain_analog": None,  # 0-4095 raw ADC — rain sensor analog
    "servo_state": None,  # "open" or "closed"
}
_last_heartbeat_epoch = None  # float seconds (time.time()) for timeout checks
weather_data = {
    "temp": None,
    "humidity": None,
    "description": None,
    "location": None,
    "lat": None,
    "lon": None,
    "rain": None,
    "clouds": None,
}

# SQLite database
DB_PATH = os.path.join(os.path.dirname(__file__), "syncguard.db")


def init_db():
    """Create the ai_check_log table if it does not already exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_check_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at        TEXT NOT NULL,
                temperature      REAL,
                humidity         REAL,
                rain_analog      INTEGER,
                sensor_simulated INTEGER DEFAULT 0,
                weather_location TEXT,
                weather_desc     TEXT,
                weather_rain     REAL,
                weather_raining  INTEGER DEFAULT 0,
                weather_sim      INTEGER DEFAULT 0,
                prediction       INTEGER,
                prob_open        REAL,
                prob_warning     REAL,
                prob_close       REAL
            )
        """)


def log_ai_check(result):
    """Persist one AI check result row to SQLite."""
    ss = result.get("sensor_snapshot", {})
    ws = result.get("weather_snapshot", {})
    probs = result.get("probabilities", [])
    logged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO ai_check_log (
                logged_at, temperature, humidity, rain_analog, sensor_simulated,
                weather_location, weather_desc, weather_rain, weather_raining, weather_sim,
                prediction, prob_open, prob_warning, prob_close
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                logged_at,
                ss.get("temperature"),
                ss.get("humidity"),
                ss.get("rain_analog"),
                int(bool(ss.get("simulated"))),
                ws.get("location"),
                ws.get("description"),
                ws.get("rain"),
                int(bool(ws.get("is_raining"))),
                int(bool(ws.get("simulated"))),
                result.get("prediction"),
                probs[0] if len(probs) > 0 else None,
                probs[1] if len(probs) > 1 else None,
                probs[2] if len(probs) > 2 else None,
            ),
        )


# Weather simulation state
weather_simulation_mode = False
simulation_weather_data = {}

# ESP32 simulation state
esp32_simulation_mode = False
simulation_sensor_data = {}

# MQTT Client Setup
mqtt_client = mqtt.Client()


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        print(f"Connected to MQTT Broker at {MQTT_BROKER}")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos)
            print(f"Subscribed to: {topic}")
    else:
        print(f"Failed to connect to MQTT Broker, return code {rc}")


def on_message(client, userdata, msg):
    """Callback when a message is received from MQTT broker"""
    global _last_heartbeat_epoch
    topic = msg.topic
    payload = msg.payload.decode("utf-8")
    timestamp = datetime.now().strftime("%H:%M:%S")

    print(f"[{timestamp}] Received from {topic}: {payload}")

    # Emit one raw event per MQTT message — used by the monitor page
    socketio.emit(
        "mqtt_message", {"topic": topic, "payload": payload, "timestamp": timestamp}
    )

    if topic == TOPIC_STATUS:
        is_online = payload in ("online",)
        esp32_status["online"] = is_online
        esp32_status["last_seen"] = timestamp
        if is_online:
            esp32_status["last_heartbeat"] = timestamp
            _last_heartbeat_epoch = time.time()
        socketio.emit(
            "status_update",
            {
                "online": is_online,
                "last_seen": timestamp,
                "last_heartbeat": esp32_status["last_heartbeat"],
                "uptime": esp32_status["uptime"],
                "heartbeat_count": esp32_status["heartbeat_count"],
                "status_type": payload,
            },
        )

    elif topic == TOPIC_HEARTBEAT:
        esp32_status["online"] = True
        esp32_status["last_seen"] = timestamp
        esp32_status["last_heartbeat"] = timestamp
        esp32_status["uptime"] = payload
        _last_heartbeat_epoch = time.time()
        socketio.emit(
            "status_update",
            {
                "online": True,
                "last_seen": timestamp,
                "last_heartbeat": timestamp,
                "uptime": payload,
                "heartbeat_count": esp32_status["heartbeat_count"],
                "status_type": "heartbeat",
            },
        )

    elif topic == TOPIC_TEMPERATURE:
        sensor_readings["temperature"] = payload
        _emit_sensor_update(timestamp)

    elif topic == TOPIC_PRESSURE:
        sensor_readings["pressure"] = payload
        _emit_sensor_update(timestamp)

    elif topic == TOPIC_HUMIDITY:
        sensor_readings["humidity"] = payload
        _emit_sensor_update(timestamp)

    elif topic == TOPIC_RAIN:
        sensor_readings["rain"] = payload  # "1" or "0"
        _emit_sensor_update(timestamp)

    elif topic == TOPIC_RAIN_ANALOG:
        sensor_readings["rain_analog"] = payload
        _emit_sensor_update(timestamp)

    elif topic == TOPIC_SERVO_STATE:
        sensor_readings["servo_state"] = payload  # "open" or "closed"
        socketio.emit("servo_update", {"state": payload, "timestamp": timestamp})

    elif topic == TOPIC_SERVO_ACK:
        # Forward ACK to browser so JS can compute round-trip latency
        socketio.emit("servo_ack", {"state": payload, "timestamp": timestamp})


def _emit_sensor_update(timestamp):
    """Emit the current sensor_readings snapshot to all connected clients.
    Skipped when ESP32 simulation mode is active so simulated data is not overwritten.
    """
    if esp32_simulation_mode:
        return
    socketio.emit(
        "sensor_update",
        {
            "temperature": sensor_readings["temperature"],
            "pressure": sensor_readings["pressure"],
            "humidity": sensor_readings["humidity"],
            "rain": sensor_readings["rain"],
            "rain_analog": sensor_readings["rain_analog"],
            "servo_state": sensor_readings["servo_state"],
            "timestamp": timestamp,
        },
    )


def on_disconnect(client, userdata, rc):
    """Callback when disconnected from MQTT broker"""
    if rc != 0:
        print(f"Unexpected disconnection from MQTT Broker. Attempting to reconnect...")


def heartbeat_watchdog_loop():
    """Mark ESP32 offline if no heartbeat received within HEARTBEAT_TIMEOUT seconds."""
    global _last_heartbeat_epoch
    while True:
        time.sleep(5)
        if esp32_status["online"] and _last_heartbeat_epoch is not None:
            elapsed = time.time() - _last_heartbeat_epoch
            if elapsed > HEARTBEAT_TIMEOUT:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(
                    f"[{timestamp}] Heartbeat timeout ({elapsed:.0f}s) — marking ESP32 offline"
                )
                esp32_status["online"] = False
                if not esp32_simulation_mode:
                    socketio.emit(
                        "status_update",
                        {
                            "online": False,
                            "last_seen": esp32_status["last_seen"],
                            "last_heartbeat": esp32_status["last_heartbeat"],
                            "uptime": esp32_status["uptime"],
                            "heartbeat_count": esp32_status["heartbeat_count"],
                            "status_type": "timeout",
                        },
                    )


# Configure MQTT callbacks
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.on_disconnect = on_disconnect


def start_mqtt():
    """Start MQTT client in background thread"""
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"MQTT Connection Error: {e}")


def get_location():
    """Get current location using geocoder"""
    try:
        g = geocoder.ip("me")
        if g.ok:
            return g.latlng  # Returns [latitude, longitude]
        return None
    except Exception as e:
        print(f"Geocoder Error: {e}")
        return None


def fetch_weather_data():
    """Fetch weather data from OpenWeather API"""
    global weather_data

    # Use browser location if available, otherwise fall back to IP geolocation
    lat, lon = None, None
    location_source = None

    if browser_location["lat"] is not None and browser_location["lon"] is not None:
        lat, lon = browser_location["lat"], browser_location["lon"]
        location_source = "browser"
    else:
        location = get_location()
        if location:
            lat, lon = location
            location_source = "ip"
        else:
            print("Could not determine location")
            return

    if lat is None or lon is None:
        return

    try:
        # OpenWeather API endpoint
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Extract relevant data
        weather_data = {
            "temp": round(data["main"]["temp"], 1),
            "humidity": data["main"]["humidity"],
            "description": data["weather"][0]["description"].title(),
            "location": data["name"],
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "rain": data.get("rain", {}).get("1h", 0),  # Rain in last hour (mm)
            "clouds": data["clouds"]["all"],  # Cloud coverage %
            "wind_speed": round(data["wind"]["speed"], 1),
        }

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{timestamp}] Weather data updated (via {location_source}): {weather_data['location']} - {weather_data['description']}, {weather_data['temp']}°C"
        )

        # Emit to all connected clients
        socketio.emit("weather_update", {"data": weather_data, "timestamp": timestamp})

    except requests.exceptions.RequestException as e:
        print(f"OpenWeather API Error: {e}")
    except KeyError as e:
        print(f"Error parsing weather data: {e}")


def weather_update_loop():
    """Periodically fetch weather data"""
    while True:
        if not weather_simulation_mode:
            fetch_weather_data()
        time.sleep(WEATHER_UPDATE_INTERVAL)


# Routes
@app.route("/")
def dashboard():
    """Serve the main dashboard"""
    return render_template("index.html")


@app.route("/test")
def test_page():
    """Serve the LED test page"""
    return render_template("test.html")


@app.route("/sounds/<path:filename>")
def serve_sound(filename):
    """Serve audio files from the sound_effects directory."""
    sounds_dir = os.path.join(os.path.dirname(__file__), "sound_effects")
    return send_from_directory(sounds_dir, filename)


@app.route("/data_collection")
def data_collection_page():
    """Serve the data collection management page."""
    return render_template("data_collection.html")


@app.route("/api/ai_log", methods=["GET"])
def api_ai_log_get():
    """Return AI check rows filtered by date range.
    Query params: start (YYYY-MM-DD), end (YYYY-MM-DD). Both default to today.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    start = request.args.get("start", today)
    end = request.args.get("end", today)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM ai_check_log WHERE date(logged_at) BETWEEN ? AND ? ORDER BY id ASC",
            (start, end),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/ai_log/<int:row_id>", methods=["DELETE"])
def api_ai_log_delete(row_id):
    """Delete a single AI check row by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM ai_check_log WHERE id = ?", (row_id,))
    return jsonify({"deleted": row_id})


@app.route("/api/ai_log/bulk_delete", methods=["POST"])
def api_ai_log_bulk_delete():
    """Delete multiple rows. Expects JSON body {\"ids\": [1, 2, 3]}."""
    ids = request.get_json(force=True).get("ids", [])
    if not ids:
        return jsonify({"deleted": 0})
    placeholders = ",".join("?" * len(ids))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"DELETE FROM ai_check_log WHERE id IN ({placeholders})", ids)
    return jsonify({"deleted": len(ids)})


@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection from client"""
    print(f"Web client connected")
    emit(
        "status_update",
        {
            "online": esp32_status["online"],
            "last_seen": esp32_status["last_seen"],
            "last_heartbeat": esp32_status["last_heartbeat"],
            "uptime": esp32_status["uptime"],
            "heartbeat_count": esp32_status["heartbeat_count"],
            "status_type": "online" if esp32_status["online"] else "offline",
        },
    )
    emit(
        "config_info",
        {
            "mqtt_broker": MQTT_BROKER,
            "mqtt_port": MQTT_PORT,
            "wifi_ssid": WIFI_SSID,
        },
    )
    # Send current sensor readings on connect
    emit(
        "sensor_update",
        {
            "temperature": sensor_readings["temperature"],
            "pressure": sensor_readings["pressure"],
            "humidity": sensor_readings["humidity"],
            "rain": sensor_readings["rain"],
            "rain_analog": sensor_readings["rain_analog"],
            "servo_state": sensor_readings["servo_state"],
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        },
    )
    if sensor_readings["servo_state"] is not None:
        emit("servo_update", {"state": sensor_readings["servo_state"]})
    emit("weather_simulation_mode", {"active": weather_simulation_mode})
    if weather_simulation_mode and simulation_weather_data:
        emit(
            "weather_update",
            {
                "data": simulation_weather_data,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            },
        )
    elif weather_data.get("temp") is not None:
        emit(
            "weather_update",
            {"data": weather_data, "timestamp": datetime.now().strftime("%H:%M:%S")},
        )
    emit("esp32_simulation_mode", {"active": esp32_simulation_mode})
    if esp32_simulation_mode and simulation_sensor_data:
        emit(
            "sensor_update",
            {
                "temperature": simulation_sensor_data.get("temperature"),
                "pressure": simulation_sensor_data.get("pressure"),
                "humidity": simulation_sensor_data.get("humidity"),
                "rain": simulation_sensor_data.get("rain"),
                "rain_analog": simulation_sensor_data.get("rain_analog"),
                "servo_state": sensor_readings.get("servo_state"),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            },
        )


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection"""
    print(f"Web client disconnected")


@socketio.on("request_status")
def handle_status_request():
    """Handle manual status request from client"""
    emit(
        "status_update",
        {
            "online": esp32_status["online"],
            "last_seen": esp32_status["last_seen"],
            "last_heartbeat": esp32_status["last_heartbeat"],
            "uptime": esp32_status["uptime"],
            "heartbeat_count": esp32_status["heartbeat_count"],
            "status_type": "online" if esp32_status["online"] else "offline",
        },
    )


@socketio.on("servo_control")
def handle_servo_control(data):
    """Send open/close command to ESP32 servo via MQTT"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    command = data.get("state", "").lower()  # "open" or "close"
    if command not in ("open", "close", "closed"):
        emit(
            "console_log",
            {
                "message": f"[{timestamp}] Invalid servo command: {command}",
                "type": "error",
            },
        )
        return
    mqtt_client.publish(TOPIC_SERVO_CMD, command)
    print(f"[{timestamp}] Servo command sent: {command}")
    socketio.emit(
        "mqtt_message",
        {"topic": TOPIC_SERVO_CMD, "payload": command, "timestamp": timestamp},
    )


@socketio.on("request_weather")
def handle_weather_request():
    """Handle manual weather data request from web client"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] Manual weather refresh requested")

    # Emit console log
    emit(
        "console_log",
        {
            "message": f"[{timestamp}] Refreshing weather data...",
            "type": "info",
        },
    )

    # Fetch weather data immediately
    fetch_weather_data()


@socketio.on("set_weather_simulation")
def handle_set_weather_simulation(data):
    """Enable or disable weather simulation mode from the test page."""
    global weather_simulation_mode, simulation_weather_data
    active = data.get("active", False)
    weather_simulation_mode = active
    timestamp = datetime.now().strftime("%H:%M:%S")

    if active:
        simulation_weather_data = data.get("data", {})
        socketio.emit(
            "weather_update",
            {"data": simulation_weather_data, "timestamp": timestamp},
        )
        print(
            f"[{timestamp}] Weather simulation ENABLED: {simulation_weather_data.get('location', '?')}"
        )
    else:
        simulation_weather_data = {}
        print(f"[{timestamp}] Weather simulation DISABLED")
        fetch_weather_data()  # Immediately push live data to all clients

    socketio.emit("weather_simulation_mode", {"active": active})


@socketio.on("clear_warning_led")
def handle_clear_warning_led():
    """Turn off yellow LED — triggered by safe AI result or manual servo control."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    mqtt_client.publish(TOPIC_LED_WARNING, "off")
    print(f"[{timestamp}] Warning LED cleared (yellow off)")
    socketio.emit(
        "mqtt_message",
        {"topic": TOPIC_LED_WARNING, "payload": "off", "timestamp": timestamp},
    )


@socketio.on("warning_dismissed")
def handle_warning_dismissed():
    """User dismissed an AI warning — light up yellow LED on ESP32 (GPIO 11)."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    mqtt_client.publish(TOPIC_LED_WARNING, "on")
    print(f"[{timestamp}] Warning dismissed — yellow LED activated")
    socketio.emit(
        "mqtt_message",
        {"topic": TOPIC_LED_WARNING, "payload": "on", "timestamp": timestamp},
    )


@socketio.on("set_location")
def handle_set_location(data):
    """Receive browser geolocation from client."""
    global browser_location
    lat = data.get("lat")
    lon = data.get("lon")
    if lat is not None and lon is not None:
        browser_location["lat"] = lat
        browser_location["lon"] = lon
        browser_location["source"] = "browser"
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] Browser location received: {lat:.4f}, {lon:.4f}")
        # Immediately fetch weather with new location
        fetch_weather_data()
    else:
        print("Invalid location data received")


@socketio.on("set_esp32_simulation")
def handle_set_esp32_simulation(data):
    """Enable or disable ESP32 sensor simulation mode from the test page."""
    global esp32_simulation_mode, simulation_sensor_data
    active = data.get("active", False)
    esp32_simulation_mode = active
    timestamp = datetime.now().strftime("%H:%M:%S")

    if active:
        simulation_sensor_data = data.get("data", {})
        socketio.emit(
            "sensor_update",
            {
                "temperature": simulation_sensor_data.get("temperature"),
                "pressure": simulation_sensor_data.get("pressure"),
                "humidity": simulation_sensor_data.get("humidity"),
                "rain": simulation_sensor_data.get("rain"),
                "rain_analog": simulation_sensor_data.get("rain_analog"),
                "servo_state": sensor_readings.get("servo_state"),
                "timestamp": timestamp,
            },
        )
        socketio.emit(
            "status_update",
            {
                "online": True,
                "last_seen": timestamp,
                "last_heartbeat": timestamp,
                "uptime": "SIM",
                "heartbeat_count": None,
                "status_type": "online",
            },
        )
        print(
            f"[{timestamp}] ESP32 simulation ENABLED: temp={simulation_sensor_data.get('temperature')}°C"
        )
    else:
        simulation_sensor_data = {}
        socketio.emit(
            "status_update",
            {
                "online": esp32_status["online"],
                "last_seen": esp32_status["last_seen"],
                "last_heartbeat": esp32_status["last_heartbeat"],
                "uptime": esp32_status["uptime"],
                "heartbeat_count": esp32_status["heartbeat_count"],
                "status_type": "online" if esp32_status["online"] else "offline",
            },
        )
        print(f"[{timestamp}] ESP32 simulation DISABLED")

    socketio.emit("esp32_simulation_mode", {"active": active})


@socketio.on("run_ai_check")
def handle_run_ai_check():
    """Run ML inference on current sensor readings and return result to client."""
    timestamp = datetime.now().strftime("%H:%M:%S")

    if ai_model is None:
        emit("ai_check_result", {"error": "ML model not loaded"})
        return

    if esp32_simulation_mode and simulation_sensor_data:
        temp = simulation_sensor_data.get("temperature")
        humidity = simulation_sensor_data.get("humidity")
        rain_analog = simulation_sensor_data.get("rain_analog")
    else:
        temp = sensor_readings.get("temperature")
        humidity = sensor_readings.get("humidity")
        rain_analog = sensor_readings.get("rain_analog")

    if any(v is None for v in [temp, humidity, rain_analog]):
        emit(
            "ai_check_result",
            {"error": "Sensor data unavailable — is the ESP32 connected?"},
        )
        return

    try:
        input_data = pd.DataFrame(
            {
                "temperature": [float(temp)],
                "humidity": [float(humidity)],
                "water_sensor": [int(float(rain_analog))],
            }
        )

        prediction = int(ai_model.predict(input_data)[0])
        probabilities = ai_model.predict_proba(input_data)[0].tolist()

        current_weather = (
            simulation_weather_data
            if (weather_simulation_mode and simulation_weather_data)
            else weather_data
        )
        weather_rain = float(current_weather.get("rain") or 0)
        weather_desc = (current_weather.get("description") or "").lower()
        weather_is_raining = weather_rain > 0 or "rain" in weather_desc

        emit(
            "ai_check_result",
            {
                "timestamp": timestamp,
                "prediction": prediction,
                "probabilities": probabilities,
                "sensor_snapshot": {
                    "temperature": temp,
                    "humidity": humidity,
                    "rain_analog": rain_analog,
                    "simulated": esp32_simulation_mode,
                },
                "weather_snapshot": {
                    "location": current_weather.get("location"),
                    "description": current_weather.get("description"),
                    "rain": weather_rain,
                    "is_raining": weather_is_raining,
                    "simulated": weather_simulation_mode,
                },
            },
        )
        print(
            f"[{timestamp}] AI Check → pred={prediction}, probs={[round(p, 2) for p in probabilities]}, weather_rain={weather_is_raining}"
        )
        log_ai_check(
            {
                "prediction": prediction,
                "probabilities": probabilities,
                "sensor_snapshot": {
                    "temperature": temp,
                    "humidity": humidity,
                    "rain_analog": rain_analog,
                    "simulated": esp32_simulation_mode,
                },
                "weather_snapshot": {
                    "location": current_weather.get("location"),
                    "description": current_weather.get("description"),
                    "rain": weather_rain,
                    "is_raining": weather_is_raining,
                    "simulated": weather_simulation_mode,
                },
            }
        )
    except Exception as e:
        emit("ai_check_result", {"error": str(e)})
        print(f"[{timestamp}] AI Check Error: {e}")


if __name__ == "__main__":
    # Initialise SQLite database
    init_db()
    print(f"SQLite DB: {DB_PATH}")

    # Start MQTT client in background thread
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    # Start heartbeat watchdog thread
    watchdog_thread = threading.Thread(target=heartbeat_watchdog_loop, daemon=True)
    watchdog_thread.start()

    # Start weather update thread
    weather_thread = threading.Thread(target=weather_update_loop, daemon=True)
    weather_thread.start()

    print("Starting SyncGuard Dashboard...")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print("Dashboard will be available at: http://localhost:8080")

    # Start Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=8080, debug=True, allow_unsafe_werkzeug=True)
