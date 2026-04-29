"""
serializer.py — SyncGuard UART → MQTT Bridge

Reads structured sensor data from the ESP32 over USB/Serial and
publishes it to the MQTT broker. Useful when the ESP32 is in
OFFLINE mode (no WiFi) or as a secondary data path.

The sketch prints a line prefixed with "SENSOR:" containing JSON
for every sensor reading cycle, e.g.:
  SENSOR:{"temperature":25.3,"humidity":60.0,"rain":2500,"rain_status":"Light Rain"}

Usage:
  python serializer.py                         # auto-detect port
  python serializer.py --port /dev/tty.usbserial-0001
  python serializer.py --port COM3 --broker 192.168.1.105
"""

import argparse
import json
import sys
import time

import paho.mqtt.client as mqtt
import serial
import serial.tools.list_ports

# ─── Configuration defaults ───────────────────────────────────────────────────
DEFAULT_BAUD = 115200
DEFAULT_BROKER = "192.168.1.105"
DEFAULT_PORT = 1883
SENSOR_TOPIC = "esp32/sensor_data/json"
TEMPERATURE_TOPIC = "esp32/sensor_data/temperature"
HUMIDITY_TOPIC = "esp32/sensor_data/humidity"
RAIN_TOPIC = "esp32/sensor_data/rain"
LOG_TOPIC = "esp32/system/logs"
SENSOR_PREFIX = "SENSOR:"
# ─────────────────────────────────────────────────────────────────────────────


def find_esp32_port() -> str | None:
    """Return the first serial port that looks like an ESP32/CP210x/CH340."""
    known_ids = {
        (0x10C4, 0xEA60),  # Silicon Labs CP210x
        (0x1A86, 0x7523),  # CH340
        (0x0403, 0x6001),  # FTDI FT232R
    }
    for port in serial.tools.list_ports.comports():
        if (port.vid, port.pid) in known_ids:
            return port.device
        if port.description and any(
            kw in port.description for kw in ("CP210", "CH340", "USB Serial", "UART")
        ):
            return port.device
    return None


def on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    if rc == 0:
        print(f"[MQTT] Connected to broker")
    else:
        print(f"[MQTT] Connection failed (rc={rc})")


def on_disconnect(client: mqtt.Client, userdata, rc: int) -> None:
    print(f"[MQTT] Disconnected (rc={rc}). Retrying…")


def publish_sensor(client: mqtt.Client, data: dict) -> None:
    """Publish parsed sensor fields to individual MQTT topics."""
    # Full JSON blob
    client.publish(SENSOR_TOPIC, json.dumps(data))

    if "temperature" in data and data["temperature"] is not None:
        client.publish(TEMPERATURE_TOPIC, str(data["temperature"]))

    if "humidity" in data and data["humidity"] is not None:
        client.publish(HUMIDITY_TOPIC, str(data["humidity"]))

    if "rain" in data:
        rain_payload = json.dumps(
            {
                "value": data["rain"],
                "status": data.get("rain_status", ""),
            }
        )
        client.publish(RAIN_TOPIC, rain_payload)

    print(
        f"[MQTT] Published → temp={data.get('temperature')}°C  "
        f"humidity={data.get('humidity')}%  "
        f"rain={data.get('rain')} ({data.get('rain_status', '')})"
    )


def run(serial_port: str, baud: int, broker: str, broker_port: int) -> None:
    # ── MQTT setup ────────────────────────────────────────────────────────────
    mqttc = mqtt.Client(client_id="syncguard-serializer")
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect

    try:
        mqttc.connect(broker, broker_port, keepalive=60)
    except OSError as e:
        print(f"[MQTT] Cannot reach broker at {broker}:{broker_port} — {e}")
        sys.exit(1)

    mqttc.loop_start()

    # ── Serial setup ──────────────────────────────────────────────────────────
    try:
        ser = serial.Serial(serial_port, baud, timeout=2)
    except serial.SerialException as e:
        print(f"[Serial] Cannot open {serial_port} — {e}")
        mqttc.loop_stop()
        sys.exit(1)

    print(f"[Serial] Listening on {serial_port} @ {baud} baud")
    print(f"[MQTT]   Broker {broker}:{broker_port}")
    print("Press Ctrl+C to quit.\n")

    # Flush stale bytes on open
    time.sleep(2)
    ser.reset_input_buffer()

    try:
        while True:
            try:
                raw = ser.readline()
            except serial.SerialException as e:
                print(f"[Serial] Read error — {e}. Retrying in 3 s…")
                time.sleep(3)
                continue

            if not raw:
                continue

            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue

            if not line:
                continue

            # Forward every serial line as a log message
            print(f"[Serial] {line}")
            if mqttc.is_connected():
                mqttc.publish(LOG_TOPIC, line)

            # Look for structured sensor data
            if line.startswith(SENSOR_PREFIX):
                json_str = line[len(SENSOR_PREFIX) :]
                try:
                    data = json.loads(json_str)
                    publish_sensor(mqttc, data)
                except json.JSONDecodeError as e:
                    print(f"[Warn] Bad JSON on sensor line: {e}")

    except KeyboardInterrupt:
        print("\n[Serializer] Stopped by user.")
    finally:
        ser.close()
        mqttc.loop_stop()
        mqttc.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="SyncGuard UART → MQTT bridge")
    parser.add_argument(
        "--port",
        default=None,
        help="Serial port (e.g. /dev/tty.usbserial-0001 or COM3)",
    )
    parser.add_argument(
        "--baud",
        default=DEFAULT_BAUD,
        type=int,
        help=f"Baud rate (default {DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--broker",
        default=DEFAULT_BROKER,
        help=f"MQTT broker IP (default {DEFAULT_BROKER})",
    )
    parser.add_argument(
        "--broker-port",
        default=DEFAULT_PORT,
        type=int,
        dest="broker_port",
        help=f"MQTT port (default {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    serial_port = args.port
    if serial_port is None:
        serial_port = find_esp32_port()
        if serial_port is None:
            print("[Error] No ESP32 serial port detected. Use --port to specify one.")
            print("Available ports:")
            for p in serial.tools.list_ports.comports():
                print(f"  {p.device}  —  {p.description}")
            sys.exit(1)
        print(f"[Serial] Auto-detected port: {serial_port}")

    run(serial_port, args.baud, args.broker, args.broker_port)


if __name__ == "__main__":
    main()
