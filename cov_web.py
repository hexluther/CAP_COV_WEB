# cov_web.py
# COV inspection tool for PAWG - finally got this working with MongoDB instead of CSV
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, redirect, url_for, make_response, Response
import os
import subprocess
from werkzeug.utils import secure_filename
# from filelock import FileLock  # not using this anymore since we switched to mongo
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import json
import threading
import time
import difflib

# google oauth stuff - had to figure this out the hard way
import requests

# Google Drive API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# load all the config stuff
load_dotenv()

app = Flask(__name__)

# grab all the config from .env file
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER')
THUMB_FOLDER = os.getenv('THUMB_FOLDER')
CAPWATCH_PATH = os.getenv('CAPWATCH_PATH', 'C:\\CAPWATCH\\Unload')
ALLOWED_EXTENSIONS = set(os.getenv('ALLOWED_VIDEO_EXTENSIONS', 'mp4,avi,mov,wmv,mpg,mpeg,m4v,flv,webm,mkv,3gp').split(','))

# Video storage configuration
VIDEO_STORAGE_MODE = os.getenv('VIDEO_STORAGE_MODE', 'local')  # "local", "gdrive", "both"
GDRIVE_FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH')

# app image for logo and favicon
APP_IMAGE = os.getenv('APP_IMAGE', 'static/images/pawg_patch.png')

# google oauth config - took forever to get this right
GOOGLE_OAUTH = os.getenv('GOOGLE_OAUTH', 'False').lower() == 'true'
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_WORKSPACE_DOMAIN = os.getenv('GOOGLE_WORKSPACE_DOMAIN')
PARENT_ORGID = os.getenv('PARENT_ORGID')
WING_ADMIN_DUTY_POSITIONS = [pos.strip().strip('"') for pos in os.getenv('WING_ADMIN_DUTY_POSITIONS', '"Transportation Officer","Director of Operations","Director of IT"').split(',')]

# oauth stuff
SCOPES = ['openid', 'email', 'profile']
REDIRECT_URI = os.getenv('REDIRECT_URI')

# Default admin authentication (when Google OAuth is disabled)
DEFAULT_SUPERADMIN_CAPID = os.getenv('DEFAULT_SUPERADMIN_CAPID')
DEFAULT_SUPERADMIN_PASSWORD = os.getenv('DEFAULT_SUPERADMIN_PASSWORD')

# Wing configuration
APPLICABLE_WING = os.getenv('APPLICABLE_WING', 'PAWG')

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'cov_inspections')

# FFmpeg configuration
FFMPEG_PATH = os.getenv('FFMPEG_PATH', r'C:\ffmpeg\bin\ffmpeg.exe')

# Validate required environment variables
required_env_vars = {
    'GOOGLE_WORKSPACE_DOMAIN': GOOGLE_WORKSPACE_DOMAIN,
    'PARENT_ORGID': PARENT_ORGID,
    'REDIRECT_URI': REDIRECT_URI,
    'DEFAULT_SUPERADMIN_CAPID': DEFAULT_SUPERADMIN_CAPID,
    'DEFAULT_SUPERADMIN_PASSWORD': DEFAULT_SUPERADMIN_PASSWORD
}

# Add Google Drive validation if using Google Drive storage
if VIDEO_STORAGE_MODE in ['gdrive', 'both']:
    required_env_vars.update({
        'GDRIVE_FOLDER_ID': GDRIVE_FOLDER_ID,
        'GOOGLE_CREDENTIALS_PATH': GOOGLE_CREDENTIALS_PATH
    })

missing_vars = [var for var, value in required_env_vars.items() if value is None]
if missing_vars:
    print(f"❌ Error: Missing required environment variables: {', '.join(missing_vars)}")
    print("Please set these variables in your .env file")
    exit(1)

# Initialize MongoDB connection with validation
try:
    client = MongoClient(MONGODB_URI)
    
    # Test MongoDB connection
    client.admin.command('ping')
    print(f"✓ MongoDB server connection successful")
    
    # Get database
    db = client[MONGODB_DATABASE]
    
    # Check if database exists and has collections
    collections = db.list_collection_names()
    print(f"✓ Connected to database: {MONGODB_DATABASE}")
    print(f"✓ Found {len(collections)} collections: {collections}")
    
    # Initialize hardcoded collections
    inspections_collection = db['inspections']
    users_collection = db['users']
    events_collection = db['events']
    activity_collection = db['activity_log']
    
    # Check if database is empty (no collections or no data)
    if not collections:
        print(f"   The application will create collections as needed")
    else:
        # Check if key collections have data
        inspection_count = inspections_collection.count_documents({})
        user_count = users_collection.count_documents({})
        
except Exception as e:
    
    # Fallback to None - will be handled in functions
    client = None
    db = None
    inspections_collection = None
    users_collection = None
    events_collection = None
    activity_collection = None

# Google Drive service initialization
def get_google_drive_service():
    """Initialize and return Google Drive service"""
    try:
        if not GOOGLE_CREDENTIALS_PATH or not os.path.exists(GOOGLE_CREDENTIALS_PATH):
            print("❌ Google credentials file not found or path not configured")
            return None
            
        # Define the scopes needed for Google Drive
        SCOPES = ['https://www.googleapis.com/auth/drive']
        
        # Load credentials from service account file
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
        )
        
        # Build the Drive service
        service = build('drive', 'v3', credentials=credentials)
        print("✓ Google Drive service initialized successfully")
        return service
        
    except Exception as e:
        print(f"❌ Error initializing Google Drive service: {str(e)}")
        return None

def create_or_find_folder(service, folder_name, parent_folder_id=None):
    """Create or find a folder in Google Drive"""
    try:
        # Search for existing folder
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and parents in '{parent_folder_id}'"
        
        results = service.files().list(
            q=query,
            fields='files(id, name)',
            supportsAllDrives=True
        ).execute()
        
        folders = results.get('files', [])
        if folders:
            return folders[0]['id']  # Return first match
        
        # Create new folder if not found
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_folder_id:
            folder_metadata['parents'] = [parent_folder_id]
        
        folder = service.files().create(
            body=folder_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        
        return folder.get('id')
        
    except Exception as e:
        print(f"Error creating/finding folder '{folder_name}': {e}")
        return None

def upload_to_google_drive(file_path, filename, folder_id=None, event_name=None, cov_number=None):
    """Upload a file to Google Drive"""
    try:
        service = get_google_drive_service()
        if not service:
            return None, "Google Drive service not available"
            
        # Use the configured folder ID or default to root
        base_folder_id = folder_id or GDRIVE_FOLDER_ID
        if not base_folder_id:
            return None, "No Google Drive folder ID configured"
        
        # Create nested folder structure: [Event Directory] -> [COV_Number_Directory]
        final_folder_id = base_folder_id
        
        if event_name and cov_number:
            # Create/find Event Directory
            event_folder_id = create_or_find_folder(service, event_name, base_folder_id)
            if event_folder_id:
                # Create/find COV Number Directory inside Event Directory
                cov_folder_name = f"COV_{cov_number}"
                final_folder_id = create_or_find_folder(service, cov_folder_name, event_folder_id)
                if not final_folder_id:
                    final_folder_id = event_folder_id  # Fallback to event folder
            else:
                final_folder_id = base_folder_id  # Fallback to base folder
            
        # Create file metadata
        file_metadata = {
            'name': filename,
            'parents': [final_folder_id]
        }
        
        # Create media upload object
        media = MediaFileUpload(file_path, resumable=True)
        
        # Upload the file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink',
            supportsAllDrives=True
        ).execute()
        
        print(f"✓ File uploaded to Google Drive: {filename}")
        return file, None
        
    except Exception as e:
        error_msg = f"Error uploading to Google Drive: {str(e)}"
        print(f"❌ {error_msg}")
        return None, error_msg

def serve_from_google_drive(filename):
    """Serve video directly from Google Drive"""
    try:
        service = get_google_drive_service()
        if not service:
            return "Google Drive service unavailable", 503
            
        # Find file in Google Drive
        results = service.files().list(
            q=f"name='{filename}' and parents in '{GDRIVE_FOLDER_ID}'",
            fields="files(id,name,webContentLink)"
        ).execute()
        
        files = results.get('files', [])
        if not files:
            return "Video not found in Google Drive", 404
            
        # Get download URL
        file_id = files[0]['id']
        request = service.files().get_media(fileId=file_id)
        
        # Stream the file
        response = make_response(request.execute())
        response.headers['Content-Type'] = 'video/mp4'
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
        
    except Exception as e:
        return f"Error serving from Google Drive: {str(e)}", 500

def get_video_location_info(inspection_id):
    """Get detailed video location information for an inspection"""
    try:
        inspection = inspections_collection.find_one({'_id': ObjectId(inspection_id)})
        if not inspection:
            return None
            
        info = {
            'original_video': {
                'filename': inspection.get('video_filename', ''),
                'location': inspection.get('video_location', 'none'),
                'gdrive_file_id': inspection.get('gdrive_file_id'),
                'gdrive_error': inspection.get('gdrive_error')
            },
            'converted_video': {
                'filename': inspection.get('converted_video_filename', ''),
                'location': inspection.get('converted_video_location', 'none'),
                'gdrive_file_id': inspection.get('gdrive_converted_file_id'),
                'gdrive_error': inspection.get('gdrive_converted_error')
            },
            'storage_mode': inspection.get('storage_mode', 'local')
        }
        return info
    except Exception as e:
        print(f"Error getting video location info: {e}")
        return None

# Google OAuth configuration
if GOOGLE_OAUTH:
    # OAuth 2.0 client configuration
    SCOPES = ['openid', 'email', 'profile']

def generate_video_thumbnail(video_filename):
    """make a thumbnail for the video - ffmpeg is pretty cool for this"""
    try:
        # make sure the thumbnails folder exists
        os.makedirs(THUMB_FOLDER, exist_ok=True)
        
        video_path = os.path.join(UPLOAD_FOLDER, video_filename)
        thumbnail_name = os.path.splitext(video_filename)[0] + '.jpg'
        thumbnail_path = os.path.join(THUMB_FOLDER, thumbnail_name)
        
        # dont bother if we already have one
        if os.path.exists(thumbnail_path):
            return True
        
        # make sure the video is actually there
        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            return False
        
        # Use ffmpeg to extract first frame
        ffmpeg_path = FFMPEG_PATH
        cmd = [
            ffmpeg_path,
            '-i', video_path,
            '-ss', '00:00:01',  # Start at 1 second (skip any black frames)
            '-vframes', '1',    # Extract only 1 frame
            '-q:v', '2',        # High quality
            '-y',               # Overwrite output file
            thumbnail_path
        ]
        
        
        # Run ffmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return True
        else:
            return False
            
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        return False
    except Exception as e:
        return False

