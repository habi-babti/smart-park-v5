
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import joblib
import os

def train_spot_recommender(csv_path="parking_data/reservations_history.csv"):
    if not os.path.exists(csv_path):
        print("❌ ERROR: File not found:", csv_path)
        return

    df = pd.read_csv(csv_path)

    if df.empty:
        print("⚠️ CSV is empty. Add data to reservations_history.csv first.")
        return

    if "spot_id" not in df.columns or "start_time" not in df.columns:
        print("❌ CSV missing required columns: 'spot_id' and 'start_time'")
        return

    # Clean & extract features
    df = df.dropna(subset=["spot_id", "start_time"])
    df["zone"] = df["spot_id"].str[0]
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df = df.dropna(subset=["start_time"])
    df["hour"] = df["start_time"].dt.hour
    df["weekday"] = df["start_time"].dt.dayofweek

    # Encode zone and spot
    le_zone = LabelEncoder()
    le_spot = LabelEncoder()
    df["zone_encoded"] = le_zone.fit_transform(df["zone"])
    df["spot_encoded"] = le_spot.fit_transform(df["spot_id"])

    X = df[["zone_encoded", "hour", "weekday"]]
    y = df["spot_encoded"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    os.makedirs("parking_data", exist_ok=True)
    joblib.dump(model, "parking_data/spot_model.pkl")
    joblib.dump(le_zone, "parking_data/zone_encoder.pkl")
    joblib.dump(le_spot, "parking_data/spot_encoder.pkl")

    print("✅ Model trained and saved:")
    print("• spot_model.pkl")
    print("• zone_encoder.pkl")
    print("• spot_encoder.pkl")

if __name__ == "__main__":
    train_spot_recommender()
