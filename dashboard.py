from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import threading
import time
from datetime import datetime
import geocoder
import requests

app = Flask(__name__)
app.config["SECRET_KEY"] = "sync-guard-secret-2026"
socketio = SocketIO(app, cors_allowed_origins="*")

# MQTT Configuration
MQTT_BROKER = "172.20.10.3"  # Your Mac's IP - Mosquitto running locally
MQTT_PORT = 1883
MQTT_TOPICS = [("esp32/status", 0), ("esp32/sensor_data", 0)]

# OpenWeather API Configuration
OPENWEATHER_API_KEY = "120d0873a392ff37d15d9562aa258a4f"  # Replace with your API key
WEATHER_UPDATE_INTERVAL = 300  # Update every 5 minutes (300 seconds)

# Global state
esp32_status = {"online": False, "last_seen": None, "sensor_data": None}
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
            print(f"📡 Subscribed to: {topic}")
    else:
        print(f"Failed to connect to MQTT Broker, return code {rc}")


def on_message(client, userdata, msg):
    """Callback when a message is received from MQTT broker"""
    topic = msg.topic
    payload = msg.payload.decode("utf-8")
    timestamp = datetime.now().strftime("%H:%M:%S")

    print(f"📨 [{timestamp}] Received from {topic}: {payload}")

    if topic == "esp32/status":
        # Update ESP32 status
        esp32_status["online"] = payload == "online"
        esp32_status["last_seen"] = timestamp

        # Emit status update to all connected web clients
        socketio.emit(
            "status_update", {"online": esp32_status["online"], "last_seen": timestamp}
        )

    elif topic == "esp32/sensor_data":
        # Update sensor data
        esp32_status["sensor_data"] = payload
        esp32_status["last_seen"] = timestamp

        # Emit sensor data to all connected web clients
        socketio.emit("sensor_update", {"value": payload, "timestamp": timestamp})


def on_disconnect(client, userdata, rc):
    """Callback when disconnected from MQTT broker"""
    if rc != 0:
        print(
            f"⚠️ Unexpected disconnection from MQTT Broker. Attempting to reconnect..."
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
        print(f"❌ MQTT Connection Error: {e}")


def get_location():
    """Get current location using geocoder"""
    try:
        g = geocoder.ip("me")
        if g.ok:
            return g.latlng  # Returns [latitude, longitude]
        return None
    except Exception as e:
        print(f"❌ Geocoder Error: {e}")
        return None


def fetch_weather_data():
    """Fetch weather data from OpenWeather API"""
    global weather_data

    # Get location
    location = get_location()
    if not location:
        print("⚠️ Could not determine location")
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
            f"🌤️ [{timestamp}] Weather data updated: {weather_data['location']} - {weather_data['description']}, {weather_data['temp']}°C"
        )

        # Emit to all connected clients
        socketio.emit("weather_update", {"data": weather_data, "timestamp": timestamp})

    except requests.exceptions.RequestException as e:
        print(f"❌ OpenWeather API Error: {e}")
    except KeyError as e:
        print(f"❌ Error parsing weather data: {e}")


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


@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection from client"""
    print(f"🔌 Web client connected")
    # Send current ESP32 status to newly connected client
    emit(
        "status_update",
        {"online": esp32_status["online"], "last_seen": esp32_status["last_seen"]},
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
    print(f"🔌 Web client disconnected")


@socketio.on("request_status")
def handle_status_request():
    """Handle manual status request from client"""
    emit(
        "status_update",
        {"online": esp32_status["online"], "last_seen": esp32_status["last_seen"]},
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


if __name__ == "__main__":
    # Start MQTT client in background thread
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    # Start weather update thread
    weather_thread = threading.Thread(target=weather_update_loop, daemon=True)
    weather_thread.start()

    print("🚀 Starting SyncGuard Dashboard...")
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print("🌐 Dashboard will be available at: http://localhost:8080")

    # Start Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=8080, debug=True, allow_unsafe_werkzeug=True)
