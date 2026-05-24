import joblib
import pandas as pd

# Load the trained model
model = joblib.load("Training_Data/Model_V6_1.6.pkl")

print("=== Sync Guard Model Tester ===")
print("Enter sensor values to predict action\n")

# Get user input
temperature = float(input("Temperature (°C): "))
humidity = float(input("Humidity (%): "))
water_sensor = int(input("Water Sensor (analog 0-4095, dry=<100, wet=>3000): "))
# api_value = int(input("Weather API value: "))

# Create input dataframe
input_data = pd.DataFrame(
    {
        "temperature": [temperature],
        "humidity": [humidity],
        "water_sensor": [water_sensor],
        # "api_value": [api_value],
    }
)

# Make prediction
prediction = model.predict(input_data)[0]
probabilities = model.predict_proba(input_data)[0]

# Map action to label
action_labels = {0: "OPEN", 1: "WARNING", 2: "CLOSE"}
action_descriptions = {
    0: "[Safe] Safe to keep window open",
    1: "[Caution] - Monitor conditions closely",
    2: "[Close] Close window for protection",
}

# Display result
print("\n" + "=" * 50)
print(f"PREDICTION: {action_labels[prediction]} ({prediction})")
print("=" * 50)

print("\n Confidence Distribution:")
for i, prob in enumerate(probabilities):
    bar_length = int(prob * 30)
    bar = "█" * bar_length + "░" * (30 - bar_length)
    print(f"  {action_labels[i]:8s} ({i}): {bar} {prob*100:5.1f}%")

print("\n💡 Recommendation:")
print(f"  {action_descriptions[prediction]}")

if prediction == 1:
    print("\n WARNING: state triggered. Consider:")
    print("  - Check weather forecast")
    print("  - Monitor sensor readings")
    print("  - Prepare to close if conditions worsen")
