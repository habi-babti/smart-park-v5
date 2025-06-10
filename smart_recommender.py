import datetime
import os
import pandas as pd
import joblib

def recommend_best_spot(zone=None, available_df=None, current_time=None):
    if available_df is None or available_df.empty:
        return None

    if current_time is None:
        current_time = datetime.datetime.now()

    try:
        model = joblib.load("parking_data/spot_model.pkl")
        zone_encoder = joblib.load("parking_data/zone_encoder.pkl")
        spot_encoder = joblib.load("parking_data/spot_encoder.pkl")
    except FileNotFoundError:
        return None  # gracefully fail if AI model isn't trained yet

    hour = current_time.hour
    weekday = current_time.weekday()

    # 🌍 GLOBAL RECOMMENDATION MODE (loop through all zones)
    if zone is None:
        zones = available_df["zone"].unique()
        for z in zones:
            encoded_zone = zone_encoder.transform([z])[0]
            features = [[encoded_zone, hour, weekday]]
            predicted = model.predict(features)[0]
            predicted_spot = spot_encoder.inverse_transform([predicted])[0]

            available_spots = available_df[available_df["zone"] == z]["spot_id"].tolist()
            if predicted_spot in available_spots:
                return predicted_spot  # Return first valid prediction globally

        # Fallback: return first available
        return available_df.sort_values("spot_id").iloc[0]["spot_id"]

    # 🧠 ZONE-SPECIFIC RECOMMENDATION MODE
    try:
        zone_encoded = zone_encoder.transform([zone])[0]
        features = [[zone_encoded, hour, weekday]]
        predicted = model.predict(features)[0]
        predicted_spot = spot_encoder.inverse_transform([predicted])[0]

        # Log recommendation
        log_row = {
            "timestamp": current_time.isoformat(),
            "zone": zone,
            "hour": hour,
            "weekday": weekday,
            "predicted_spot": predicted_spot
        }
        log_file = "parking_data/ai_recommendation_log.csv"
        pd.DataFrame([log_row]).to_csv(log_file, mode='a', header=not os.path.exists(log_file), index=False)

        # Check if the prediction is actually available
        available_spots = available_df[available_df["zone"] == zone]["spot_id"].tolist()
        if predicted_spot in available_spots:
            return predicted_spot
        elif available_spots:
            return available_spots[0]
        else:
            return None

    except Exception as e:
        return None
