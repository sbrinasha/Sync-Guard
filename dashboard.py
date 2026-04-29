from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import threading
import time
import json
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
MQTT_TOPICS = [("esp32/status", 0), ("esp32/sensor_data", 0), ("esp32/system/logs", 0)]

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
_last_heartbeat_epoch = None  # float seconds (time.time()) for timeout checks
weather_sim_active = False  # When True, real API fetch is suppressed
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
        # Subscribe to topics
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos)
            print(f"Subscribed to: {topic}")
    else:
        print(f"Failed to connect to MQTT Broker, return code {rc}")


def on_message(client, userdata, msg):
    """Callback when a message is received from MQTT broker"""
    topic = msg.topic
    payload = msg.payload.decode("utf-8")
    timestamp = datetime.now().strftime("%H:%M:%S")

    print(f"[{timestamp}] Received from {topic}: {payload}")

    if topic == "esp32/status":
        # Try to parse JSON heartbeat, fall back to plain string
        try:
            parsed = json.loads(payload)
            status_type = parsed.get("status", "")
            uptime = parsed.get("uptime")
            count = parsed.get("count")
        except (json.JSONDecodeError, ValueError):
            status_type = payload  # plain "online" / "offline" (e.g. from simulate)
            uptime = None
            count = None

        global _last_heartbeat_epoch
        is_online = status_type in ("online", "heartbeat")

        esp32_status["online"] = is_online
        esp32_status["last_seen"] = timestamp
        if is_online:
            esp32_status["last_heartbeat"] = timestamp
            esp32_status["uptime"] = uptime
            esp32_status["heartbeat_count"] = count
            _last_heartbeat_epoch = time.time()

        socketio.emit(
            "status_update",
            {
                "online": is_online,
                "last_seen": timestamp,
                "last_heartbeat": esp32_status["last_heartbeat"],
                "uptime": uptime,
                "heartbeat_count": count,
                "status_type": status_type,
            },
        )

    elif topic == "esp32/system/logs":
        # Forward ESP32 log line to all connected web clients
        socketio.emit("esp_log", {"message": payload, "timestamp": timestamp})

    elif topic == "esp32/sensor_data":
        # Update sensor data
        esp32_status["sensor_data"] = payload
        esp32_status["last_seen"] = timestamp

        # Try to parse structured JSON payload
        try:
            parsed = json.loads(payload)
            socketio.emit(
                "sensor_update",
                {
                    "temp": parsed.get("temp"),
                    "humidity": parsed.get("humidity"),
                    "rain": parsed.get("rain"),
                    "timestamp": timestamp,
                },
            )
        except (json.JSONDecodeError, ValueError):
            socketio.emit("sensor_update", {"value": payload, "timestamp": timestamp})


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
    global weather_data, weather_sim_active

    if weather_sim_active:
        print("Weather simulation mode active — skipping real API fetch")
        return

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
    # Send connection config so the UI can display MQTT/WiFi details
    emit(
        "config_info",
        {
            "mqtt_broker": MQTT_BROKER,
            "mqtt_port": MQTT_PORT,
            "wifi_ssid": WIFI_SSID,
        },
    )
    # Send current weather data if available
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


