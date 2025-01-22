# app/routes.py
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, Credential
from app import db
import cv2
import numpy as np
from cryptography.fernet import Fernet
import base64
import json
from app.utils.s3 import S3Handler

auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('main.dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        user = User(
            username=request.form['username'],
            email=request.form['email']
        )
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    credentials = current_user.credentials.all()
    return render_template('dashboard.html', credentials=credentials)

@main_bp.route('/credential', methods=['POST'])
@login_required
def add_credential():
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image provided'})
    
    file = request.files['image']
    if not file:
        return jsonify({'success': False, 'error': 'Invalid image'})

    try:
        # Read image
        file_bytes = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        # Create encryption key
        key = Fernet.generate_key()
        cipher_suite = Fernet(key)
        print(f"Generated key: {base64.b64encode(key).decode('utf-8')}")
        
        # Prepare credentials data
        credentials_data = {
            'username': request.form['username'],
            'password': request.form['password']
        }
        
        # Encrypt the data
        json_data = json.dumps(credentials_data)
        encrypted_data = cipher_suite.encrypt(json_data.encode())
        binary_data = ''.join(format(byte, '08b') for byte in encrypted_data)
        
        # Embed in image
        data_index = 0
        for i in range(image.shape[0]):
            for j in range(image.shape[1]):
                for k in range(3):
                    if data_index < len(binary_data):
                        image[i, j, k] = (image[i, j, k] & 254) | int(binary_data[data_index])
                        data_index += 1
        
        # Convert to base64
        _, buffer = cv2.imencode('.png', image)
        image_base64 = base64.b64encode(buffer).decode('utf-8')

        # Upload to S3 if configured
        s3_url = None
        if current_app.config.get('AWS_ACCESS_KEY_ID'):
            try:
                s3_handler = S3Handler()
                s3_url = s3_handler.upload_image(image_base64)
            except Exception as s3_error:
                print(f"S3 upload failed: {str(s3_error)}")
        
        # Create credential record
        credential = Credential(
            website_name=request.form['website_name'],
            website_url=request.form['website_url'],
            image_data=image_base64,  # Keep local storage
            s3_image_url=s3_url,      # Store S3 URL if available
            encryption_key=base64.b64encode(key).decode('utf-8'),
            notes=request.form.get('notes', ''),
            user_id=current_user.id
        )
        
        db.session.add(credential)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@main_bp.route('/credential/<int:id>/get-password', methods=['GET'])
@login_required
def get_password(id):
    credential = Credential.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        # Get image data from local storage
        image_bytes = base64.b64decode(credential.image_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Extract binary data
        binary_data = ''
        for i in range(image.shape[0]):
            for j in range(image.shape[1]):
                for k in range(3):
                    binary_data += str(image[i, j, k] & 1)
                    if len(binary_data) >= 1120:  # Matches the encrypted data length
                        break
                if len(binary_data) >= 1120:
                    break
            if len(binary_data) >= 1120:
                break
        
        # Convert binary back to bytes
        extracted_bytes = bytearray()
        for i in range(0, 1120, 8):
            extracted_bytes.append(int(binary_data[i:i+8], 2))
        
        # Decrypt
        cipher_suite = Fernet(base64.b64decode(credential.encryption_key))
        decrypted_data = cipher_suite.decrypt(bytes(extracted_bytes))
        credentials = json.loads(decrypted_data.decode('utf-8'))
        
        return jsonify({
            'success': True,
            'password': credentials['password']
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@main_bp.route('/credential/<int:id>', methods=['DELETE'])
@login_required
def delete_credential(id):
    credential = Credential.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        # Delete from S3 if URL exists
        if credential.s3_image_url and current_app.config.get('AWS_ACCESS_KEY_ID'):
            try:
                s3_handler = S3Handler()
                s3_handler.delete_image(credential.s3_image_url)
            except Exception as s3_error:
                print(f"S3 delete failed: {str(s3_error)}")
        
        # Delete database record
        db.session.delete(credential)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Delete error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400