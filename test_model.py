import joblib
import pandas as pd

# Load the trained model
model = joblib.load("Training_Data/model.pkl")

print("=== Sync Guard Model Tester ===")
print("Enter sensor values to predict action\n")

# Get user input
water = int(input("Water detected? (0 = No, 1 = Yes): "))
humidity = int(input("Humidity (%): "))
temperature = int(input("Temperature (°C): "))
api_value = int(input("Weather API value: "))

# Create input dataframe
input_data = pd.DataFrame(
    {
        "water": [water],
        "humidity": [humidity],
        "temperature": [temperature],
        "api_value": [api_value],
    }
)

# Make prediction
prediction = model.predict(input_data)[0]

# Display result
print("\n" + "=" * 40)
print(f"Prediction: {'OPEN (1)' if prediction == 1 else 'CLOSE (0)'}")
print("=" * 40)

if prediction == 1:
    print("✓ Safe to keep open")
else:
    print("✗ Should close for protection")