def convert_video_to_mp4(input_filename, output_filename=None):
    """convert whatever video format to mp4 - mobile devices are picky"""
    try:
        input_path = os.path.join(UPLOAD_FOLDER, input_filename)
        
        # figure out what to call the output file
        if output_filename is None:
            base_name = os.path.splitext(input_filename)[0]
            output_filename = base_name + '.mp4'
        
        output_path = os.path.join(UPLOAD_FOLDER, output_filename)
        
        # skip if we already converted it
        if os.path.exists(output_path):
            print(f"Converted file already exists: {output_filename}")
            return output_filename
        
        # make sure the input file is actually there
        if not os.path.exists(input_path):
            print(f"Input file not found: {input_path}")
            return None
        
        # use ffmpeg to convert to mp4 - this took me forever to get right
        ffmpeg_path = FFMPEG_PATH
        cmd = [
            ffmpeg_path,
            '-i', input_path,
            '-c:v', 'copy',           # Copy video stream (since it's already H.264)
            '-c:a', 'aac',            # AAC audio codec
            '-movflags', '+faststart', # Enable progressive download
            '-y',                     # Overwrite output file
            output_path
        ]
        
        print(f"Converting {input_filename} to {output_filename}...")
        
        # Run ffmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 minute timeout
        
        if result.returncode == 0:
            return output_filename
        else:
            return None
            
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None
    except Exception as e:
        return None

def background_video_processing(video_filename, inspection_id):
    """Background thread to convert video and update database"""
    def process_video():
        try:
            print(f"🔄 Starting background processing for {video_filename}")
            
            # update status to processing
            inspections_collection.update_one(
                {'_id': ObjectId(inspection_id)},
                {'$set': {'video_status': 'processing'}}
            )
            
            
            # Convert video to MP4
            converted_filename = convert_video_to_mp4(video_filename)
            
            if converted_filename:
                # Upload converted video to Google Drive if needed
                gdrive_converted_id = None
                gdrive_converted_error = None
                converted_video_location = 'local'  # Default to local since conversion creates local file
                
                if VIDEO_STORAGE_MODE in ['gdrive', 'both']:
                    converted_path = os.path.join(UPLOAD_FOLDER, converted_filename)
                    gdrive_file, gdrive_error = upload_to_google_drive(converted_path, converted_filename, event_name=data.get('event_name'), cov_number=data.get('van_number'))
                    if gdrive_file:
                        gdrive_converted_id = gdrive_file.get('id')
                        converted_video_location = 'both'  # Now in both local and Google Drive
                        print(f"✓ Converted video uploaded to Google Drive with ID: {gdrive_converted_id}")
                    else:
                        gdrive_converted_error = gdrive_error
                        print(f"❌ Failed to upload converted video to Google Drive: {gdrive_error}")
                
                # Update database with converted filename and ready status
                update_data = {
                    'converted_video_filename': converted_filename,
                    'converted_video_location': converted_video_location,
                    'video_status': 'ready'
                }
                
                # Add Google Drive info if applicable
                if gdrive_converted_id:
                    update_data['gdrive_converted_file_id'] = gdrive_converted_id
                if gdrive_converted_error:
                    update_data['gdrive_converted_error'] = gdrive_converted_error
                
                inspections_collection.update_one(
                    {'_id': ObjectId(inspection_id)},
                    {'$set': update_data}
                )
            else:
                # Mark as failed
                inspections_collection.update_one(
                    {'_id': ObjectId(inspection_id)},
                    {'$set': {'video_status': 'failed'}}
                )
                
        except Exception as e:
            # Mark as failed
            try:
                inspections_collection.update_one(
                    {'_id': ObjectId(inspection_id)},
                    {'$set': {'video_status': 'failed'}}
                )
            except:
                pass
    
    # Start background thread
    thread = threading.Thread(target=process_video)
    thread.daemon = True
    thread.start()
    return thread

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMB_FOLDER, exist_ok=True)

# Field definitions
CHECKLIST_FIELDS = [
    'body','branding','tire_press','inspection','registration',
    'inspection_card','van_book','form_132','shell_card',
    'oil_level','antifreeze_level','power_steering','battery',
    'horn','backup_lights','backup_camera','backup_alarm',
    'head_lights','brake_lights','turn_signals','windshield',
    'hazard_lights'
]
ARRIVAL_FIELDS = [
    'arrival_fuel_level',
    'arrival_oil_level',
    'arrival_wiper_fluid_level',
    'arrival_power_steering_level'
]

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload():
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    video_file = request.files.get('inspection_video')
    video_filename = ''
    gdrive_file_id = None
    gdrive_error = None
    video_location = 'none'
    
    if video_file and allowed_file(video_file.filename):
        van = request.form.get('van_number','UNKNOWN')
        inspector_id = request.form.get('inspector_id','UNKNOWN')
        date = request.form.get('date','UNKNOWN').replace('/', '-')  # Convert MM/DD/YYYY to MM-DD-YYYY
        ext = video_file.filename.rsplit('.',1)[1].lower()
        video_filename = f"{van}_{date}_{inspector_id}.{ext}"
        
        # Handle different storage modes and track actual location
        local_success = False
        gdrive_success = False
        
        if VIDEO_STORAGE_MODE in ['local', 'both']:
            # Save to local storage
            video_path = os.path.join(UPLOAD_FOLDER, video_filename)
            try:
                video_file.save(video_path)
                local_success = True
                print(f"✓ Video saved locally: {video_filename}")
                
                # Generate thumbnail automatically after saving video
                thumbnail_success = generate_video_thumbnail(video_filename)
            except Exception as e:
                print(f"❌ Failed to save video locally: {e}")
        
        if VIDEO_STORAGE_MODE in ['gdrive', 'both']:
            # Upload to Google Drive
            if VIDEO_STORAGE_MODE == 'gdrive':
                # For gdrive-only mode, save to temp location first
                temp_path = os.path.join(UPLOAD_FOLDER, video_filename)
                try:
                    video_file.save(temp_path)
                    upload_path = temp_path
                except Exception as e:
                    print(f"❌ Failed to save temp file for Google Drive: {e}")
                    upload_path = None
            else:
                # For both mode, use the already saved file
                upload_path = os.path.join(UPLOAD_FOLDER, video_filename)
            
            if upload_path and os.path.exists(upload_path):
                # Upload to Google Drive
                gdrive_file, gdrive_error = upload_to_google_drive(upload_path, video_filename, event_name=data.get('event_name'), cov_number=data.get('van_number'))
                if gdrive_file:
                    gdrive_file_id = gdrive_file.get('id')
                    gdrive_success = True
                    print(f"✓ Video uploaded to Google Drive with ID: {gdrive_file_id}")
                else:
                    print(f"❌ Failed to upload to Google Drive: {gdrive_error}")
                
                # Clean up temp file if gdrive-only mode
                if VIDEO_STORAGE_MODE == 'gdrive' and os.path.exists(upload_path):
                    try:
                        os.remove(upload_path)
                        print(f"✓ Cleaned up temporary file: {upload_path}")
                    except Exception as e:
                        print(f"⚠️ Could not clean up temp file: {e}")
        
        # Determine final video location based on what actually succeeded
        if local_success and gdrive_success:
            video_location = 'both'
        elif local_success:
            video_location = 'local'
        elif gdrive_success:
            video_location = 'gdrive'
        else:
            video_location = 'none'
            print(f"❌ Video upload completely failed for: {video_filename}")

    # Collect all form data
    data = {
        'date': request.form.get('date',''),
        'inspector_id': request.form.get('inspector_id',''),
        'van_number': request.form.get('van_number',''),
        'odometer_in': request.form.get('odometer_in',''),
        'license_plate': request.form.get('license_plate',''),
        'inspection_sticker': request.form.get('inspection_sticker',''),
        'comments': request.form.get('comments',''),
        'engine_oil': request.form.get('engine_oil',''),
        'transmission_fluid': request.form.get('transmission_fluid',''),
        'wiper_fluid': request.form.get('wiper_fluid',''),
        'event_name': request.form.get('event_name',''),
        'vin_display_hidden': request.form.get('vin_display_hidden',''),
        'vin_confirmed': request.form.get('vin_confirmed'),
        'video_filename': video_filename,
        'video_status': 'uploaded' if video_filename else 'none',
        'video_location': video_location,
        'gdrive_file_id': gdrive_file_id,
        'gdrive_error': gdrive_error,
        'storage_mode': VIDEO_STORAGE_MODE,
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }
    
    # Checklist radios
    for f in CHECKLIST_FIELDS:
        data[f] = request.form.get(f, 'No')
    
    # Arrival sliders - convert to percentages
    for f in ARRIVAL_FIELDS:
        value = request.form.get(f, '')
        if value and value.isdigit():
            # Convert to percentage based on field type
            if f == 'arrival_fuel_level':
                # Fuel: 8 increments (0-8)
                percentage = round((int(value) / 8) * 100, 1)
            else:
                # Other fluids: 4 increments (0-4)
                percentage = round((int(value) / 4) * 100, 1)
            data[f] = f"{percentage}%"
        else:
            data[f] = ''

    # tire date codes - had to add these for the new requirements
    tire_fields = ['tire_fl', 'tire_fr', 'tire_rl', 'tire_rr', 'tire_spare']
    for f in tire_fields:
        data[f] = request.form.get(f, '')

    try:
        # Insert into MongoDB
        result = inspections_collection.insert_one(data)
        inspection_id = str(result.inserted_id)
        
        # Start background video processing if video was uploaded
        if video_filename:
            print(f"Starting background processing for {video_filename}")  
            background_video_processing(video_filename, inspection_id)     
        resp = {
            'status': 'success',
            'van_number': data['van_number'],
            'license_plate': data['license_plate'],
            'odometer': data['odometer_in'],
            **{f: data[f] for f in ARRIVAL_FIELDS},
            'video_filename': data['video_filename'],
            'video_status': data['video_status'],
            'video_location': data['video_location'],
            'gdrive_file_id': data['gdrive_file_id'],
            'gdrive_error': data['gdrive_error'],
            'storage_mode': data['storage_mode'],
            'inspection_id': inspection_id
        }
        return jsonify(resp)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def find_member_info(capid):
    try:
        with open(os.path.join(CAPWATCH_PATH, 'Member.txt'), encoding='utf-8') as f:
            f.readline()
            for ln in f:
                parts = [v.strip('"') for v in ln.split(',')]
                if parts[0] == capid:
                    return {'rank': parts[14], 'first_name': parts[3], 'last_name': parts[2]}
    except FileNotFoundError:
        pass
    return None

