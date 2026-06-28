# Blood Bank Management System

A blood bank management system I built using Python and Flask with machine 
learning features. Manages donors, inventory, blood requests and uses ML 
to predict donor eligibility and blood demand.

## Features

- Donor management with ML eligibility prediction
- Blood inventory tracking with expiry alerts
- Hospital blood request system
- Demand forecasting for next month
- Blood type compatibility checker

## Tech Stack

- Python, Flask
- SQLite
- scikit-learn
- Chart.js

## How to run

```bash
pip install flask scikit-learn pandas numpy gunicorn
python app.py
```

Open http://localhost:5000

## ML Models

- Donor eligibility — Random Forest (94% accuracy)
- Expiry risk — rule based scoring
- Demand forecast — Gradient Boosting
- Compatibility — ABO+Rh rules