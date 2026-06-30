# Blood Bank Management System

I built this as a full blood bank management web app using Python, Flask and some ML models. It started as a desktop Tkinter app and I converted it to a web app so anyone can access it through a link.

## What it does

Basically manages everything a blood bank needs — donors, blood inventory, requests from hospitals, and uses ML to make predictions.

The ML part was the interesting bit:
- Checks if a donor is eligible to donate (age, weight, hemoglobin, last donation date etc.) — Random Forest model, got 94% accuracy
- Flags blood units that are about to expire so staff can use them before they go to waste
- Forecasts how much blood each type will be needed next month
- Checks if two blood types are compatible for transfusion

## Pages

- **Dashboard** — overview stats and charts
- **Donors** — add, search, view donor eligibility status
- **Inventory** — track blood stock with expiry risk alerts
- **Requests** — log and fulfill hospital blood requests
- **ML Tools** — run the ML models interactively

## Tech used

- Python, Flask
- SQLite for the database
- scikit-learn for the ML models
- Chart.js for the charts in the browser
- Deployed on Render.com

## Run it locally

```bash
pip install flask scikit-learn pandas numpy gunicorn
python app.py
```

Then open `http://localhost:5000`

## Deploy

Hosted on Render.com — just connect the GitHub repo and it builds automatically.
