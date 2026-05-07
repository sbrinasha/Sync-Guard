from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import threading
import time
import os
import re
from datetime import datetime
import geocoder
import requests


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

app = Flask(__name__)
app.config["SECRET_KEY"] = "sync-guard-secret-2026"
socketio = SocketIO(app, cors_allowed_origins="*")

# MQTT Configuration — sourced from Sync_Guard_Sketch/config.h
MQTT_BROKER = _config.get("MQTT_SERVER", "172.20.10.4")
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
TOPIC_BLINK_TEST = "syncguard/blink-test"

MQTT_TOPICS = [
    (TOPIC_STATUS, 0),
    (TOPIC_HEARTBEAT, 0),
    (TOPIC_TEMPERATURE, 0),
    (TOPIC_PRESSURE, 0),
    (TOPIC_HUMIDITY, 0),
    (TOPIC_RAIN, 0),
    (TOPIC_RAIN_ANALOG, 0),
    (TOPIC_SERVO_STATE, 0),
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
    socketio.emit("mqtt_message", {"topic": topic, "payload": payload, "timestamp": timestamp})

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


def _emit_sensor_update(timestamp):
    """Emit the current sensor_readings snapshot to all connected clients."""
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

    # Get location
    location = get_location()
    if not location:
        print("Could not determine location")
        return

    lat, lon = location

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
            f"[{timestamp}] Weather data updated: {weather_data['location']} - {weather_data['description']}, {weather_data['temp']}°C"
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
    if weather_data.get("temp") is not None:
        emit(
            "weather_update",
            {"data": weather_data, "timestamp": datetime.now().strftime("%H:%M:%S")},
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
    socketio.emit("mqtt_message", {"topic": TOPIC_SERVO_CMD, "payload": command, "timestamp": timestamp})


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


if __name__ == "__main__":
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
