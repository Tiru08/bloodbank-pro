from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import threading
import os
import sys
from functools import wraps

sys.path.insert(0, os.path.dirname(__file__))
from database import init_db, get_connection, BLOOD_TYPES
from ml_engine import (
    donor_eligibility_model, expiry_risk_model,
    demand_forecast_model, compatibility_checker
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bloodbank-secret-2024-change-me")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


class User(UserMixin):
    def __init__(self, id, username, role, full_name):
        self.id = id
        self.username = username
        self.role = role
        self.full_name = full_name


@login_manager.user_loader
def load_user(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row["id"], row["username"], row["role"], row["full_name"])
    return None


def admin_required(f):
    """Restrict a route to admin role only."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.role != "admin":
            flash("Admin access required for this action.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


# ── Train ML models on startup ──────────────────────────────
def train_models():
    donor_eligibility_model.train()
    conn = get_connection()
    rows = conn.execute("SELECT blood_type, units_used, month, year FROM demand_history").fetchall()
    conn.close()
    MONTH_MAP = {m: i+1 for i, m in enumerate([
        "January","February","March","April","May","June",
        "July","August","September","October","November","December"
    ])}
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["month_num"] = df["month"].map(MONTH_MAP)
        demand_forecast_model.train(df)

init_db()
train_models()  # train synchronously so models ready on first request


# ── AUTH ROUTES ──────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_connection()
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            user = User(row["id"], row["username"], row["role"], row["full_name"])
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/users")
@login_required
@admin_required
def users():
    conn = get_connection()
    rows = conn.execute("SELECT id, username, role, full_name, created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("users.html", users=[dict(r) for r in rows])


@app.route("/users/add", methods=["POST"])
@login_required
@admin_required
def add_user():
    f = request.form
    username = f.get("username", "").strip()
    password = f.get("password", "")
    role = f.get("role", "staff")
    full_name = f.get("full_name", "")
    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("users"))
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO users (username, password_hash, role, full_name)
            VALUES (?, ?, ?, ?)
        """, (username, generate_password_hash(password), role, full_name))
        conn.commit()
        flash(f"User '{username}' created.", "success")
    except sqlite3.IntegrityError:
        flash("That username already exists.", "danger")
    conn.close()
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash("You can't delete your own account.", "danger")
        return redirect(url_for("users"))
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    flash("User removed.", "success")
    return redirect(url_for("users"))


# ── PAGES ────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    conn = get_connection()
    total_donors   = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    total_units    = conn.execute("SELECT COALESCE(SUM(units),0) FROM inventory WHERE status='available'").fetchone()[0]
    critical_units = conn.execute("""
        SELECT COALESCE(SUM(units),0) FROM inventory
        WHERE status='available' AND julianday(expiry_date)-julianday('now') <= 7
    """).fetchone()[0]
    pending_req    = conn.execute("SELECT COUNT(*) FROM requests WHERE status='pending'").fetchone()[0]

    # Inventory by blood type
    inv_rows = conn.execute("""
        SELECT blood_type, COALESCE(SUM(units),0) as total
        FROM inventory WHERE status='available'
        GROUP BY blood_type
    """).fetchall()
    inv_data = {bt: 0 for bt in BLOOD_TYPES}
    for r in inv_rows:
        inv_data[r["blood_type"]] = r["total"]

    # Expiry risk summary
    all_inv = conn.execute(
        "SELECT id, blood_type, units, collection_date, expiry_date FROM inventory WHERE status='available'"
    ).fetchall()
    conn.close()

    assessed = expiry_risk_model.assess_inventory([dict(r) for r in all_inv])
    risk_summary = expiry_risk_model.get_summary(assessed)

    return render_template("dashboard.html",
        now=datetime.now().strftime("%A, %d %B %Y"),
        total_donors=total_donors,
        total_units=total_units,
        critical_units=critical_units,
        pending_req=pending_req,
        inv_data=inv_data,
        risk_summary=risk_summary,
        blood_types=BLOOD_TYPES
    )


@app.route("/donors")
def donors():
    search = request.args.get("search", "").lower()
    bt_filter = request.args.get("bt", "All")
    conn = get_connection()
    rows = conn.execute("SELECT * FROM donors ORDER BY id DESC").fetchall()
    conn.close()

    donors_list = []
    for r in rows:
        d = dict(r)
        if search and search not in d["name"].lower():
            continue
        if bt_filter != "All" and d["blood_type"] != bt_filter:
            continue
        result = donor_eligibility_model.predict(
            d["age"] or 25, d["weight"] or 60, d["hemoglobin"] or 13.5,
            d["last_donation"] or "2000-01-01", d["donations_count"] or 0,
            d["medical_conditions"] or ""
        )
        d["eligible"] = result["eligible"]
        d["confidence"] = result["confidence"]
        donors_list.append(d)

    return render_template("donors.html",
        donors=donors_list, blood_types=BLOOD_TYPES,
        search=search, bt_filter=bt_filter
    )


