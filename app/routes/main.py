# app/routes/main.py
from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from app.models import Credential
from app import db
import base64

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    credentials = current_user.credentials.all()
    return render_template('main/dashboard.html', credentials=credentials)

@main_bp.route('/credential', methods=['POST'])
@login_required
def add_credential():
    if 'image' in request.files:
        file = request.files['image']
        if file:
            # Convert image to base64
            image_data = base64.b64encode(file.read()).decode('utf-8')
    else:
        image_data = None

    credential = Credential(
        website_name=request.form['website_name'],
        website_url=request.form['website_url'],
        username=request.form['username'],
        password=request.form['password'],
        notes=request.form.get('notes', ''),
        image_data=image_data,
        user_id=current_user.id
    )
    db.session.add(credential)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/credential/<int:id>', methods=['DELETE'])
@login_required
def delete_credential(id):
    credential = Credential.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(credential)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/credential/<int:id>', methods=['PUT'])
@login_required
def update_credential(id):
    credential = Credential.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    if 'image' in request.files:
        file = request.files['image']
        if file:
            image_data = base64.b64encode(file.read()).decode('utf-8')
            credential.image_data = image_data
    
    credential.website_name = request.form.get('website_name', credential.website_name)
    credential.website_url = request.form.get('website_url', credential.website_url)
    credential.username = request.form.get('username', credential.username)
    
    if 'password' in request.form:
        credential.password = request.form['password']
    
    credential.notes = request.form.get('notes', credential.notes)
    
    db.session.commit()
    return jsonify({'success': True})
