import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bloodbank.db")

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS donors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        blood_type TEXT,
        gender TEXT,
        phone TEXT,
        email TEXT,
        weight REAL,
        hemoglobin REAL,
        last_donation TEXT,
        donations_count INTEGER DEFAULT 0,
        medical_conditions TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        blood_type TEXT NOT NULL,
        units INTEGER DEFAULT 0,
        collection_date TEXT,
        expiry_date TEXT,
        donor_id INTEGER,
        status TEXT DEFAULT 'available',
        FOREIGN KEY (donor_id) REFERENCES donors(id)
    );

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        blood_type TEXT,
        units_needed INTEGER,
        hospital TEXT,
        urgency TEXT DEFAULT 'normal',
        status TEXT DEFAULT 'pending',
        requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
        fulfilled_at TEXT
    );

    CREATE TABLE IF NOT EXISTS demand_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        blood_type TEXT,
        units_used INTEGER,
        month TEXT,
        year INTEGER
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'staff',
        full_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Seed with sample data if empty
    count = c.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    if count == 0:
        _seed_sample_data(c)

    # Seed default admin account if no users exist
    user_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        from werkzeug.security import generate_password_hash
        c.execute("""
            INSERT INTO users (username, password_hash, role, full_name)
            VALUES (?, ?, ?, ?)
        """, ("admin", generate_password_hash("admin123"), "admin", "Administrator"))

    conn.commit()
    conn.close()

def _seed_sample_data(c):
    first_names = ["Aarav", "Priya", "Rahul", "Sneha", "Vikram", "Ananya", "Rohan", "Kavya",
                   "Arjun", "Pooja", "Suresh", "Meera", "Kiran", "Neha", "Amit", "Divya",
                   "Ravi", "Sunita", "Ajay", "Rekha", "Sanjay", "Lakshmi", "Deepak", "Asha"]
    last_names = ["Sharma", "Patel", "Singh", "Kumar", "Reddy", "Nair", "Iyer", "Mehta",
                  "Joshi", "Gupta", "Verma", "Rao", "Shah", "Pillai", "Chatterjee", "Das"]

    conditions_pool = ["", "", "", "", "hypertension", "diabetes", "asthma", ""]
    
    donors = []
    for i in range(40):
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        age = random.randint(18, 60)
        blood_type = random.choice(BLOOD_TYPES)
        gender = random.choice(["Male", "Female"])
        last_donation_days = random.randint(0, 365)
        last_donation = (datetime.now() - timedelta(days=last_donation_days)).strftime("%Y-%m-%d")
        weight = round(random.uniform(50, 90), 1)
        hemoglobin = round(random.uniform(11.5, 17.5), 1)
        donations_count = random.randint(0, 15)
        conditions = random.choice(conditions_pool)
        phone = f"9{random.randint(100000000, 999999999)}"
        email = f"{name.split()[0].lower()}{random.randint(10,99)}@email.com"

        donors.append((name, age, blood_type, gender, phone, email, weight, hemoglobin,
                       last_donation, donations_count, conditions))

    c.executemany("""
        INSERT INTO donors (name, age, blood_type, gender, phone, email, weight, hemoglobin,
                            last_donation, donations_count, medical_conditions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, donors)

    # Inventory — varied expiry dates
    inventory = []
    for blood_type in BLOOD_TYPES:
        for _ in range(random.randint(2, 8)):
            collection_days_ago = random.randint(1, 40)
            collection_date = (datetime.now() - timedelta(days=collection_days_ago)).strftime("%Y-%m-%d")
            expiry_date = (datetime.now() + timedelta(days=(42 - collection_days_ago))).strftime("%Y-%m-%d")
            units = random.randint(1, 5)
            status = "available" if collection_days_ago < 42 else "expired"
            inventory.append((blood_type, units, collection_date, expiry_date, status))

    c.executemany("""
        INSERT INTO inventory (blood_type, units, collection_date, expiry_date, status)
        VALUES (?, ?, ?, ?, ?)
    """, inventory)

    # Historical demand
    demand = []
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    for year in [2023, 2024, 2025]:
        for month in months:
            for bt in BLOOD_TYPES:
                units_used = random.randint(5, 50)
                demand.append((bt, units_used, month, year))

    c.executemany("""
        INSERT INTO demand_history (blood_type, units_used, month, year)
        VALUES (?, ?, ?, ?)
    """, demand)

    # Sample requests
    hospitals = ["Apollo Hospital", "Fortis Healthcare", "AIIMS Mumbai", "Kokilaben Hospital", "Nanavati Hospital"]
    for _ in range(15):
        bt = random.choice(BLOOD_TYPES)
        urgency = random.choice(["normal", "urgent", "critical"])
        status = random.choice(["pending", "fulfilled", "pending"])
        req_date = (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO requests (patient_name, blood_type, units_needed, hospital, urgency, status, requested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"Patient {random.randint(100,999)}", bt, random.randint(1, 4),
              random.choice(hospitals), urgency, status, req_date))
