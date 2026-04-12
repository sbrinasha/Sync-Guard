import pandas as pd
from sklearn.model_selection import train_test_split

# from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
import joblib

# Load data
data = pd.read_csv("Training_Data/training_datav2.csv")

# Features (inputs)
X = data[["temperature", "humidity", "water_sensor"]]

# Labels (output)
y = data["action"]

# Split data (train/test)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Create model
# model = DecisionTreeClassifier()
model = RandomForestClassifier(n_estimators=100, random_state=42)

# Train model
model.fit(X_train, y_train)

# Evaluate model
score = model.score(X_test, y_test)

# Save model
joblib.dump(model, "Training_Data/Model_V5.pkl")

print("Model trained and saved!")
print(f"Model accuracy: {score * 100:.2f}%")
print(f"Classes: {model.classes_} -> [0=OPEN, 1=WARNING, 2=CLOSE]")
