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
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # Increased to 100 MB to support hiding files

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
ALLOWED_PDF_EXTENSIONS = {'pdf'}

MAGIC_DELIMITER = b"||STEGOVAULT_MAGIC||"

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def get_fernet_key(password):
    digest = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(digest)

def hide_file_eof(cover_filepath, secret_filepath, password):
    # encrypt the secret file
    with open(secret_filepath, 'rb') as f:
        secret_data = f.read()
    
    fernet = Fernet(get_fernet_key(password))
    encrypted_data = fernet.encrypt(secret_data)
    
    secret_filename = os.path.basename(secret_filepath)
    # Format: MAGIC_DELIMITER + filename_bytes + MAGIC_DELIMITER + encrypted_data
    payload = MAGIC_DELIMITER + secret_filename.encode() + MAGIC_DELIMITER + encrypted_data
    
    with open(cover_filepath, 'ab') as f:
        f.write(payload)

def reveal_file_eof(filepath, password):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    idx = data.find(MAGIC_DELIMITER)
    if idx == -1:
        return None, None
    
    parts = data[idx:].split(MAGIC_DELIMITER, 2)
    # parts: ['', 'filename_bytes', 'encrypted_data']
    if len(parts) < 3:
        return None, None
        
    filename = parts[1].decode(errors='ignore')
    encrypted_data = parts[2]
    
    try:
        fernet = Fernet(get_fernet_key(password))
        decrypted_data = fernet.decrypt(encrypted_data)
        return filename, decrypted_data
    except Exception:
        return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/encode', methods=['GET', 'POST'])
def encode():
    # Legacy encode (text in image via LSB)
    if request.method == 'POST':
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

        if file and allowed_file(file.filename, ALLOWED_EXTENSIONS):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            output_filename = f"encoded_{uuid.uuid4().hex}.png"
            output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            try:
                f = Fernet(get_fernet_key(password))
                encrypted_message = f.encrypt(message.encode()).decode()

                secret_img = lsb.hide(filepath, encrypted_message)
                secret_img.save(output_filepath)
                
                if os.path.exists(filepath):
                    os.remove(filepath)
                    
                return render_template('result.html', mode='encode', filename=output_filename, type='text')
            except Exception as e:
                flash(f'Error encoding image: {str(e)}')
                return redirect(request.url)
        else:
            flash('Allowed image types are png, jpg, jpeg')
            return redirect(request.url)

    return render_template('encode.html')

@app.route('/encode_image', methods=['GET', 'POST'])
def encode_image():
    if request.method == 'POST':
        cover = request.files.get('cover_image')
        secret = request.files.get('secret_image')
        password = request.form.get('password')

        if not cover or not secret or cover.filename == '' or secret.filename == '':
            flash('Both cover and secret images are required')
            return redirect(request.url)
        
        if not password:
            flash('Password cannot be empty')
            return redirect(request.url)

        if allowed_file(cover.filename, ALLOWED_EXTENSIONS) and allowed_file(secret.filename, ALLOWED_EXTENSIONS):
            cover_filename = secure_filename(cover.filename)
            secret_filename = secure_filename(secret.filename)
            
            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], f"tmp_cover_{uuid.uuid4().hex}_{cover_filename}")
            secret_path = os.path.join(app.config['UPLOAD_FOLDER'], f"tmp_sec_{uuid.uuid4().hex}_{secret_filename}")
            
            cover.save(cover_path)
            secret.save(secret_path)

            output_filename = f"encoded_{uuid.uuid4().hex}_{cover_filename}"
            output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            try:
                with open(cover_path, 'rb') as f1, open(output_filepath, 'wb') as f2:
                    f2.write(f1.read())

                hide_file_eof(output_filepath, secret_path, password)
                
                if os.path.exists(cover_path): os.remove(cover_path)
                if os.path.exists(secret_path): os.remove(secret_path)
                    
                return render_template('result.html', mode='encode', filename=output_filename, type='image')
            except Exception as e:
                flash(f'Error encoding image: {str(e)}')
                return redirect(request.url)
        else:
            flash('Allowed image types are png, jpg, jpeg')
            return redirect(request.url)

    return render_template('encode_image.html')
    
