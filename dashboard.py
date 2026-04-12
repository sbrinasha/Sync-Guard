from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import threading
import time
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "sync-guard-secret-2026"
socketio = SocketIO(app, cors_allowed_origins="*")

# MQTT Configuration
MQTT_BROKER = "172.20.10.3"  # Your Mac's IP - Mosquitto running locally
MQTT_PORT = 1883
MQTT_TOPICS = [("esp32/status", 0), ("esp32/sensor_data", 0)]

# Global state
esp32_status = {"online": False, "last_seen": None, "sensor_data": None}

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


if __name__ == "__main__":
    # Start MQTT client in background thread
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    print("🚀 Starting SyncGuard Dashboard...")
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print("🌐 Dashboard will be available at: http://localhost:8080")

    # Start Flask-SocketIO server
    socketio.run(app, host="0.0.0.0", port=8080, debug=True, allow_unsafe_werkzeug=True)
