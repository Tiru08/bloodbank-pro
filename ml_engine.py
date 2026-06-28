import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings("ignore")

class DonorEligibilityModel:
    """Predicts if a donor is eligible to donate blood."""

    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=1)
        self.trained = False

    def _generate_training_data(self, n=1000):
        np.random.seed(42)
        age = np.random.randint(18, 65, n)
        weight = np.random.uniform(45, 100, n)
        hemoglobin = np.random.uniform(10.0, 18.0, n)
        days_since_last = np.random.randint(0, 400, n)
        donations = np.random.randint(0, 20, n)
        has_condition = np.random.randint(0, 2, n)

        eligible = (
            (age >= 18) & (age <= 60) &
            (weight >= 50) &
            (hemoglobin >= 12.5) &
            (days_since_last >= 90) &
            (has_condition == 0)
        ).astype(int)

        # Add some noise
        noise_idx = np.random.choice(n, size=int(n * 0.05), replace=False)
        eligible[noise_idx] = 1 - eligible[noise_idx]

        return pd.DataFrame({
            "age": age, "weight": weight, "hemoglobin": hemoglobin,
            "days_since_last": days_since_last, "donations": donations,
            "has_condition": has_condition
        }), eligible

    def train(self):
        X, y = self._generate_training_data()
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        self.model.fit(X_train, y_train)
        self.trained = True
        return self.model.score(X_test, y_test)

    def predict(self, age, weight, hemoglobin, last_donation_date, donations_count, medical_conditions):
        if not self.trained:
            self.train()

        try:
            last = datetime.strptime(last_donation_date, "%Y-%m-%d")
            days_since = (datetime.now() - last).days
        except:
            days_since = 999

        has_condition = 1 if medical_conditions and medical_conditions.strip() else 0
        features = [[age, weight, hemoglobin, days_since, donations_count, has_condition]]

        prob = self.model.predict_proba(features)[0]
        eligible = self.model.predict(features)[0]

        reasons = []
        if age < 18 or age > 60:
            reasons.append(f"Age {age} is outside eligible range (18–60)")
        if weight < 50:
            reasons.append(f"Weight {weight}kg is below minimum (50kg)")
        if hemoglobin < 12.5:
            reasons.append(f"Hemoglobin {hemoglobin} g/dL is below threshold (12.5)")
        if days_since < 90:
            reasons.append(f"Only {days_since} days since last donation (need 90+)")
        if has_condition:
            reasons.append(f"Medical condition(s) reported: {medical_conditions}")

        return {
            "eligible": bool(eligible),
            "confidence": round(float(max(prob)) * 100, 1),
            "reasons": reasons,
            "days_since_last": days_since,
            "next_eligible_date": (datetime.now() + timedelta(days=max(0, 90 - days_since))).strftime("%d %b %Y") if days_since < 90 else "Now"
        }


