# SPDX-FileCopyrightText: 2026 Pardha Saradhi Edupalli
# SPDX-License-Identifier: MIT

import os
import hmac
import secrets
from getpass import getpass
from datetime import datetime, timezone
from flask import Flask, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect, FlaskForm
from wtforms import StringField, FloatField, SelectField, PasswordField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Email

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('ASSET_RENTAL_SECRET_KEY') or secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['ADMIN_PASSWORD'] = os.environ.get('ASSET_RENTAL_ADMIN_PASSWORD')

CSRFProtect(app)
db = SQLAlchemy(app)


def utc_now():
    # SQLite stores UTC timestamps without timezone information in this model.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def rental_cost(start, end, hourly_rate):
    hours = max((end - start).total_seconds() / 3600, 0.01)
    return round(hours * hourly_rate, 2)


def action_form_error(message):
    db.session.rollback()
    flash(message, "warning")
    return redirect(url_for("admin_dashboard"))


# --- DATABASE MODELS ---
class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    hourly_rate = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Available')  # Available, Rented, Maintenance

class RentalSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    user_email = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending, Active, Completed
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    total_cost = db.Column(db.Float, default=0.0)
    asset = db.relationship('Asset', backref=db.backref('rentals', lazy=True))

# --- FLASK-WTF FORMS ---
class AssetForm(FlaskForm):
    name = StringField('Asset Name', validators=[DataRequired()])
    category = SelectField(
        'Category',
        choices=[('Laptop', 'Laptop'), ('Camera', 'Camera'), ('Networking', 'Networking'), ('Tablet', 'Tablet')],
        validators=[DataRequired()]
    )
    hourly_rate = FloatField('Hourly Rate ($)', validators=[DataRequired(), NumberRange(min=0.5, max=500.0)])
    submit = SubmitField('Add Asset')

class RentalRequestForm(FlaskForm):
    user_name = StringField('Full Name', validators=[DataRequired()])
    user_email = StringField('University Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Submit Rental Request')

class AdminLoginForm(FlaskForm):
    password = PasswordField('Admin Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# --- ROUTES ---
@app.route('/')
@app.route('/browse')
def browse():
    assets = Asset.query.all()
    return render_template('browse.html', assets=assets)

@app.route('/request/<int:asset_id>', methods=['GET', 'POST'])
def request_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    if asset.status != 'Available':
        flash('This asset is currently unavailable.', 'warning')
        return redirect(url_for('browse'))
    form = RentalRequestForm()
    if form.validate_on_submit():
        rental = RentalSession(
            asset_id=asset.id,
            user_name=form.user_name.data,
            user_email=form.user_email.data,
            status='Pending'
        )
        db.session.add(rental)
        db.session.commit()
        flash('Rental request submitted for admin approval.', 'success')
        return redirect(url_for('browse'))
    return render_template('request_asset.html', asset=asset, form=form)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        admin_password = app.config['ADMIN_PASSWORD']
        if admin_password and hmac.compare_digest(form.password.data.encode(), admin_password.encode()):
            session.clear()
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid administrative password.', 'danger')
    return render_template('admin_login.html', form=form)

@app.post('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('browse'))

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    form = AssetForm()
    if form.validate_on_submit():
        new_asset = Asset(
            name=form.name.data,
            category=form.category.data,
            hourly_rate=form.hourly_rate.data
        )
        db.session.add(new_asset)
        db.session.commit()
        flash('New IT asset added to inventory.', 'success')
        return redirect(url_for('admin_dashboard'))

    assets = Asset.query.all()
    rentals = RentalSession.query.order_by(RentalSession.id.desc()).all()

    now = utc_now()
    for r in rentals:
        if r.status == 'Active' and r.start_time:
            r.live_cost = rental_cost(r.start_time, now, r.asset.hourly_rate)
        else:
            r.live_cost = r.total_cost

    available_count = Asset.query.filter_by(status='Available').count()
    rented_count = Asset.query.filter_by(status='Rented').count()
    maint_count = Asset.query.filter_by(status='Maintenance').count()

    return render_template(
        'admin_dashboard.html',
        form=form,
        assets=assets,
        rentals=rentals,
        chart_data=[available_count, rented_count, maint_count]
    )

@app.post('/admin/approve/<int:rental_id>')
def approve_rental(rental_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    rental = db.get_or_404(RentalSession, rental_id)
    claimed = db.session.execute(
        db.update(Asset).where(Asset.id == rental.asset_id, Asset.status == 'Available')
        .values(status='Rented')
    )
    if not claimed.rowcount:
        return action_form_error('This asset is no longer available.')
    approved = db.session.execute(
        db.update(RentalSession).where(RentalSession.id == rental_id, RentalSession.status == 'Pending')
        .values(status='Active', start_time=utc_now())
    )
    if not approved.rowcount:
        return action_form_error('Only a pending request can be approved.')
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


@app.post('/admin/complete/<int:rental_id>')
def complete_rental(rental_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    rental = db.get_or_404(RentalSession, rental_id)
    if rental.status != 'Active' or rental.start_time is None:
        return action_form_error('Only an active rental can be billed.')
    ended = utc_now()
    charge = rental_cost(rental.start_time, ended, rental.asset.hourly_rate)
    completed = db.session.execute(
        db.update(RentalSession).where(RentalSession.id == rental_id, RentalSession.status == 'Active')
        .values(status='Completed', end_time=ended, total_cost=charge)
    )
    if not completed.rowcount:
        return action_form_error('This rental has already ended.')
    rental.asset.status = 'Available'
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


@app.post('/admin/delete_asset/<int:asset_id>')
def delete_asset(asset_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    db.get_or_404(Asset, asset_id)
    has_rentals = db.select(RentalSession.id).where(RentalSession.asset_id == Asset.id).exists()
    removed = db.session.execute(
        db.delete(Asset).where(Asset.id == asset_id, ~has_rentals)
        .execution_options(synchronize_session=False)
    )
    if not removed.rowcount:
        return action_form_error('Assets with rental history must be kept.')
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    if not app.config['ADMIN_PASSWORD']:
        app.config['ADMIN_PASSWORD'] = getpass('Choose an admin password for this local run: ')
        if not app.config['ADMIN_PASSWORD']:
            raise SystemExit('An admin password is required.')
    with app.app_context():
        db.create_all()
        if not Asset.query.first():
            db.session.add_all([
                Asset(name='Dell XPS 15', category='Laptop', hourly_rate=5.00),
                Asset(name='Sony Alpha a7 IV', category='Camera', hourly_rate=8.50),
                Asset(name='iPad Pro 12.9"', category='Tablet', hourly_rate=3.50)
            ])
            db.session.commit()
    app.run()
