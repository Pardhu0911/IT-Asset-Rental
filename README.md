# IT Asset Rental & Live Billing System

A university department lends laptops, cameras and tablets by the hour. In this Flask app, a borrower requests a device and an administrator approves it. The rental clock starts on approval. Returning the device closes the bill and makes it available to the next borrower.

**Pardha Saradhi Edupalli** · University of Cincinnati

## Run locally on Windows

Run these commands in PowerShell from this project folder with Python 3.12 installed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Choose an admin password at the local terminal prompt, then open <http://127.0.0.1:5000>. The first run creates `instance/assets.db` and adds three example devices. The Bootstrap styles and Chart.js chart load from a CDN. If you want the same local admin password or signed sessions across launches, configure `ASSET_RENTAL_ADMIN_PASSWORD` and `ASSET_RENTAL_SECRET_KEY` privately in your environment.

## Try a rental

1. In the catalog, select **Request Rental**. Submit a fictional name and valid-format email.
2. Open **Admin Login**, enter the password you chose, then approve the pending request.
3. Refresh the dashboard during the rental to recalculate the displayed cost.
4. Select **Complete & Bill**. The database stores the final amount and makes the asset available again.

For a two-hour rental of a $5/hour laptop, the charge is **$10.00**. The implementation uses elapsed hours, a minimum of 0.01 hour and rounding to cents. The dashboard computes costs on page load. Its doughnut chart shows available, rented and maintenance inventory.

## Implementation

`Asset` holds inventory and hourly rates. `RentalSession` stores both requests and active/completed rentals. Flask-WTF validates forms, SQLAlchemy persists records in SQLite, and Jinja renders the catalog, request, login and admin pages.

An approval updates the rental and the asset in one database transaction. If two requests are pending for the same laptop, approving the first leaves the second pending. Administrative changes use CSRF-protected forms. Billing history stays available after a device is returned.

Copyright © 2026 Pardha Saradhi Edupalli. [MIT license](LICENSE)