def find_capid_by_email(email):
    """Find CAPID by email address in MbrContact.txt"""
    try:
        with open(os.path.join(CAPWATCH_PATH, 'MbrContact.txt'), encoding='utf-8') as f:
            f.readline()  # Skip header
            for line in f:
                parts = [v.strip('"') for v in line.split(',')]
                if len(parts) >= 4:
                    capid, contact_type, priority, contact = parts[0], parts[1], parts[2], parts[3]
                    if contact_type == 'EMAIL' and contact.lower() == email.lower():
                        return capid
    except FileNotFoundError:
        pass
    return None

def get_member_orgid(capid):
    """Get ORGID for a member from Member.txt"""
    try:
        with open(os.path.join(CAPWATCH_PATH, 'Member.txt'), encoding='utf-8') as f:
            f.readline()  # Skip header
            for line in f:
                parts = [v.strip('"') for v in line.split(',')]
                if len(parts) >= 12 and parts[0] == capid:
                    return parts[11]  # ORGID column
    except FileNotFoundError:
        pass
    return None

def get_authorized_orgids():
    """Get list of authorized ORGIDs (parent, children, grandchildren)"""
    authorized_orgids = {str(PARENT_ORGID)}
    
    try:
        with open(os.path.join(CAPWATCH_PATH, 'Organization.txt'), encoding='utf-8') as f:
            f.readline()  # Skip header
            for line in f:
                parts = [v.strip('"') for v in line.split(',')]
                if len(parts) >= 6:
                    orgid, next_level = str(parts[0]), str(parts[4])
                    if next_level == str(PARENT_ORGID):
                        authorized_orgids.add(orgid)  # Direct child
                        
        # Find grandchildren
        with open(os.path.join(CAPWATCH_PATH, 'Organization.txt'), encoding='utf-8') as f:
            f.readline()  # Skip header
            for line in f:
                parts = [v.strip('"') for v in line.split(',')]
                if len(parts) >= 6:
                    orgid, next_level = str(parts[0]), str(parts[4])
                    if next_level in authorized_orgids:
                        authorized_orgids.add(orgid)  # Grandchild
                        
    except FileNotFoundError:
        pass
    
    return authorized_orgids

def is_wing_admin(capid):
    """Check if member holds a wing admin duty position"""
    try:
        with open(os.path.join(CAPWATCH_PATH, 'DutyPosition.txt'), encoding='utf-8') as f:
            f.readline()  # Skip header
            for line in f:
                parts = [v.strip('"') for v in line.split(',')]
                if len(parts) >= 5:
                    member_capid, duty, level = parts[0], parts[1], parts[3]
                    if member_capid == capid and level == 'WING' and duty in WING_ADMIN_DUTY_POSITIONS:
                        return True
    except FileNotFoundError:
        pass
    return False

def validate_google_user(email):
    """Validate Google user against CAPWATCH data"""
    # Check domain
    if not email.endswith(f'@{GOOGLE_WORKSPACE_DOMAIN}'):
        return {'valid': False, 'error': 'Email not from authorized domain'}
    
    # Find CAPID
    capid = find_capid_by_email(email)
    if not capid:
        return {'valid': False, 'error': 'Email not found in CAPWATCH system'}
    
    # Check organization hierarchy
    member_orgid = get_member_orgid(capid)
    if not member_orgid:
        return {'valid': False, 'error': 'Member not found in CAPWATCH system'}
    
    authorized_orgids = get_authorized_orgids()
    if str(member_orgid) not in authorized_orgids:
        return {'valid': False, 'error': 'Member not authorized for this wing'}
    
    # Check if wing admin
    is_admin = is_wing_admin(capid)
    
    # Check if super admin (matches DEFAULT_SUPERADMIN_CAPID)
    is_super_admin = (capid == DEFAULT_SUPERADMIN_CAPID)
    
    # Get member info
    member_info = find_member_info(capid)
    if not member_info:
        return {'valid': False, 'error': 'Member information not found'}
    
    return {
        'valid': True,
        'capid': capid,
        'is_admin': is_admin,
        'is_super_admin': is_super_admin,
        'member_info': member_info
    }

def require_auth(f):
    """Decorator to require authentication"""
    def decorated_function(*args, **kwargs):
        if GOOGLE_OAUTH:
            if 'user_email' not in session:
                return redirect(url_for('google_login'))
        else:
            if 'capid' not in session:
                return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def require_admin(f):
    """Decorator to require admin access"""
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin', False):
            return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/google_login')
def google_login():
    """Initiate Google OAuth login"""
    if not GOOGLE_OAUTH:
        return redirect('/')
    
    from urllib.parse import urlencode
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "select_account consent",  # Force account selection and consent
        "hd": GOOGLE_WORKSPACE_DOMAIN,  # Restrict to workspace domain
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return redirect(auth_url)

