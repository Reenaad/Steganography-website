import os
from flask import Flask, render_template, request, redirect, flash, send_from_directory
from werkzeug.utils import secure_filename
from stegano import lsb
import uuid
import hashlib
import base64
from cryptography.fernet import Fernet, InvalidToken

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_flash_messages'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max upload

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_fernet_key(password):
    digest = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(digest)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/encode', methods=['GET', 'POST'])
def encode():
    if request.method == 'POST':
        # Check if file is present
        if 'image' not in request.files:
            flash('No image file part')
            return redirect(request.url)
        
        file = request.files['image']
        message = request.form.get('message')
        password = request.form.get('password')

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if not message or not password:
            flash('Secret message and password cannot be empty')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Generate unique output filename
            output_filename = f"encoded_{uuid.uuid4().hex}.png"
            output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            try:
                # Encrypt the message
                f = Fernet(get_fernet_key(password))
                encrypted_message = f.encrypt(message.encode()).decode()

                # Stegano works best with PNGs, saving as PNG preserves LSB
                secret_img = lsb.hide(filepath, encrypted_message)
                secret_img.save(output_filepath)
                
                # Cleanup original upload optionally
                if os.path.exists(filepath):
                    os.remove(filepath)
                    
                return render_template('result.html', mode='encode', filename=output_filename)
            except Exception as e:
                flash(f'Error encoding image: {str(e)}')
                return redirect(request.url)
        else:
            flash('Allowed image types are png, jpg, jpeg')
            return redirect(request.url)

    return render_template('encode.html')

@app.route('/decode', methods=['GET', 'POST'])
def decode():
    if request.method == 'POST':
        if 'image' not in request.files:
            flash('No image file part')
            return redirect(request.url)
        
        file = request.files['image']
        password = request.form.get('password')

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if not password:
            flash('Password cannot be empty')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                secret_message_encrypted = lsb.reveal(filepath)
                
                # Cleanup the uploaded file after reading
                if os.path.exists(filepath):
                    os.remove(filepath)

                if secret_message_encrypted:
                    try:
                        f = Fernet(get_fernet_key(password))
                        decrypted_message = f.decrypt(secret_message_encrypted.encode()).decode()
                        return render_template('result.html', mode='decode', message=decrypted_message)
                    except InvalidToken:
                        flash('Incorrect password or corrupted image!')
                        return redirect(request.url)
                else:
                    flash('No hidden message found in the image.')
                    return redirect(request.url)
            except IndexError:
                # stegano throws IndexError if no message is found
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash('No hidden message found in the image, or the image is not properly encoded.')
                return redirect(request.url)
            except Exception as e:
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash(f'Error reading image: {str(e)}')
                return redirect(request.url)
        else:
            flash('Allowed image types are png, jpg, jpeg')
            return redirect(request.url)

    return render_template('decode.html')

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
