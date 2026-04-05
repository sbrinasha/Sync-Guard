import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
import joblib

# Load data
data = pd.read_csv("Training_Data/dataset.csv")

# Features (inputs)
X = data[["water", "humidity", "temperature", "api_value"]]

# Labels (output)
y = data["action"]

# Split data (train/test)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Create model
model = DecisionTreeClassifier()

# Train model
model.fit(X_train, y_train)

# Save model
joblib.dump(model, "Training_Data/model.pkl")

print("Model trained and saved!")
