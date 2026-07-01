import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bloodbank.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Render gives postgres:// but psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


class HybridRow:
    """Behaves like sqlite3.Row: supports row['col'] and row[0] both."""
    def __init__(self, row_dict):
        self._dict = row_dict
        self._values = list(row_dict.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def keys(self):
        return self._dict.keys()

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def items(self):
        return self._dict.items()

    def __iter__(self):
        return iter(self._values)

    def __repr__(self):
        return repr(self._dict)


class HybridCursor:
    """Wraps a psycopg2 RealDictCursor so fetchone()/fetchall() return
    HybridRow objects instead of plain dicts."""
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        return HybridRow(row) if row is not None else None

    def fetchall(self):
        return [HybridRow(r) for r in self._cur.fetchall()]

    def __getattr__(self, name):
        return getattr(self._cur, name)


class PGConnWrapper:
    """Wraps a psycopg2 connection so .execute() on the connection itself
    works like sqlite3's shortcut, and rows behave like dicts AND tuples."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=()):
        query = _to_pg_query(query)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        return HybridCursor(cur)

    def executemany(self, query, seq_of_params):
        query = _to_pg_query(query)
        cur = self._conn.cursor()
        cur.executemany(query, seq_of_params)
        return cur

    def executescript(self, script):
        cur = self._conn.cursor()
        cur.execute(script)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def cursor(self):
        return HybridCursor(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))


def _to_pg_query(query):
    """Convert sqlite-style ? placeholders to postgres %s placeholders,
    and AUTOINCREMENT -> SERIAL for schema statements."""
    query = query.replace("?", "%s")
    return query


def get_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return PGConnWrapper(conn)
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    conn = get_connection()

    if USE_POSTGRES:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            blood_type TEXT NOT NULL,
            units INTEGER DEFAULT 0,
            collection_date TEXT,
            expiry_date TEXT,
            donor_id INTEGER,
            status TEXT DEFAULT 'available'
        );

        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            blood_type TEXT,
            units_used INTEGER,
            month TEXT,
            year INTEGER
        );

        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'staff',
            full_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()

        c.execute("SELECT COUNT(*) AS cnt FROM donors")
        count = c.fetchone()["cnt"]
        if count == 0:
            _seed_sample_data(conn)

        c.execute("SELECT COUNT(*) AS cnt FROM users")
        user_count = c.fetchone()["cnt"]
        if user_count == 0:
            from werkzeug.security import generate_password_hash
            conn.execute("""
                INSERT INTO users (username, password_hash, role, full_name)
                VALUES (?, ?, ?, ?)
            """, ("admin", generate_password_hash("admin123"), "admin", "Administrator"))

        conn.commit()
        conn.close()

    else:
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

        count = c.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
        if count == 0:
            _seed_sample_data(conn, sqlite_cursor=c)

        user_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            from werkzeug.security import generate_password_hash
            c.execute("""
                INSERT INTO users (username, password_hash, role, full_name)
                VALUES (?, ?, ?, ?)
            """, ("admin", generate_password_hash("admin123"), "admin", "Administrator"))

        conn.commit()
        conn.close()


def _seed_sample_data(conn, sqlite_cursor=None):
    """Works for both backends. conn.execute()/.executemany() route correctly
    via PGConnWrapper or sqlite3.Connection — both support that interface."""
    exec_many = sqlite_cursor.executemany if sqlite_cursor else conn.executemany
    exec_one = sqlite_cursor.execute if sqlite_cursor else conn.execute

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

    exec_many("""
        INSERT INTO donors (name, age, blood_type, gender, phone, email, weight, hemoglobin,
                            last_donation, donations_count, medical_conditions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, donors)

    inventory = []
    for blood_type in BLOOD_TYPES:
        for _ in range(random.randint(2, 8)):
            collection_days_ago = random.randint(1, 40)
            collection_date = (datetime.now() - timedelta(days=collection_days_ago)).strftime("%Y-%m-%d")
            expiry_date = (datetime.now() + timedelta(days=(42 - collection_days_ago))).strftime("%Y-%m-%d")
            units = random.randint(1, 5)
            status = "available" if collection_days_ago < 42 else "expired"
            inventory.append((blood_type, units, collection_date, expiry_date, status))

    exec_many("""
        INSERT INTO inventory (blood_type, units, collection_date, expiry_date, status)
        VALUES (?, ?, ?, ?, ?)
    """, inventory)

    demand = []
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    for year in [2023, 2024, 2025]:
        for month in months:
            for bt in BLOOD_TYPES:
                units_used = random.randint(5, 50)
                demand.append((bt, units_used, month, year))

    exec_many("""
        INSERT INTO demand_history (blood_type, units_used, month, year)
        VALUES (?, ?, ?, ?)
    """, demand)

    hospitals = ["Apollo Hospital", "Fortis Healthcare", "AIIMS Mumbai", "Kokilaben Hospital", "Nanavati Hospital"]
    for _ in range(15):
        bt = random.choice(BLOOD_TYPES)
        urgency = random.choice(["normal", "urgent", "critical"])
        status = random.choice(["pending", "fulfilled", "pending"])
        req_date = (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M:%S")
        exec_one("""
            INSERT INTO requests (patient_name, blood_type, units_needed, hospital, urgency, status, requested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"Patient {random.randint(100,999)}", bt, random.randint(1, 4),
              random.choice(hospitals), urgency, status, req_date))
