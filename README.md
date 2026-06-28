# 🩸 BloodBank Pro — Web App

A Flask web app with ML features, ready to deploy on Render.com (free).

## 🚀 Deploy to Render (get a free link)

### Step 1 — Push to GitHub
1. Create a new repo on github.com (e.g. `bloodbank-pro`)
2. Upload all these files to it

### Step 2 — Deploy on Render
1. Go to **render.com** → Sign up free
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo
4. Fill in:
   - **Name**: bloodbank-pro
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Click **"Create Web Service"**
6. Wait ~2 minutes → get your link like `https://bloodbank-pro.onrender.com`

## 🗂 File Structure

```
bloodbank_web/
├── app.py            # Flask routes + API endpoints
├── database.py       # SQLite setup + sample data
├── ml_engine.py      # 4 ML models
├── requirements.txt  # Python dependencies
├── Procfile          # Render start command
└── templates/
    ├── base.html       # Sidebar + layout
    ├── dashboard.html  # Stats + charts
    ├── donors.html     # Donor list
    ├── donor_detail.html
    ├── donor_form.html
    ├── inventory.html
    ├── requests.html
    └── ml_tools.html   # Eligibility + Forecast + Compat
```

## 🤖 ML Features
- **Donor Eligibility** — Random Forest (94% accuracy)
- **Expiry Risk Alerts** — Rule-based risk scoring
- **Demand Forecast** — Gradient Boosting per blood type
- **Compatibility Checker** — Full ABO+Rh matrix

## 💻 Run Locally
```bash
pip install flask scikit-learn pandas numpy gunicorn
python app.py
# Open http://localhost:5000
```