@app.route('/encode_pdf', methods=['GET', 'POST'])
def encode_pdf():
    if request.method == 'POST':
        cover = request.files.get('cover_pdf')
        secret_type = request.form.get('secret_type', 'file')
        password = request.form.get('password')

        if not cover or cover.filename == '':
            flash('Cover PDF is required')
            return redirect(request.url)
            
        secret_path = None
        
        if secret_type == 'file':
            secret = request.files.get('secret_file')
            if not secret or secret.filename == '':
                flash('Secret file is required')
                return redirect(request.url)
            secret_filename = secure_filename(secret.filename)
            secret_path = os.path.join(app.config['UPLOAD_FOLDER'], f"tmp_sec_{uuid.uuid4().hex}_{secret_filename}")
            secret.save(secret_path)
            
        elif secret_type == 'text':
            secret_text = request.form.get('secret_text')
            if not secret_text:
                flash('Secret text is required')
                return redirect(request.url)
            secret_filename = "secret_message.txt"
            secret_path = os.path.join(app.config['UPLOAD_FOLDER'], f"tmp_sec_{uuid.uuid4().hex}_{secret_filename}")
            with open(secret_path, 'w', encoding='utf-8') as f:
                f.write(secret_text)
        
        if not password:
            flash('Password cannot be empty')
            return redirect(request.url)

        if allowed_file(cover.filename, ALLOWED_PDF_EXTENSIONS):
            cover_filename = secure_filename(cover.filename)
            
            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], f"tmp_cover_{uuid.uuid4().hex}_{cover_filename}")
            
            cover.save(cover_path)

            output_filename = f"encoded_{uuid.uuid4().hex}_{cover_filename}"
            output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            try:
                with open(cover_path, 'rb') as f1, open(output_filepath, 'wb') as f2:
                    f2.write(f1.read())

                hide_file_eof(output_filepath, secret_path, password)
                
                if os.path.exists(cover_path): os.remove(cover_path)
                if os.path.exists(secret_path): os.remove(secret_path)
                    
                return render_template('result.html', mode='encode', filename=output_filename, type='pdf')
            except Exception as e:
                flash(f'Error encoding PDF: {str(e)}')
                return redirect(request.url)
        else:
            flash('Cover file must be a PDF')
            return redirect(request.url)

    return render_template('encode_pdf.html')

@app.route('/decode', methods=['GET', 'POST'])
def decode():
    if request.method == 'POST':
        # Now expects 'file' instead of 'image' due to universal design
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        password = request.form.get('password')

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if not password:
            flash('Password cannot be empty')
            return redirect(request.url)

        if file and (allowed_file(file.filename, ALLOWED_EXTENSIONS) or allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS)):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                # 1. First attempt to reveal EOF data
                secret_filename, secret_data = reveal_file_eof(filepath, password)
                if secret_filename and secret_data:
                    if secret_filename == "secret_message.txt":
                        decrypted_message = secret_data.decode('utf-8', errors='ignore')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return render_template('result.html', mode='decode', message=decrypted_message, filename=None)
                        
                    decoded_output_filename = f"decoded_{uuid.uuid4().hex}_{secret_filename}"
                    decoded_output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], decoded_output_filename)
                    with open(decoded_output_filepath, 'wb') as f:
                        f.write(secret_data)
                    
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        
                    return render_template('result.html', mode='decode', filename=decoded_output_filename, message=None)

                # 2. EOF Reveal failed. If image, try LSB text decode.
                if allowed_file(filename, ALLOWED_EXTENSIONS):
                    secret_message_encrypted = lsb.reveal(filepath)
                    if secret_message_encrypted:
                        try:
                            f = Fernet(get_fernet_key(password))
                            decrypted_message = f.decrypt(secret_message_encrypted.encode()).decode()
                            
                            if os.path.exists(filepath):
                                os.remove(filepath)
                                
                            return render_template('result.html', mode='decode', message=decrypted_message, filename=None)
                        except InvalidToken:
                            flash('Incorrect password or corrupted image!')
                            if os.path.exists(filepath): os.remove(filepath)
                            return redirect(request.url)
                    
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash('No hidden data found or incorrect password.')
                return redirect(request.url)

            except Exception as e:
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash(f'Error reading file or incorrect password.')
                return redirect(request.url)
        else:
            flash('Allowed file types are png, jpg, jpeg, and pdf')
            return redirect(request.url)

    return render_template('decode.html')

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