@app.route("/donors/add", methods=["GET", "POST"])
@login_required
def add_donor():
    if request.method == "POST":
        f = request.form
        conn = get_connection()
        conn.execute("""
            INSERT INTO donors (name, age, blood_type, gender, phone, email,
                weight, hemoglobin, last_donation, medical_conditions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["name"], int(f.get("age") or 0), f["blood_type"], f["gender"],
            f.get("phone",""), f.get("email",""),
            float(f.get("weight") or 0), float(f.get("hemoglobin") or 0),
            f.get("last_donation",""), f.get("medical_conditions","")
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("donors"))
    return render_template("donor_form.html", blood_types=BLOOD_TYPES, donor=None)


@app.route("/donors/<int:donor_id>")
def donor_detail(donor_id):
    conn = get_connection()
    donor = conn.execute("SELECT * FROM donors WHERE id=?", (donor_id,)).fetchone()
    conn.close()
    if not donor:
        return redirect(url_for("donors"))
    d = dict(donor)
    result = donor_eligibility_model.predict(
        d["age"] or 25, d["weight"] or 60, d["hemoglobin"] or 13.5,
        d["last_donation"] or "2000-01-01", d["donations_count"] or 0,
        d["medical_conditions"] or ""
    )
    return render_template("donor_detail.html", donor=d, ml=result)


@app.route("/donors/<int:donor_id>/edit", methods=["GET", "POST"])
@login_required
def edit_donor(donor_id):
    conn = get_connection()
    donor = dict(conn.execute("SELECT * FROM donors WHERE id=?", (donor_id,)).fetchone())
    if request.method == "POST":
        f = request.form
        conn.execute("""
            UPDATE donors SET name=?, age=?, blood_type=?, gender=?, phone=?, email=?,
                weight=?, hemoglobin=?, last_donation=?, medical_conditions=?
            WHERE id=?
        """, (
            f["name"], int(f.get("age") or 0), f["blood_type"], f["gender"],
            f.get("phone",""), f.get("email",""),
            float(f.get("weight") or 0), float(f.get("hemoglobin") or 0),
            f.get("last_donation",""), f.get("medical_conditions",""), donor_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("donor_detail", donor_id=donor_id))
    conn.close()
    return render_template("donor_form.html", blood_types=BLOOD_TYPES, donor=donor)


@app.route("/inventory")
def inventory():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM inventory ORDER BY expiry_date ASC"
    ).fetchall()
    conn.close()
    assessed = expiry_risk_model.assess_inventory([dict(r) for r in rows])
    return render_template("inventory.html", items=assessed, blood_types=BLOOD_TYPES)


@app.route("/inventory/add", methods=["POST"])
@login_required
def add_stock():
    f = request.form
    exp_default = (datetime.now() + timedelta(days=42)).strftime("%Y-%m-%d")
    conn = get_connection()
    conn.execute("""
        INSERT INTO inventory (blood_type, units, collection_date, expiry_date, status)
        VALUES (?, ?, ?, ?, 'available')
    """, (f["blood_type"], int(f.get("units",1)),
          f.get("collection_date", datetime.now().strftime("%Y-%m-%d")),
          f.get("expiry_date", exp_default)))
    conn.commit()
    conn.close()
    return redirect(url_for("inventory"))


@app.route("/requests")
def blood_requests():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM requests ORDER BY requested_at DESC").fetchall()
    conn.close()
    return render_template("requests.html", requests=[dict(r) for r in rows], blood_types=BLOOD_TYPES)


@app.route("/requests/add", methods=["POST"])
@login_required
def add_request():
    f = request.form
    conn = get_connection()
    conn.execute("""
        INSERT INTO requests (patient_name, blood_type, units_needed, hospital, urgency)
        VALUES (?, ?, ?, ?, ?)
    """, (f["patient_name"], f["blood_type"], int(f.get("units_needed",1)),
          f.get("hospital",""), f.get("urgency","normal")))
    conn.commit()
    conn.close()
    return redirect(url_for("blood_requests"))


@app.route("/requests/<int:req_id>/fulfill", methods=["POST"])
@login_required
def fulfill_request(req_id):
    conn = get_connection()
    conn.execute("UPDATE requests SET status='fulfilled', fulfilled_at=? WHERE id=?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), req_id))
    conn.commit()
    conn.close()
    return redirect(url_for("blood_requests"))


@app.route("/ml")
def ml_tools():
    return render_template("ml_tools.html", blood_types=BLOOD_TYPES)


# ── API ENDPOINTS ────────────────────────────────────────────

@app.route("/api/eligibility", methods=["POST"])
def api_eligibility():
    d = request.json
    try:
        result = donor_eligibility_model.predict(
            int(d.get("age", 25)), float(d.get("weight", 60)),
            float(d.get("hemoglobin", 13.5)), d.get("last_donation", "2020-01-01"),
            int(d.get("donations_count", 0)), d.get("medical_conditions", "")
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/forecast")
def api_forecast():
    forecasts = demand_forecast_model.forecast_all()
    return jsonify(forecasts)


@app.route("/api/compatibility")
def api_compatibility():
    donor = request.args.get("donor", "O+")
    recipient = request.args.get("recipient", "A+")
    result = compatibility_checker.check(donor, recipient)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
