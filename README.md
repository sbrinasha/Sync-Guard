# Sync-Guard

Sync-Guard is an ESP32-based smart home safety dashboard that uses MQTT for live device communication and Flask for monitoring and control.

## Overview

The ESP32 publishes sensor and device status data through MQTT.
The Flask dashboard subscribes to those MQTT topics, displays live readings, and sends control commands back to the device.

## Frameworks and Protocols

- Flask (Python)
- MQTT (communication protocol)
- Arduino MQTT libraries (ESP32 side)

## Programming Languages

- Python
- C++

## Installation

Install project dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Run the dashboard:

```bash
python dashboard.py
```

## Broker Commands

Start Mosquitto:

```bash
brew services start mosquitto
```

Restart Mosquitto:

```bash
brew services restart mosquitto
```

Verify Mosquitto is running:

```bash
brew services list | grep mosquitto
```

Stop Mosquitto:

```bash
brew services stop mosquitto
```

## Useful Commands

Find local IP address:

```bash
ifconfig en0 | grep "inet " | awk '{print $2}'
```

Kill old dashboard process on port 8080:

```bash
kill -9 $(lsof -ti :8080)
```

## Notes

- Tags: `#SereyyyKO` `#Amendesiak`


## MQTT Broker Setup (Mosquitto on macOS)

### Installation

1. **Install Mosquitto using Homebrew:**
   ```bash
   brew install mosquitto
   ```

2. **Create Configuration File:**
   
   Create a config file to allow connections on port 1883:
   ```bash
   cat > /opt/homebrew/etc/mosquitto/mosquitto.conf << 'EOF'
   # Mosquitto Configuration for SyncGuard
   listener 1883
   allow_anonymous true
   EOF
   ```

3. **Start Mosquitto Service:**
   ```bash
   brew services start mosquitto
   ```
   
   This will start Mosquitto automatically on boot.

### Configuration

- **Config File Location:** `/opt/homebrew/etc/mosquitto/mosquitto.conf`
- **Default Port:** `1883`
- **Your Mac's IP:** Run to find your local IP
  ```bash
  ifconfig en0 | grep "inet " | awk '{print $2}'
  ```

### Testing the Broker

1. **Test broker connectivity:**
   ```bash
   mosquitto_pub -h localhost -t test/topic -m "hello"
   ```

2. **Subscribe to see all messages:**
   
   In one terminal, run:
   ```bash
   mosquitto_sub -h localhost -t '#' -v
   ```
   
   In another terminal, publish a message:
   ```bash
   mosquitto_pub -h localhost -t test/topic -m "test message"
   ```
   
   You should see the message appear in the subscriber terminal.

3. **Monitor ESP32 messages:**
   ```bash
   mosquitto_sub -h localhost -t 'esp32/#' -v
   ```
   
   This will show all messages from ESP32 (status and sensor data).

### Common Commands

**Check if Mosquitto is running:**
```bash
brew services list | grep mosquitto
```

**View active connections on port 1883:**
```bash
lsof -i :1883
```

**Stop the broker:**
```bash
brew services stop mosquitto
```

**Start the broker:**
```bash
brew services start mosquitto
```

**Restart the broker:**
```bash
brew services restart mosquitto
```

**Test connection manually:**
```bash
mosquitto_pub -h localhost -t test/connection -m "testing"
```

### Troubleshooting

**If you get "Connection refused" errors:**

1. Check if Mosquitto is running:
   ```bash
   brew services list
   ```

2. Restart the service:
   ```bash
   brew services restart mosquitto
   ```

3. Check if port 1883 is in use:
   ```bash
   lsof -i :1883
   ```

4. View Mosquitto logs (if available):
   ```bash
   tail -f /opt/homebrew/var/log/mosquitto.log
   ```

### Update Configuration After Installation

After installing Mosquitto, update the following files with your Mac's IP address:

1. **dashboard.py** - Change `MQTT_BROKER` to your Mac's IP
2. **Sync_Guard_Sketch.ino** - Change `mqtt_server` to your Mac's IP

Example: If your Mac's IP is `192.168.1.100`:
- dashboard.py: `MQTT_BROKER = "192.168.1.100"`
- Sync_Guard_Sketch.ino: `const char* mqtt_server = "192.168.1.100";`

# SETUP FOR TEST MODEL

source .venv/bin/activate