class ExpiryRiskModel:
    """Classifies blood units by expiry risk and suggests action."""

    SHELF_LIFE_DAYS = 42  # Standard for whole blood / RBC

    def assess_inventory(self, inventory_rows):
        results = []
        today = datetime.now().date()

        for row in inventory_rows:
            try:
                expiry = datetime.strptime(row["expiry_date"], "%Y-%m-%d").date()
                days_left = (expiry - today).days
                collection = datetime.strptime(row["collection_date"], "%Y-%m-%d").date()
                age_days = (today - collection).days
                pct_life_used = age_days / self.SHELF_LIFE_DAYS

                if days_left < 0:
                    risk = "expired"
                    color = "#e74c3c"
                    action = "Discard immediately"
                elif days_left <= 3:
                    risk = "critical"
                    color = "#e74c3c"
                    action = "Use within 3 days or discard"
                elif days_left <= 7:
                    risk = "high"
                    color = "#f39c12"
                    action = "Prioritize for immediate use"
                elif days_left <= 14:
                    risk = "medium"
                    color = "#f1c40f"
                    action = "Schedule for use soon"
                else:
                    risk = "low"
                    color = "#27ae60"
                    action = "Normal rotation"

                results.append({
                    "id": row["id"],
                    "blood_type": row["blood_type"],
                    "units": row["units"],
                    "expiry_date": row["expiry_date"],
                    "days_left": days_left,
                    "risk": risk,
                    "color": color,
                    "action": action,
                    "pct_life_used": round(pct_life_used * 100, 1)
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["days_left"])
        return results

    def get_summary(self, assessed):
        summary = {"expired": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        for item in assessed:
            summary[item["risk"]] += item["units"]
        return summary


class DemandForecastModel:
    """Forecasts blood demand for next month using Gradient Boosting."""

    def __init__(self):
        self.models = {}
        self.trained = False

    def train(self, demand_df):
        """demand_df: columns = [blood_type, month_num, year, units_used]"""
        if demand_df.empty:
            return False

        blood_types = demand_df["blood_type"].unique()
        for bt in blood_types:
            df = demand_df[demand_df["blood_type"] == bt].copy()
            if len(df) < 5:
                continue
            X = df[["month_num", "year"]].values
            y = df["units_used"].values
            model = GradientBoostingRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)
            self.models[bt] = model

        self.trained = bool(self.models)
        return self.trained

    def forecast_next_month(self, blood_type):
        if blood_type not in self.models:
            return None

        today = datetime.now()
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_num = next_month.month
        year = next_month.year

        pred = self.models[blood_type].predict([[month_num, year]])[0]

        # Estimate uncertainty based on feature importance-like heuristic
        margin = pred * 0.15
        return {
            "blood_type": blood_type,
            "month": next_month.strftime("%B %Y"),
            "forecast_units": max(0, round(pred)),
            "lower": max(0, round(pred - margin)),
            "upper": round(pred + margin)
        }

    def forecast_all(self):
        from database import BLOOD_TYPES
        results = []
        for bt in BLOOD_TYPES:
            f = self.forecast_next_month(bt)
            if f:
                results.append(f)
        return results


class CompatibilityChecker:
    """Blood type compatibility rules."""

    # donor -> list of compatible recipients
    CAN_DONATE_TO = {
        "O-":  ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
        "O+":  ["O+", "A+", "B+", "AB+"],
        "A-":  ["A-", "A+", "AB-", "AB+"],
        "A+":  ["A+", "AB+"],
        "B-":  ["B-", "B+", "AB-", "AB+"],
        "B+":  ["B+", "AB+"],
        "AB-": ["AB-", "AB+"],
        "AB+": ["AB+"],
    }

    # recipient -> list of compatible donors
    CAN_RECEIVE_FROM = {
        "O-":  ["O-"],
        "O+":  ["O-", "O+"],
        "A-":  ["O-", "A-"],
        "A+":  ["O-", "O+", "A-", "A+"],
        "B-":  ["O-", "B-"],
        "B+":  ["O-", "O+", "B-", "B+"],
        "AB-": ["O-", "A-", "B-", "AB-"],
        "AB+": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    }

    RARITY = {
        "O-": "Very Rare (~6%)", "AB-": "Rare (~1%)", "B-": "Rare (~2%)",
        "A-": "Uncommon (~6%)", "O+": "Common (~38%)", "A+": "Common (~34%)",
        "B+": "Common (~9%)", "AB+": "Common (~4%)"
    }

    def check(self, donor_type, recipient_type):
        compatible = recipient_type in self.CAN_DONATE_TO.get(donor_type, [])
        return {
            "donor": donor_type,
            "recipient": recipient_type,
            "compatible": compatible,
            "donor_can_give_to": self.CAN_DONATE_TO.get(donor_type, []),
            "recipient_can_receive_from": self.CAN_RECEIVE_FROM.get(recipient_type, []),
            "donor_rarity": self.RARITY.get(donor_type, "Unknown"),
            "recipient_rarity": self.RARITY.get(recipient_type, "Unknown"),
        }


# Singleton instances
donor_eligibility_model = DonorEligibilityModel()
expiry_risk_model = ExpiryRiskModel()
demand_forecast_model = DemandForecastModel()
compatibility_checker = CompatibilityChecker()