@socketio.on("button_test")
def handle_button_test():
    """Handle button test from web client - send command to ESP32"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] Button test triggered - sending to ESP32")

    # Publish to MQTT topic that ESP32 is subscribed to
    mqtt_client.publish("esp32/button_test", "BLINK")

    # Emit confirmation back to web client
    emit(
        "console_log",
        {
            "message": f"[{timestamp}] Button pressed - Command sent to ESP32",
            "type": "info",
        },
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


@socketio.on("led_control")
def handle_led_control(data):
    """Handle LED control command from test page"""
    color = data.get("color", "").lower()
    timestamp = datetime.now().strftime("%H:%M:%S")

    # Validate color
    if color not in ["red", "green", "yellow"]:
        emit(
            "led_console_log",
            {
                "message": f"[{timestamp}] Invalid color: {color}",
                "type": "error",
            },
        )
        return

    # MQTT topic for this LED color
    topic = f"esp32/test/led/{color}"

    print(f"[{timestamp}] LED Control: {color.upper()} - Publishing to {topic}")

    # Publish to MQTT broker (payload: "BLINK3")
    mqtt_client.publish(topic, "BLINK3")

    # Emit confirmation back to web client
    emit(
        "led_console_log",
        {
            "message": f"[{timestamp}] {color.upper()} LED command sent → {topic}",
            "type": "success",
        },
    )


@socketio.on("simulate_sensor")
def handle_simulate_sensor(data):
    """Simulate ESP32 sensor data by publishing to MQTT broker"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    temp = data.get("temp")
    humidity = data.get("humidity")
    rain = data.get("rain")

    payload = json.dumps({"temp": temp, "humidity": humidity, "rain": rain})

    # Mark ESP32 as online and publish sensor data through MQTT
    mqtt_client.publish("esp32/status", "online")
    mqtt_client.publish("esp32/sensor_data", payload)

    # Also emit directly so the dashboard updates even if MQTT loop has a delay
    socketio.emit("status_update", {"online": True, "last_seen": timestamp})
    socketio.emit(
        "sensor_update",
        {"temp": temp, "humidity": humidity, "rain": rain, "timestamp": timestamp},
    )

    print(
        f"[{timestamp}] Simulated sensor: temp={temp}, humidity={humidity}, rain={rain}"
    )
    emit(
        "sim_console_log",
        {
            "message": f"[{timestamp}] Published → esp32/sensor_data: temp={temp}°C, humidity={humidity}%, rain={rain}",
            "type": "success",
        },
    )


@socketio.on("simulate_status")
def handle_simulate_status(data):
    """Simulate ESP32 online/offline status by publishing to MQTT broker"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status = "online" if data.get("online") else "offline"

    mqtt_client.publish("esp32/status", status)

    # Also emit directly
    socketio.emit(
        "status_update", {"online": data.get("online"), "last_seen": timestamp}
    )

    print(f"[{timestamp}] Simulated status: {status}")
    emit(
        "sim_console_log",
        {
            "message": f"[{timestamp}] Published → esp32/status: {status}",
            "type": "success" if data.get("online") else "warning",
        },
    )


@socketio.on("set_weather_sim_mode")
def handle_set_weather_sim_mode(data):
    """Toggle weather simulation mode — suppresses real API updates when active"""
    global weather_sim_active
    weather_sim_active = data.get("active", False)
    timestamp = datetime.now().strftime("%H:%M:%S")
    mode_str = "ON" if weather_sim_active else "OFF"
    print(f"[{timestamp}] Weather simulation mode: {mode_str}")
    emit(
        "sim_console_log",
        {
            "message": f"[{timestamp}] Weather simulation mode: {mode_str}",
            "type": "success" if weather_sim_active else "warning",
        },
    )


@socketio.on("simulate_weather")
def handle_simulate_weather(data):
    """Emit a simulated weather_update event directly to all clients"""
    global weather_data
    timestamp = datetime.now().strftime("%H:%M:%S")

    sim_data = {
        "temp": data.get("temp"),
        "humidity": data.get("humidity"),
        "description": data.get("description", "Simulated"),
        "location": "Kuching (1.55, 110.3333)",
        "lat": 1.55,
        "lon": 110.3333,
        "rain": data.get("rain", 0),
        "clouds": data.get("clouds", 0),
        "wind_speed": 0,
    }
    weather_data.update(sim_data)

    socketio.emit("weather_update", {"data": sim_data, "timestamp": timestamp})
    print(
        f"[{timestamp}] Simulated weather: {sim_data['description']}, {sim_data['temp']}°C"
    )
    emit(
        "sim_console_log",
        {
            "message": f"[{timestamp}] Simulated weather → {sim_data['description']}, temp={sim_data['temp']}°C, humidity={sim_data['humidity']}%, rain={sim_data['rain']}mm",
            "type": "success",
        },
    )


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