@app.route('/auth/callback')
def google_callback():
    """Handle Google OAuth callback"""
    if not GOOGLE_OAUTH:
        return redirect('/')
    
    if error := request.args.get("error"):
        return render_template('index.html', 
                             app_image=APP_IMAGE,
                             applicable_wing=APPLICABLE_WING,
                             error=f'OAuth error: {error}')
    
    code = request.args.get("code")
    if not code:
        return render_template('index.html', 
                             app_image=APP_IMAGE,
                             applicable_wing=APPLICABLE_WING,
                             error='Missing authorization code.')
    
    # Use the redirect URI from environment configuration
    redirect_uri = REDIRECT_URI
    
    try:
        import requests
        from requests.auth import HTTPBasicAuth
        
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            auth=HTTPBasicAuth(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
            data={
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        
        # Get user info
        user_resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        user_resp.raise_for_status()
        user_info = user_resp.json()
        email = user_info.get('email')
        
        # Validate user
        validation = validate_google_user(email)
        if not validation['valid']:
            return render_template('index.html', 
                                 app_image=APP_IMAGE,
                                 applicable_wing=APPLICABLE_WING,
                                 error=validation['error'])
        
        # Store session data
        session['user_email'] = email
        session['capid'] = validation['capid']
        session['is_admin'] = validation['is_admin']
        session['is_super_admin'] = validation['is_super_admin']
        session['member_info'] = validation['member_info']
        
        return redirect('/')
        
    except Exception as e:
        print(f"Error during OAuth callback: {e}")
        return render_template('index.html', 
                             app_image=APP_IMAGE,
                             applicable_wing=APPLICABLE_WING,
                             error=f'An unexpected error occurred: {e}')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect('/')

@app.route('/clear_session')
def clear_session():
    """Clear session completely"""
    session.clear()
    return redirect('/')

@app.route('/api/current_time')
def get_current_time():
    """Get current server time in NY timezone"""
    from datetime import datetime
    import pytz
    
    ny_tz = pytz.timezone('America/New_York')
    current_time = datetime.now(ny_tz)
    return jsonify({
        'time': current_time.strftime('%m/%d/%Y %I:%M:%S %p'),
        'timestamp': current_time.isoformat()
    })

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    """CAPID + DOB login for non-OAuth mode"""
    if GOOGLE_OAUTH:
        return redirect('/google_login')
    
    if request.method == 'POST':
        capid = request.form.get('capid', '').strip()
        dob = request.form.get('dob', '').strip()
        
        # Check for super admin override (for backwards compatibility)
        if capid == DEFAULT_SUPERADMIN_CAPID and dob == DEFAULT_SUPERADMIN_PASSWORD:
            session['capid'] = capid
            session['is_admin'] = True
            session['is_super_admin'] = True
            session['user_email'] = f'admin-{capid}@pawg.cap.gov'
            return redirect('/admin')
        
        # Verify CAPID + DOB against Members.txt
        if capid and dob:
            member_info = find_member_info(capid)
            if member_info and member_info.get('dob'):
                # Compare DOB (both should be in MM/DD/YYYY format)
                if member_info['dob'] == dob:
                    # Set session for verified member
                    session['capid'] = capid
                    session['user_email'] = f'{capid}@pawg.cap.gov'
                    session['member_info'] = member_info
                    
                    # Check if member is admin based on duty position
                    if member_info.get('duty_position') in WING_ADMIN_DUTY_POSITIONS:
                        session['is_admin'] = True
                        session['is_super_admin'] = (capid == DEFAULT_SUPERADMIN_CAPID)
                    
                    return redirect('/admin' if session.get('is_admin') else '/')
                else:
                    return render_template('admin_login.html', applicable_wing=APPLICABLE_WING, error='Invalid date of birth')
            else:
                return render_template('admin_login.html', applicable_wing=APPLICABLE_WING, error='CAPID not found or missing DOB information')
        else:
            return render_template('admin_login.html', applicable_wing=APPLICABLE_WING, error='Please enter both CAPID and date of birth')
    
    return render_template('admin_login.html', applicable_wing=APPLICABLE_WING)

@app.route('/check_capid', methods=['POST'])
def check_capid():
    capid = request.json.get('capid','').strip()
    info = find_member_info(capid)
    if info:
        return jsonify({**info, 'status':'found'})
    return jsonify({'status':'not_found'})

def is_valid_van_number(vn):
    try:
        with open(os.path.join(CAPWATCH_PATH, 'vehicles.txt'), encoding='utf-8') as f:
            f.readline()
            for line in f:
                parts = line.split(',')
                if len(parts) > 3 and parts[3].strip('"').strip() == vn:
                    # Return both validation status and VIN (vin_id is in column 9)
                    vin_id = parts[9].strip('"').strip() if len(parts) > 9 else ''
                    return True, vin_id
            return False, ''
    except FileNotFoundError:
        return False, ''

@app.route('/check_van', methods=['POST'])
def check_van():
    van_number = request.json.get('van_number','').strip()
    is_valid, vin_id = is_valid_van_number(van_number)
    return jsonify({
        'status': 'valid' if is_valid else 'invalid',
        'vin_id': vin_id if is_valid else ''
    })

@app.route('/inspected_vans', methods=['GET'])
def inspected_vans():
    if inspections_collection is None:
        return jsonify({'inspections': [], 'total': 0, 'page': 1, 'pages': 0, 'per_page': 10})
    
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        # Get sorting parameters
        sort_by = request.args.get('sort', 'created_at')  # Default: newest first
        sort_order = request.args.get('order', 'desc')    # Default: descending
        event_filter = request.args.get('event', '')      # Filter by event
        
        # Build sort criteria
        sort_direction = -1 if sort_order == 'desc' else 1
        
        # Handle multi-level sorting
        if sort_by == 'van_date':
            sort_criteria = [('van_number', 1), ('created_at', -1)]
        elif sort_by == 'van_inspector_date':
            sort_criteria = [('van_number', 1), ('inspector_id', 1), ('created_at', -1)]
        elif sort_by == 'date_van':
            sort_criteria = [('created_at', -1), ('van_number', 1)]
        elif sort_by == 'event_date':
            sort_criteria = [('event_name', 1), ('created_at', -1)]
        else:
            sort_criteria = [(sort_by, sort_direction)]
        
        # Build filter criteria
        filter_criteria = {}
        if event_filter:
            filter_criteria['event_name'] = event_filter
        
        # Get total count
        total = inspections_collection.count_documents(filter_criteria)
        
        # Calculate pagination
        skip = (page - 1) * per_page
        pages = (total + per_page - 1) // per_page  # Ceiling division
        
        res = []
        # Get paginated inspection data with sorting and filtering
        for doc in inspections_collection.find(filter_criteria).sort(sort_criteria).skip(skip).limit(per_page):
            inspection_data = {
                'id': str(doc.get('_id', '')),
                'date': doc.get('date', ''),
                'van_number': doc.get('van_number', ''),
                'inspector_id': doc.get('inspector_id', ''),
                'odometer_in': doc.get('odometer_in', ''),
                'license_plate': doc.get('license_plate', ''),
                'inspection_sticker': doc.get('inspection_sticker', ''),
                'comments': doc.get('comments', ''),
                'event_name': doc.get('event_name', ''),
                'video_filename': doc.get('video_filename', ''),
                'created_at': doc.get('created_at', ''),
                'updated_at': doc.get('updated_at', '')
            }
            
            # Add checklist fields
            for field in CHECKLIST_FIELDS:
                inspection_data[field] = doc.get(field, 'No')
            
            # Legacy support: if either form_73 or form_132 is "Yes", show "Yes" for form_132
            form_73_value = doc.get('form_73', 'No')
            form_132_value = doc.get('form_132', 'No')
            inspection_data['form_132'] = 'Yes' if form_73_value == 'Yes' or form_132_value == 'Yes' else 'No'
            
            # Add arrival fluid levels
            for field in ARRIVAL_FIELDS:
                inspection_data[field] = doc.get(field, '')
            
            # Add fluid additions
            inspection_data['engine_oil'] = doc.get('engine_oil', '')
            inspection_data['transmission_fluid'] = doc.get('transmission_fluid', '')
            inspection_data['wiper_fluid'] = doc.get('wiper_fluid', '')
            
            # Add tire date codes
            inspection_data['tire_fl'] = doc.get('tire_fl', '')
            inspection_data['tire_fr'] = doc.get('tire_fr', '')
            inspection_data['tire_rl'] = doc.get('tire_rl', '')
            inspection_data['tire_rr'] = doc.get('tire_rr', '')
            inspection_data['tire_spare'] = doc.get('tire_spare', '')
            
            res.append(inspection_data)
        
        return jsonify({
            'inspections': res,
            'total': total,
            'page': page,
            'pages': pages,
            'per_page': per_page
        })
    except Exception as e:
        print(f"Error fetching inspected vans: {e}")
        return jsonify([])

@app.route('/missing_videos', methods=['GET'])
def missing_videos():
    if inspections_collection is None:
        return jsonify([])
    
    try:
        res = []
        for doc in inspections_collection.find({'video_filename': {'$in': ['', None]}}, {'van_number': 1, 'inspector_id': 1, '_id': 0}):
            res.append({
                'van_number': doc.get('van_number', ''),
                'inspector_id': doc.get('inspector_id', '')
            })
        return jsonify(res)
    except Exception as e:
        return jsonify([])

@app.route('/attach_video', methods=['POST'])
def attach_video():
    if inspections_collection is None:
        return jsonify({'status':'error','message':'Database not available'}), 500
    
    van = request.form.get('van_number','')
    insp = request.form.get('inspector_id','')
    date = request.form.get('date','UNKNOWN').replace('/', '-')  # Convert MM/DD/YYYY to MM-DD-YYYY
    vf = request.files.get('inspection_video')
    
    if not (vf and allowed_file(vf.filename)):
        return jsonify({'status':'error','message':'Invalid video'}), 400
    
    ext = vf.filename.rsplit('.',1)[1].lower()
    fn = f"{van}_{date}_{insp}.{ext}"
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
    vf.save(video_path)
    
    # Generate thumbnail automatically after saving video
    thumbnail_success = generate_video_thumbnail(fn)

    try:
        # Update the first matching record without a video
        result = inspections_collection.update_one(
            {'van_number': van, 'inspector_id': insp, 'video_filename': {'$in': ['', None]}},
            {'$set': {
                'video_filename': fn, 
                'video_status': 'uploaded',
                'updated_at': datetime.now()
            }}
        )
        
        if result.modified_count > 0:
            # Get the updated document to get its ID for background processing
            updated_doc = inspections_collection.find_one(
                {'van_number': van, 'inspector_id': insp, 'video_filename': fn}
            )
            
            if updated_doc:
                inspection_id = str(updated_doc['_id'])
                print(f"Starting background processing for attached video: {fn}")
                background_video_processing(fn, inspection_id)
            
            return jsonify({'status':'success','video_filename': fn, 'video_status': 'uploaded'})
        else:
            return jsonify({'status':'error','message':'No matching inspection found'}), 404
    except Exception as e:
        return jsonify({'status':'error','message': str(e)}), 500

@app.route('/replace_video', methods=['POST'])
def replace_video():
    """Replace an existing video with audit trail"""
    if inspections_collection is None:
        return jsonify({'status':'error','message':'Database not available'}), 500
    
    inspection_id = request.form.get('inspection_id')
    new_video_file = request.files.get('inspection_video')
    replacing_inspector = request.form.get('inspector_id')
    
    if not inspection_id or not new_video_file or not replacing_inspector:
        return jsonify({'status':'error','message':'Missing required fields'}), 400
    
    if not allowed_file(new_video_file.filename):
        return jsonify({'status':'error','message':'Invalid video format'}), 400
    
    try:
        # Get the existing inspection record
        inspection = inspections_collection.find_one({'_id': ObjectId(inspection_id)})
        if not inspection:
            return jsonify({'status':'error','message':'Inspection not found'}), 404
        
        original_filename = inspection.get('video_filename', '')
        if not original_filename:
            return jsonify({'status':'error','message':'No existing video to replace'}), 400
        
        # Create the replacement filename (original + replacing inspector + REPLACED_BY_CAPID)
        base_name = os.path.splitext(original_filename)[0]
        ext = original_filename.rsplit('.',1)[1].lower()
        replaced_filename = f"{base_name}_{replacing_inspector}_REPLACED_BY_CAPID.{ext}"
        
        # Move original video to replaced filename
        original_path = os.path.join(UPLOAD_FOLDER, original_filename)
        replaced_path = os.path.join(UPLOAD_FOLDER, replaced_filename)
        
        if os.path.exists(original_path):
            os.rename(original_path, replaced_path)
            print(f"Moved original video to: {replaced_filename}")
            
            # Also move converted version if it exists
            converted_original = base_name + '.mp4'
            converted_replaced = f"{base_name}_{replacing_inspector}_REPLACED_BY_CAPID.mp4"
            converted_original_path = os.path.join(UPLOAD_FOLDER, converted_original)
            converted_replaced_path = os.path.join(UPLOAD_FOLDER, converted_replaced)
            
            if os.path.exists(converted_original_path):
                os.rename(converted_original_path, converted_replaced_path)
                print(f"Moved converted video to: {converted_replaced}")
        
        # Save new video with original filename
        new_video_file.save(original_path)
        
        # Generate thumbnail for new video
        thumbnail_success = generate_video_thumbnail(original_filename)
        
        # Update database
        inspections_collection.update_one(
            {'_id': ObjectId(inspection_id)},
            {'$set': {
                'video_filename': original_filename,  # Keep same filename
                'video_status': 'uploaded',
                'video_replaced_by': replacing_inspector,
                'video_replaced_at': datetime.now(),
                'replaced_video_filename': replaced_filename,
                'updated_at': datetime.now()
            }}
        )
        
        # Start background processing for new video
        background_video_processing(original_filename, inspection_id)
        
        return jsonify({
            'status': 'success',
            'message': 'Video replaced successfully',
            'original_filename': original_filename,
            'replaced_filename': replaced_filename,
            'video_status': 'uploaded'
        })
        
    except Exception as e:
        return jsonify({'status':'error','message': str(e)}), 500

@app.route('/events', methods=['GET'])
def get_events():
    """Get list of all events with lock status"""
    if events_collection is None:
        return jsonify([])
    
    try:
        events = []
        for event in events_collection.find({}).sort('name', 1):
            # Check if this event is locked by looking at any inspection with this event name
            is_locked = False
            locked_by = None
            locked_at = None
            
            if inspections_collection is not None:
                # Find any inspection for this event to check lock status
                inspection = inspections_collection.find_one({'event_name': event['name']})
                if inspection:
                    is_locked = inspection.get('event_locked', False)
                    locked_by = inspection.get('event_locked_by')
                    locked_at = inspection.get('event_locked_at')
            
            # Handle created_at serialization
            created_at = event.get('created_at')
            if created_at and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            elif created_at:
                created_at = str(created_at)
            
            events.append({
                'id': str(event['_id']),
                'name': event['name'],
                'created_at': created_at,
                'is_locked': is_locked,
                'locked_by': locked_by,
                'locked_at': locked_at.isoformat() if locked_at and hasattr(locked_at, 'isoformat') else str(locked_at) if locked_at else None
            })
        
        return jsonify(events)
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify([])

@app.route('/events', methods=['POST'])
def create_event():
    """Create a new event"""
    if events_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    event_name = request.json.get('name', '').strip()
    if not event_name:
        return jsonify({'status': 'error', 'message': 'Event name is required'}), 400
    
    try:
        # Canonicalize the event name (lowercase, trim, normalize spaces)
        canonical_name = ' '.join(event_name.lower().split())
        
        # Check if event already exists (exact match)
        existing = events_collection.find_one({'name': event_name})
        if existing:
            return jsonify({
                'status': 'success', 
                'event': {'id': str(existing['_id']), 'name': existing['name']},
                'message': 'Event already exists'
            })
        
        # Check if canonicalized version already exists
        existing_canonical = events_collection.find_one({'canonical_name': canonical_name})
        if existing_canonical:
            return jsonify({
                'status': 'error',
                'message': f'An event with a similar name already exists: "{existing_canonical["name"]}"'
            }), 409
        
        # Check for similar event names using fuzzy matching (for warning only)
        all_events = list(events_collection.find()) if events_collection is not None else []
        similar_events = []
        
        for event in all_events:
            existing_name = event.get('name', '')
            existing_canonical = event.get('canonical_name', '').lower()
            
            # Use difflib's SequenceMatcher for similarity ratio
            similarity = difflib.SequenceMatcher(None, canonical_name, existing_canonical).ratio()
            
            # If similarity is above 0.75 (75%), it's worth warning about
            if similarity > 0.75 and similarity < 1.0:
                similar_events.append({
                    'name': existing_name,
                    'similarity': similarity
                })
        
        # Check if user wants to force creation (bypass similar event checks)
        force_create = request.json.get('force_create', False)
        
        # If similar events found and not forcing creation, return them for user to choose
        if similar_events and not force_create:
            # Sort by similarity (highest first)
            similar_events.sort(key=lambda x: x['similarity'], reverse=True)
            return jsonify({
                'status': 'similar_events_found',
                'message': f'Found {len(similar_events)} similar event name(s). Please choose one or create new anyway.',
                'similar_events': similar_events,
                'requested_name': event_name
            })
        
        # Create new event
        event_data = {
            'name': event_name,
            'canonical_name': canonical_name,
            'created_at': datetime.now(),
            'created_by': request.json.get('inspector_id', 'Unknown')
        }
        
        result = events_collection.insert_one(event_data)
        
        return jsonify({
            'status': 'success',
            'event': {'id': str(result.inserted_id), 'name': event_name},
            'message': 'Event created successfully'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/')
def home():
    # Check if user is authenticated via Google OAuth
    if GOOGLE_OAUTH:
        user_email = session.get('user_email')
        
        if not user_email or not user_email.strip() or not user_email.endswith(f'@{GOOGLE_WORKSPACE_DOMAIN}'):
            # User is not authenticated, show login page
            return render_template('index.html', 
                                 app_image=APP_IMAGE,
                                 applicable_wing=APPLICABLE_WING,
                                 google_oauth=GOOGLE_OAUTH,
                                 show_login=True)
        else:
            # User is authenticated, show main application
            return render_template('index.html', 
                                 app_image=APP_IMAGE,
                                 applicable_wing=APPLICABLE_WING,
                                 google_oauth=GOOGLE_OAUTH,
                                 user_email=session.get('user_email'),
                                 capid=session.get('capid'),
                                 is_admin=session.get('is_admin', False),
                                 member_info=session.get('member_info'))
    else:
        # Non-OAuth mode - check if user is authenticated
        if 'capid' not in session:
            # User is not authenticated, show login page
            return render_template('index.html', 
                                 app_image=APP_IMAGE,
                                 applicable_wing=APPLICABLE_WING,
                                 google_oauth=GOOGLE_OAUTH,
                                 show_login=True)
        else:
            # User is authenticated, show main application
            return render_template('index.html', 
                                 app_image=APP_IMAGE,
                                 applicable_wing=APPLICABLE_WING,
                                 google_oauth=GOOGLE_OAUTH,
                                 user_email=session.get('user_email'),
                                 capid=session.get('capid'),
                                 is_admin=session.get('is_admin', False),
                                 member_info=session.get('member_info'))

@app.route('/admin')
@require_auth
@require_admin
def admin():
    return render_template('admin_dashboard.html')

@app.route('/admin/covs')
@require_auth
@require_admin
def admin_covs():
    return render_template('admin.html', applicable_wing=APPLICABLE_WING, app_image=APP_IMAGE)

@app.route('/admin/export/csv')
@require_auth
@require_admin
def export_csv():
    """Export all inspection data to CSV"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        import csv
        import io
        from datetime import datetime
        
        # Get all inspections
        inspections = list(inspections_collection.find().sort('date', -1))
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        headers = [
            'Inspection ID', 'Date', 'Time', 'COV Number', 'License Plate', 
            'Odometer', 'Event Name', 'Inspector ID', 'Inspector Name',
            'Inspection Sticker', 'Video Filename', 'Video Status',
            'Converted Video Filename', 'Video Replaced By', 'Video Replaced At',
            'Replaced Video Filename',
            # Arrival Fluids
            'Arrival Fuel Level', 'Arrival Oil Level', 'Arrival Wiper Fluid Level',
            # Checklist Items
            'Body Condition', 'Head Lights', 'Brake Lights', 'Turn Signals', 'Hazard Lights',
            'Windshield', 'Oil Level', 'Transmission Fluid', 'Windshield Wiper Fluid',
            'Tire Condition', 'Tire Pressure', 'Brake Condition', 'Steering',
            'Engine Condition', 'Exhaust System', 'Lights Working', 'Horn',
            'Mirrors', 'Seat Belts', 'Fire Extinguisher', 'First Aid Kit',
            'Emergency Equipment', 'Radio', 'GPS', 'Other Equipment',
            # Final Notes
            'Engine Oil Added', 'Transmission Fluid Added', 'Comments',
            'Created At', 'Updated At'
        ]
        writer.writerow(headers)
        
        # Write data rows
        for inspection in inspections:
            # Get inspector info - try to resolve from CAPID if name is missing
            inspector_name = inspection.get('inspector_name', '')
            inspector_id = inspection.get('inspector_id', '')
            
            if not inspector_name and inspector_id:
                # Try to look up member info from CAPID
                try:
                    member_info = find_member_info(inspector_id)
                    if member_info:
                        inspector_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({inspector_id})".strip()
                    else:
                        inspector_name = f"CAPID {inspector_id}"
                except:
                    inspector_name = f"CAPID {inspector_id}" if inspector_id else "Unknown Inspector"
            elif not inspector_name:
                inspector_name = "Unknown Inspector"
            
            row = [
                str(inspection.get('_id', '')),
                inspection.get('date', ''),
                inspection.get('time', ''),
                inspection.get('van_number', ''),
                inspection.get('license_plate', ''),
                inspection.get('odometer_in', ''),
                inspection.get('event_name', ''),
                inspection.get('inspector_id', ''),
                inspector_name,
                inspection.get('inspection_sticker', ''),
                inspection.get('video_filename', ''),
                inspection.get('video_status', ''),
                inspection.get('converted_video_filename', ''),
                inspection.get('video_replaced_by', ''),
                inspection.get('video_replaced_at', ''),
                inspection.get('replaced_video_filename', ''),
                # Arrival Fluids
                inspection.get('arrival_fuel_level', ''),
                inspection.get('arrival_oil_level', ''),
                inspection.get('arrival_wiper_fluid_level', ''),
                # Checklist Items
                inspection.get('body', ''),
                inspection.get('head_lights', ''),
                inspection.get('brake_lights', ''),
                inspection.get('turn_signals', ''),
                inspection.get('hazard_lights', ''),
                inspection.get('windshield', ''),
                inspection.get('oil_level', ''),
                inspection.get('transmission_fluid', ''),
                inspection.get('windshield_wiper_fluid', ''),
                inspection.get('tire_condition', ''),
                inspection.get('tire_pressure', ''),
                inspection.get('brake_condition', ''),
                inspection.get('steering', ''),
                inspection.get('engine_condition', ''),
                inspection.get('exhaust_system', ''),
                inspection.get('lights_working', ''),
                inspection.get('horn', ''),
                inspection.get('mirrors', ''),
                inspection.get('seat_belts', ''),
                inspection.get('fire_extinguisher', ''),
                inspection.get('first_aid_kit', ''),
                inspection.get('emergency_equipment', ''),
                inspection.get('radio', ''),
                inspection.get('gps', ''),
                inspection.get('other_equipment', ''),
                # Final Notes
                inspection.get('engine_oil', ''),
                inspection.get('transmission_fluid', ''),
                inspection.get('comments', ''),
                inspection.get('created_at', ''),
                inspection.get('updated_at', '')
            ]
            writer.writerow(row)
        
        # Get CSV content
        csv_content = output.getvalue()
        output.close()
        
        # Create response
        from flask import Response
        response = Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=all_inspections_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        return response
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/stats')
@require_auth
@require_admin
def admin_stats():
    """Get admin dashboard statistics"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Total inspections
        total_inspections = inspections_collection.count_documents({})
        
        # Total unique COVs
        total_covs = len(inspections_collection.distinct('van_number'))
        
        # Total unique events
        total_events = len(inspections_collection.distinct('event_name'))
        
        # Videos with actual issues (processing failed, missing, or corrupted)
        videos_with_issues = inspections_collection.count_documents({
            '$or': [
                {'video_status': 'failed'},  # Videos that failed to process
                {'video_status': 'error'},   # Videos with processing errors
                {'video_status': {'$exists': False}},  # Videos with no status (likely missing)
                {'video_filename': {'$exists': True, '$ne': ''}, 'converted_video_filename': {'$exists': False}, 'video_status': {'$ne': 'ready'}}  # Videos that should be converted but aren't ready
            ]
        })
        
        return jsonify({
            'total_inspections': total_inspections,
            'total_covs': total_covs,
            'total_events': total_events,
            'videos_with_issues': videos_with_issues
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/events')
@require_auth
@require_admin
def admin_events():
    """Get all events with lock status"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Get all events from the events collection (not from inspections)
        all_events = list(events_collection.find().sort('name', 1)) if events_collection is not None else []
        
        formatted_events = []
        for event_doc in all_events:
            event_name = event_doc.get('name', '')
            if event_name:
                # Get inspection count for this event
                inspection_count = inspections_collection.count_documents({'event_name': event_name}) if inspections_collection is not None else 0
                
                formatted_events.append({
                    'name': event_name,
                    'inspection_count': inspection_count,
                    'locked': event_doc.get('is_locked', False),
                    'locked_by': event_doc.get('locked_by', ''),
                    'locked_at': event_doc.get('locked_at', '')
                })
        
        return jsonify({
            'status': 'success',
            'events': formatted_events
        })
        
    except Exception as e:
        print(f"Error in admin_events: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/events/<event_name>/lock', methods=['POST'])
@require_auth
@require_admin
def lock_event(event_name):
    """Lock an event to prevent new inspections"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        from datetime import datetime
        
        # Update all inspections with this event name
        result = inspections_collection.update_many(
            {'event_name': event_name},
            {
                '$set': {
                    'event_locked': True,
                    'event_locked_by': session.get('capid', 'Unknown'),
                    'event_locked_at': datetime.now().isoformat()
                }
            }
        )
        
        if result.modified_count > 0:
            # Log the lock activity
            try:
                from datetime import datetime
                
                # Get full user info for the person doing the lock
                locked_by_capid = session.get('capid', 'Unknown')
                locked_by_name = 'Unknown'
                if locked_by_capid and locked_by_capid != 'Unknown':
                    try:
                        member_info = find_member_info(locked_by_capid)
                        if member_info:
                            locked_by_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({locked_by_capid})".strip()
                        else:
                            locked_by_name = f"CAPID {locked_by_capid}"
                    except:
                        locked_by_name = f"CAPID {locked_by_capid}"
                
                activity_log = {
                    'type': 'event_locked',
                    'event_name': event_name,
                    'locked_by': locked_by_capid,
                    'locked_by_name': locked_by_name,
                    'locked_at': datetime.now(),
                    'timestamp': datetime.now().isoformat()
                }
                if activity_collection is not None:
                    activity_collection.insert_one(activity_log)
            except Exception as e:
                print(f"Error logging lock activity: {e}")
            
            return jsonify({
                'status': 'success',
                'message': f'Event "{event_name}" locked successfully',
                'modified_count': result.modified_count
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'No inspections found for event "{event_name}"'
            }), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/events/<event_name>/unlock', methods=['POST'])
@require_auth
@require_admin
def unlock_event(event_name):
    """Unlock an event to allow new inspections"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Update all inspections with this event name
        result = inspections_collection.update_many(
            {'event_name': event_name},
            {
                '$unset': {
                    'event_locked': '',
                    'event_locked_by': '',
                    'event_locked_at': ''
                }
            }
        )
        
        if result.modified_count > 0:
            # Log the unlock activity
            try:
                from datetime import datetime
                # Get full user info for the person doing the unlock
                unlocked_by_capid = session.get('capid', 'Unknown')
                unlocked_by_name = 'Unknown'
                if unlocked_by_capid and unlocked_by_capid != 'Unknown':
                    try:
                        member_info = find_member_info(unlocked_by_capid)
                        if member_info:
                            unlocked_by_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({unlocked_by_capid})".strip()
                        else:
                            unlocked_by_name = f"CAPID {unlocked_by_capid}"
                    except:
                        unlocked_by_name = f"CAPID {unlocked_by_capid}"
                
                activity_log = {
                    'type': 'event_unlocked',
                    'event_name': event_name,
                    'unlocked_by': unlocked_by_capid,
                    'unlocked_by_name': unlocked_by_name,
                    'unlocked_at': datetime.now(),
                    'timestamp': datetime.now().isoformat()
                }
                if activity_collection is not None:
                    activity_collection.insert_one(activity_log)
            except Exception as e:
                print(f"Error logging unlock activity: {e}")
            
            return jsonify({
                'status': 'success',
                'message': f'Event "{event_name}" unlocked successfully',
                'modified_count': result.modified_count
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'No inspections found for event "{event_name}"'
            }), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/events/<event_name>/lock-status', methods=['GET'])
@require_auth
def get_event_lock_status(event_name):
    """Check if an event is locked"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Find any inspection for this event to check lock status
        inspection = inspections_collection.find_one({'event_name': event_name})
        
        if not inspection:
            return jsonify({
                'status': 'success',
                'event_name': event_name,
                'is_locked': False,
                'locked_by': None,
                'locked_at': None
            })
        
        is_locked = inspection.get('event_locked', False)
        locked_by = inspection.get('event_locked_by')
        locked_at = inspection.get('event_locked_at')
        
        # Handle locked_at field - it might be a string or datetime object
        locked_at_str = None
        if locked_at:
            if hasattr(locked_at, 'isoformat'):
                # It's a datetime object
                locked_at_str = locked_at.isoformat()
            else:
                # It's already a string
                locked_at_str = str(locked_at)
        
        return jsonify({
            'status': 'success',
            'event_name': event_name,
            'is_locked': is_locked,
            'locked_by': locked_by,
            'locked_at': locked_at_str
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/access-info')
@require_auth
@require_admin
def admin_access_info():
    """Get information about why the user has admin access"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'status': 'error', 'message': 'User not authenticated'}), 401
        
        # Get user's CAPID from session
        capid = session.get('capid')
        if not capid:
            return jsonify({'status': 'error', 'message': 'CAPID not found'}), 400
        
        # Find member info
        member_info = find_member_info(capid)
        if not member_info:
            return jsonify({'status': 'error', 'message': 'Member not found'}), 404
        
        # Get user's duty positions
        duty_positions = []
        duty_position_file = os.path.join(CAPWATCH_PATH, 'DutyPosition.txt')
        if os.path.exists(duty_position_file):
            try:
                with open(duty_position_file, 'r', encoding='utf-8') as f:
                    f.readline()  # Skip header
                    for line in f:
                        if line.strip():
                            parts = [v.strip('"') for v in line.split(',')]
                            if len(parts) >= 2 and parts[0] == capid:
                                duty_positions.append(parts[1])
            except Exception as e:
                print(f"Error reading duty positions: {e}")
        
        # Check which duty positions grant admin access
        admin_duty_positions = []
        for position in duty_positions:
            if position in WING_ADMIN_DUTY_POSITIONS:
                admin_duty_positions.append(position)
        
        # Check if user is super admin
        is_super_admin = capid == DEFAULT_SUPERADMIN_CAPID
        
        return jsonify({
            'status': 'success',
            'user_info': {
                'capid': capid,
                'name': f"{member_info.get('first_name', '')} {member_info.get('last_name', '')}".strip(),
                'rank': member_info.get('rank', ''),
                'email': user_email
            },
            'all_duty_positions': duty_positions,
            'admin_duty_positions': admin_duty_positions,
            'admin_duty_positions_list': WING_ADMIN_DUTY_POSITIONS,
            'is_super_admin': is_super_admin
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/export-activity')
@require_auth
@require_admin
def export_activity():
    """Export activity log as CSV - admin only"""
    try:
        if activity_collection is None:
            return jsonify({'status': 'error', 'message': 'Activity collection not available'}), 500
        
        # Get all activity log entries
        activities = list(activity_collection.find().sort('timestamp', -1))
        
        # Create CSV content
        csv_content = "Timestamp,Type,Description\n"
        for activity in activities:
            timestamp = activity.get('timestamp', '')
            activity_type = activity.get('type', '')
            
            # Create description based on type
            if activity_type == 'inspection_deleted':
                van_number = activity.get('van_number', 'Unknown')
                event_name = activity.get('event_name', 'Unknown')
                deleted_by = activity.get('deleted_by_name', activity.get('deleted_by', 'Unknown'))
                description = f"COV {van_number} inspection deleted from {event_name} by {deleted_by}"
            elif activity_type == 'event_locked':
                event_name = activity.get('event_name', 'Unknown')
                locked_by = activity.get('locked_by_name', activity.get('locked_by', 'Unknown'))
                description = f"Event '{event_name}' locked by {locked_by}"
            elif activity_type == 'event_unlocked':
                event_name = activity.get('event_name', 'Unknown')
                unlocked_by = activity.get('unlocked_by_name', activity.get('unlocked_by', 'Unknown'))
                description = f"Event '{event_name}' unlocked by {unlocked_by}"
            else:
                description = f"Unknown activity: {activity_type}"
            
            # Escape CSV values
            timestamp = timestamp.replace('"', '""')
            activity_type = activity_type.replace('"', '""')
            description = description.replace('"', '""')
            
            csv_content += f'"{timestamp}","{activity_type}","{description}"\n'
        
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=activity_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/system-info')
@require_auth
@require_admin
def system_info():
    """Get system information (CPU, memory, disk, etc.)"""
    try:
        import psutil
        import platform
        import time
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk usage (from uploads directory where images/videos are stored)
        import os
        uploads_path = os.path.join(os.path.dirname(__file__), 'uploads')
        if os.path.exists(uploads_path):
            disk = psutil.disk_usage(uploads_path)
        else:
            disk = psutil.disk_usage('/')  # Fallback to root
        disk_percent = (disk.used / disk.total) * 100
        disk_free = f"{disk.free / (1024**3):.1f} GB"
        
        # System uptime
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_hours = int(uptime_seconds // 3600)
        uptime_days = uptime_hours // 24
        uptime_hours = uptime_hours % 24
        uptime = f"{uptime_days}d {uptime_hours}h"
        
        # Python version
        python_version = platform.python_version()
        
        return jsonify({
            'status': 'success',
            'cpu_percent': round(cpu_percent, 1),
            'memory_percent': round(memory_percent, 1),
            'disk_percent': round(disk_percent, 1),
            'disk_free': disk_free,
            'uptime': uptime,
            'python_version': python_version
        })
        
    except ImportError:
        return jsonify({
            'status': 'error', 
            'message': 'psutil library not available. Install with: pip install psutil'
        }), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/events/<event_name>', methods=['DELETE'])
@require_auth
@require_admin
def delete_event(event_name):
    """Delete an event - super admin only, and only if no inspections exist"""
    if not session.get('is_super_admin', False):
        return jsonify({'status': 'error', 'message': 'Super admin access required'}), 403
    
    try:
        # Check if event exists
        event_doc = events_collection.find_one({'name': event_name}) if events_collection is not None else None
        if not event_doc:
            return jsonify({'status': 'error', 'message': f'Event "{event_name}" not found'}), 404
        
        # Check if event is locked
        if event_doc.get('is_locked', False):
            return jsonify({'status': 'error', 'message': f'Cannot delete locked event "{event_name}"'}), 400
        
        # Check if there are any inspections for this event
        inspection_count = inspections_collection.count_documents({'event_name': event_name}) if inspections_collection is not None else 0
        if inspection_count > 0:
            return jsonify({'status': 'error', 'message': f'Cannot delete event "{event_name}" - it has {inspection_count} inspection(s). Use merge instead.'}), 400
        
        # Delete the event
        result = events_collection.delete_one({'name': event_name})
        
        if result.deleted_count == 0:
            return jsonify({'status': 'error', 'message': 'Event not found'}), 404
        
        # Log the deletion activity
        try:
            from datetime import datetime
            
            deleted_by_capid = session.get('capid', 'Unknown')
            # Use member info from session (already available from login)
            member_info = session.get('member_info', {})
            if member_info:
                deleted_by_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({deleted_by_capid})".strip()
            else:
                deleted_by_name = f"CAPID {deleted_by_capid}"
            
            activity_log = {
                'type': 'event_deleted',
                'event_name': event_name,
                'deleted_by': deleted_by_capid,
                'deleted_by_name': deleted_by_name,
                'deleted_at': datetime.now(),
                'timestamp': datetime.now().isoformat()
            }
            if activity_collection is not None:
                activity_collection.insert_one(activity_log)
        except Exception as e:
            pass
        
        return jsonify({
            'status': 'success',
            'message': f'Event "{event_name}" deleted successfully'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/merge-events', methods=['POST'])
@require_auth
@require_admin
def merge_events():
    """Merge two events - admin only"""
    try:
        data = request.get_json()
        source_event = data.get('source_event')
        target_event = data.get('target_event')
        
        if not source_event or not target_event:
            return jsonify({'status': 'error', 'message': 'Source and target events are required'}), 400
        
        if source_event == target_event:
            return jsonify({'status': 'error', 'message': 'Cannot merge an event with itself'}), 400
        
        # Check if both events exist
        source_event_doc = events_collection.find_one({'name': source_event}) if events_collection is not None else None
        target_event_doc = events_collection.find_one({'name': target_event}) if events_collection is not None else None
        
        if not source_event_doc:
            return jsonify({'status': 'error', 'message': f'Source event "{source_event}" not found'}), 404
        
        if not target_event_doc:
            return jsonify({'status': 'error', 'message': f'Target event "{target_event}" not found'}), 404
        
        # Check if target event is locked
        if target_event_doc.get('is_locked', False):
            return jsonify({'status': 'error', 'message': f'Cannot merge into locked event "{target_event}"'}), 400
        
        # Get all inspections from source event
        source_inspections = list(inspections_collection.find({'event_name': source_event})) if inspections_collection is not None else []
        
        if not source_inspections:
            return jsonify({'status': 'error', 'message': f'No inspections found in source event "{source_event}"'}), 400
        
        # Update all inspections to use target event
        updated_count = 0
        for inspection in source_inspections:
            inspections_collection.update_one(
                {'_id': inspection['_id']},
                {'$set': {'event_name': target_event}}
            )
            updated_count += 1
        
        # Delete the source event
        events_collection.delete_one({'name': source_event})
        
        # Log the merge activity
        try:
            from datetime import datetime
            
            # Get full user info for the person doing the merge
            merged_by_capid = session.get('capid', 'Unknown')
            merged_by_name = 'Unknown'
            if merged_by_capid and merged_by_capid != 'Unknown':
                try:
                    member_info = find_member_info(merged_by_capid)
                    if member_info:
                        merged_by_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({merged_by_capid})".strip()
                    else:
                        merged_by_name = f"CAPID {merged_by_capid}"
                except:
                    merged_by_name = f"CAPID {merged_by_capid}"
            
            activity_log = {
                'type': 'events_merged',
                'source_event': source_event,
                'target_event': target_event,
                'inspections_moved': updated_count,
                'merged_by': merged_by_capid,
                'merged_by_name': merged_by_name,
                'merged_at': datetime.now(),
                'timestamp': datetime.now().isoformat()
            }
            if activity_collection is not None:
                activity_collection.insert_one(activity_log)
        except Exception as e:
            print(f"Error logging merge activity: {e}")
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully merged "{source_event}" into "{target_event}". {updated_count} inspections moved.'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/initialize-database', methods=['POST'])
@require_auth
@require_admin
def initialize_database():
    """Initialize database with required collections and indexes - super admin only"""
    if not session.get('is_super_admin', False):
        return jsonify({'status': 'error', 'message': 'Super admin access required'}), 403
    
    try:
        if db is None:
            return jsonify({'status': 'error', 'message': 'Database not available'}), 500
        
        # Create collections if they don't exist (MongoDB creates them automatically on first insert)
        # But we can create indexes for better performance
        
        # Create indexes for inspections collection
        inspections_collection.create_index([("van_number", 1)])
        inspections_collection.create_index([("event_name", 1)])
        inspections_collection.create_index([("created_at", -1)])
        inspections_collection.create_index([("inspector_id", 1)])
        
        # Create indexes for users collection
        users_collection.create_index([("capid", 1)], unique=True)
        users_collection.create_index([("email", 1)], unique=True)
        
        # Create indexes for events collection
        events_collection.create_index([("name", 1)], unique=True)
        events_collection.create_index([("is_locked", 1)])
        
        # Create indexes for activity collection
        activity_collection.create_index([("timestamp", -1)])
        activity_collection.create_index([("type", 1)])
        
        return jsonify({
            'status': 'success', 
            'message': f'Database "{MONGODB_DATABASE}" initialized successfully with indexes'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/recent-activity')
@require_auth
@require_admin
def admin_recent_activity():
    """Get recent activity including inspections, deletions, and event changes"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        activities = []
        
        # Get recent inspections (last 5)
        recent_inspections = list(inspections_collection.find().sort('created_at', -1).limit(5))
        for inspection in recent_inspections:
            # Format time
            created_at = inspection.get('created_at', '')
            if created_at:
                try:
                    from datetime import datetime
                    if isinstance(created_at, str):
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        dt = created_at
                    time_str = dt.strftime('%m/%d %H:%M')
                except Exception as e:
                    time_str = 'Unknown'
            else:
                time_str = 'Unknown'
            
            # Get inspector info
            inspector_name = inspection.get('inspector_name', '')
            inspector_id = inspection.get('inspector_id', '')
            
            if not inspector_name and inspector_id:
                try:
                    member_info = find_member_info(inspector_id)
                    if member_info:
                        inspector_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({inspector_id})".strip()
                    else:
                        inspector_name = f"CAPID {inspector_id}"
                except:
                    inspector_name = f"CAPID {inspector_id}" if inspector_id else "Unknown Inspector"
            elif not inspector_name:
                inspector_name = "Unknown Inspector"
            
            # Create activity text
            van_number = inspection.get('van_number', 'Unknown COV')
            event_name = inspection.get('event_name', 'Unknown Event')
            
            activity_text = f"COV {van_number} inspected at {event_name} by {inspector_name}"
            
            activities.append({
                'time': time_str,
                'text': activity_text,
                'type': 'inspection'
            })
        
        # Get recent activity log entries (deletions, event changes)
        if activity_collection is not None:
            recent_activities = list(activity_collection.find().sort('timestamp', -1).limit(5))
            for activity in recent_activities:
                try:
                    from datetime import datetime
                    if isinstance(activity.get('timestamp'), str):
                        dt = datetime.fromisoformat(activity['timestamp'].replace('Z', '+00:00'))
                    else:
                        dt = activity.get('deleted_at') or activity.get('timestamp')
                    time_str = dt.strftime('%m/%d %H:%M')
                except:
                    time_str = 'Unknown'
                
                activity_type = activity.get('type', '')
                if activity_type == 'inspection_deleted':
                    van_number = activity.get('van_number', 'Unknown COV')
                    event_name = activity.get('event_name', 'Unknown Event')
                    deleted_by_name = activity.get('deleted_by_name', 'Unknown')
                    if not deleted_by_name or deleted_by_name == 'Unknown':
                        # Fallback to CAPID if name not stored
                        deleted_by_capid = activity.get('deleted_by', 'Unknown')
                        deleted_by_name = f"CAPID {deleted_by_capid}" if deleted_by_capid != 'Unknown' else 'Unknown'
                    activity_text = f"🗑️ COV {van_number} inspection deleted from {event_name} by {deleted_by_name}"
                elif activity_type == 'event_locked':
                    event_name = activity.get('event_name', 'Unknown Event')
                    locked_by_name = activity.get('locked_by_name', 'Unknown')
                    if not locked_by_name or locked_by_name == 'Unknown':
                        # Fallback to CAPID if name not stored
                        locked_by_capid = activity.get('locked_by', 'Unknown')
                        locked_by_name = f"CAPID {locked_by_capid}" if locked_by_capid != 'Unknown' else 'Unknown'
                    activity_text = f"🔒 Event '{event_name}' locked by {locked_by_name}"
                elif activity_type == 'event_unlocked':
                    event_name = activity.get('event_name', 'Unknown Event')
                    unlocked_by_name = activity.get('unlocked_by_name', 'Unknown')
                    if not unlocked_by_name or unlocked_by_name == 'Unknown':
                        # Fallback to CAPID if name not stored
                        unlocked_by_capid = activity.get('unlocked_by', 'Unknown')
                        unlocked_by_name = f"CAPID {unlocked_by_capid}" if unlocked_by_capid != 'Unknown' else 'Unknown'
                    activity_text = f"🔓 Event '{event_name}' unlocked by {unlocked_by_name}"
                elif activity_type == 'events_merged':
                    source_event = activity.get('source_event', 'Unknown')
                    target_event = activity.get('target_event', 'Unknown')
                    inspections_moved = activity.get('inspections_moved', 0)
                    merged_by_name = activity.get('merged_by_name', 'Unknown')
                    if not merged_by_name or merged_by_name == 'Unknown':
                        merged_by_capid = activity.get('merged_by', 'Unknown')
                        merged_by_name = f"CAPID {merged_by_capid}" if merged_by_capid != 'Unknown' else 'Unknown'
                    activity_text = f"🔄 Event '{source_event}' merged into '{target_event}' ({inspections_moved} inspections) by {merged_by_name}"
                elif activity_type == 'event_deleted':
                    event_name = activity.get('event_name', 'Unknown Event')
                    deleted_by_name = activity.get('deleted_by_name', 'Unknown')
                    if not deleted_by_name or deleted_by_name == 'Unknown':
                        deleted_by_capid = activity.get('deleted_by', 'Unknown')
                        deleted_by_name = f"CAPID {deleted_by_capid}" if deleted_by_capid != 'Unknown' else 'Unknown'
                    activity_text = f"🗑️ Event '{event_name}' deleted by {deleted_by_name}"
                else:
                    continue
                
                activities.append({
                    'time': time_str,
                    'text': activity_text,
                    'type': activity_type
                })
        else:
            pass  # No activity collection available
        
        # Sort all activities by time (most recent first) and limit to 10
        activities.sort(key=lambda x: x['time'], reverse=True)
        activities = activities[:10]
        
        return jsonify({'status': 'success', 'activities': activities})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/cov/<cov_number>')
@require_auth
@require_admin
def cov_details(cov_number):
    capid = session.get('capid', '')
    
    # Fix session: if CAPID matches super admin but is_super_admin is not set, fix it
    if capid == DEFAULT_SUPERADMIN_CAPID and not session.get('is_super_admin', False):
        session['is_super_admin'] = True
    
    is_super_admin = session.get('is_super_admin', False)
    
    return render_template('cov_details.html', cov_number=cov_number, is_super_admin=is_super_admin, app_image=APP_IMAGE)

@app.route('/api/admin/inspections/<inspection_id>', methods=['DELETE'])
@require_auth
@require_admin
def delete_inspection(inspection_id):
    """Delete an inspection - super admin only"""
    if not session.get('is_super_admin', False):
        return jsonify({'status': 'error', 'message': 'Super admin access required'}), 403
    
    try:
        if inspections_collection is None:
            return jsonify({'status': 'error', 'message': 'Database not available'}), 500
        
        # First, get the inspection to check if its event is locked
        inspection = inspections_collection.find_one({'_id': ObjectId(inspection_id)})
        if not inspection:
            return jsonify({'status': 'error', 'message': 'Inspection not found'}), 404
        
        # Check if the event is locked
        event_name = inspection.get('event_name')
        if event_name and event_name != 'No Event':
            # Check if event is locked
            event = events_collection.find_one({'name': event_name}) if events_collection is not None else None
            if event and event.get('is_locked', False):
                return jsonify({'status': 'error', 'message': f'Cannot delete inspection from locked event: "{event_name}"'}), 403
            
        # Event is not locked or has no event, proceed with deletion
        result = inspections_collection.delete_one({'_id': ObjectId(inspection_id)})
        
        if result.deleted_count > 0:
            # Log the deletion activity
            try:
                from datetime import datetime
                
                # Get full user info for the person doing the deletion
                deleted_by_capid = session.get('capid', 'Unknown')
                deleted_by_name = 'Unknown'
                if deleted_by_capid and deleted_by_capid != 'Unknown':
                    try:
                        member_info = find_member_info(deleted_by_capid)
                        if member_info:
                            deleted_by_name = f"{member_info.get('rank', '')} {member_info.get('first_name', '')} {member_info.get('last_name', '')} ({deleted_by_capid})".strip()
                        else:
                            deleted_by_name = f"CAPID {deleted_by_capid}"
                    except:
                        deleted_by_name = f"CAPID {deleted_by_capid}"
                
                activity_log = {
                    'type': 'inspection_deleted',
                    'inspection_id': str(inspection_id),
                    'van_number': inspection.get('van_number', 'Unknown'),
                    'event_name': inspection.get('event_name', 'Unknown Event'),
                    'inspector_id': inspection.get('inspector_id', 'Unknown'),
                    'deleted_by': deleted_by_capid,
                    'deleted_by_name': deleted_by_name,
                    'deleted_at': datetime.now(),
                    'timestamp': datetime.now().isoformat()
                }
                if activity_collection is not None:
                    activity_collection.insert_one(activity_log)
            except Exception as e:
                print(f"Error logging deletion activity: {e}")
            
            return jsonify({'status': 'success', 'message': 'Inspection deleted successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Inspection not found'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/covs', methods=['GET'])
def get_covs():
    """Get list of all COVs with inspection counts and events"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Get sorting parameters
        sort_by = request.args.get('sort', 'cov_number')
        sort_order = request.args.get('order', 'asc')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 12))
        
        # Build sort criteria
        sort_direction = 1 if sort_order == 'asc' else -1
        sort_criteria = {sort_by: sort_direction}
        
        # Aggregate to get COV statistics
        pipeline = [
            {
                '$group': {
                    '_id': '$van_number',
                    'total_inspections': {'$sum': 1},
                    'events': {'$addToSet': '$event_name'},
                    'last_inspection': {'$max': '$created_at'},
                    'first_inspection': {'$min': '$created_at'},
                    'inspectors': {'$addToSet': '$inspector_id'}
                }
            },
            {
                '$project': {
                    'cov_number': '$_id',
                    'total_inspections': 1,
                    'event_count': {'$size': '$events'},
                    'events': 1,
                    'last_inspection': 1,
                    'first_inspection': 1,
                    'inspector_count': {'$size': '$inspectors'},
                    'inspectors': 1
                }
            },
            {'$sort': sort_criteria}
        ]
        
        # Execute aggregation
        covs = list(inspections_collection.aggregate(pipeline))
        
        # Pagination
        total = len(covs)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_covs = covs[start:end]
        
        return jsonify({
            'status': 'success',
            'covs': paginated_covs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/cov/<cov_number>/inspections', methods=['GET'])
def get_cov_inspections(cov_number):
    """Get all inspections for a specific COV"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Get sorting parameters
        sort_by = request.args.get('sort', 'created_at')
        sort_order = request.args.get('order', 'desc')
        group_by_event = request.args.get('group_by_event', 'false').lower() == 'true'
        
        # Build sort criteria
        sort_direction = 1 if sort_order == 'asc' else -1
        sort_criteria = {sort_by: sort_direction}
        
        # Find inspections for this COV
        inspections = list(inspections_collection.find(
            {'van_number': cov_number}
        ).sort(sort_criteria))
        
        # Convert ObjectId to string for JSON serialization and add legacy support
        for inspection in inspections:
            inspection['_id'] = str(inspection['_id'])
            if 'created_at' in inspection:
                inspection['created_at'] = inspection['created_at'].isoformat()
            if 'updated_at' in inspection:
                inspection['updated_at'] = inspection['updated_at'].isoformat()
            
            # Legacy support: if either form_73 or form_132 is "Yes", show "Yes" for form_132
            form_73_value = inspection.get('form_73', 'No')
            form_132_value = inspection.get('form_132', 'No')
            inspection['form_132'] = 'Yes' if form_73_value == 'Yes' or form_132_value == 'Yes' else 'No'
            
            # Ensure tire code fields are present
            if 'tire_fl' not in inspection:
                inspection['tire_fl'] = ''
            if 'tire_fr' not in inspection:
                inspection['tire_fr'] = ''
            if 'tire_rl' not in inspection:
                inspection['tire_rl'] = ''
            if 'tire_rr' not in inspection:
                inspection['tire_rr'] = ''
            if 'tire_spare' not in inspection:
                inspection['tire_spare'] = ''
        
        # Group by event if requested
        if group_by_event:
            grouped = {}
            for inspection in inspections:
                event = inspection.get('event_name', 'No Event')
                if event not in grouped:
                    grouped[event] = []
                grouped[event].append(inspection)
            
            return jsonify({
                'status': 'success',
                'cov_number': cov_number,
                'inspections_by_event': grouped,
                'total_inspections': len(inspections)
            })
        else:
            return jsonify({
                'status': 'success',
                'cov_number': cov_number,
                'inspections': inspections,
                'total_inspections': len(inspections)
            })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/inspection/<inspection_id>', methods=['GET'])
def get_inspection_details(inspection_id):
    """Get detailed information for a specific inspection"""
    if inspections_collection is None:
        return jsonify({'status': 'error', 'message': 'Database not available'}), 500
    
    try:
        # Find the specific inspection
        inspection = inspections_collection.find_one({'_id': ObjectId(inspection_id)})
        
        if not inspection:
            return jsonify({'status': 'error', 'message': 'Inspection not found'}), 404
        
        # Convert ObjectId to string for JSON serialization
        inspection['_id'] = str(inspection['_id'])
        if 'created_at' in inspection:
            inspection['created_at'] = inspection['created_at'].isoformat()
        if 'updated_at' in inspection:
            inspection['updated_at'] = inspection['updated_at'].isoformat()
        
        # Legacy support: if either form_73 or form_132 is "Yes", show "Yes" for form_132
        form_73_value = inspection.get('form_73', 'No')
        form_132_value = inspection.get('form_132', 'No')
        inspection['form_132'] = 'Yes' if form_73_value == 'Yes' or form_132_value == 'Yes' else 'No'
        
        # Ensure tire code fields are present
        if 'tire_fl' not in inspection:
            inspection['tire_fl'] = ''
        if 'tire_fr' not in inspection:
            inspection['tire_fr'] = ''
        if 'tire_rl' not in inspection:
            inspection['tire_rl'] = ''
        if 'tire_rr' not in inspection:
            inspection['tire_rr'] = ''
        if 'tire_spare' not in inspection:
            inspection['tire_spare'] = ''
        
        return jsonify({
            'status': 'success',
            'inspection': inspection
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/video/<filename>')
def serve_video(filename):
    """Serve video files based on actual storage location"""
    try:
        # Get inspection record to find video location
        inspection = inspections_collection.find_one({'video_filename': filename})
        if not inspection:
            # Fallback to old behavior for backward compatibility
            return serve_video_fallback(filename)
            
        video_location = inspection.get('video_location', 'local')  # Default to local for backward compatibility
        
        if video_location in ['local', 'both']:
            # Try local first (faster)
            base_name = os.path.splitext(filename)[0]
            mp4_filename = base_name + '.mp4'
            mp4_path = os.path.join(UPLOAD_FOLDER, mp4_filename)
            
            if os.path.exists(mp4_path):
                return send_from_directory(UPLOAD_FOLDER, mp4_filename)
            elif os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
                return send_from_directory(UPLOAD_FOLDER, filename)
        
        if video_location in ['gdrive', 'both']:
            # Serve from Google Drive
            return serve_from_google_drive(filename)
            
        # If we get here, video location is 'none' or file not found
        return f"Video not found: {filename}", 404
        
    except Exception as e:
        return f"Video not found: {filename}", 404

def serve_video_fallback(filename):
    """Fallback method for serving videos (backward compatibility)"""
    try:
        # Check if there's a converted MP4 version available
        base_name = os.path.splitext(filename)[0]
        mp4_filename = base_name + '.mp4'
        mp4_path = os.path.join(UPLOAD_FOLDER, mp4_filename)
        
        # If MP4 version exists, serve it instead
        if os.path.exists(mp4_path):
            return send_from_directory(UPLOAD_FOLDER, mp4_filename)
        else:
            # Serve original file
            return send_from_directory(UPLOAD_FOLDER, filename)
    except Exception as e:
        return f"Video not found: {filename}", 404

@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    """Serve thumbnail files"""
    try:
        # Try to serve actual thumbnail
        return send_from_directory(THUMB_FOLDER, filename)
    except Exception as e:
        # Return placeholder image if thumbnail doesn't exist
        return send_from_directory('static/images', 'video_placeholder.svg')

if __name__=='__main__':
    app.run(host=os.getenv('FLASK_HOST', '0.0.0.0'), 
            port=int(os.getenv('FLASK_PORT', 5000)), 
            debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true')
