# COV Inspection Tool

A web-based inspection tool for Corporate Owned Vehicles (COV) designed for Civil Air Patrol Wings. This tool replaces paper-based inspection systems with a modern, touch-friendly interface that works on tablets and mobile devices.

## Features

- **Touch-Friendly Interface**: Optimized for tablets and touch screens with large, easy-to-use buttons
- **Multi-Step Inspection Process**: 6-page guided inspection covering all vehicle aspects
- **Video Documentation**: Upload walk-around videos with automatic MP4 conversion
- **Flexible Video Storage**: Store videos locally, in Google Drive, or both with automatic fallback
- **Google OAuth Authentication**: Secure login with Google Workspace domain restriction
- **CAPWATCH Integration**: Validates inspector CAPIDs and vehicle numbers from CAPWATCH data
- **MongoDB Storage**: Reliable data storage with complete inspection history
- **Responsive Design**: Works seamlessly on mobile, tablet, and desktop devices
- **Administrative Dashboard**: Management interface with system monitoring and controls
- **Event Management**: Lock/unlock events, merge duplicates, and prevent naming conflicts
- **Data Export**: Export inspection data to CSV format
- **Theme Support**: Dark and light mode options with user preference memory
- **Video Thumbnails**: Automatic thumbnail generation for uploaded videos
- **Background Processing**: Non-blocking video processing for smooth user experience

## Installation & Setup

### System Requirements
- Python 3.8 or higher
- MongoDB 4.0 or higher
- FFmpeg (for video processing and thumbnail generation)
- CAPWATCH data files (Member.txt, DutyPosition.txt)
- Google Workspace domain (for OAuth authentication)
- Google Drive API credentials (optional, for cloud video storage)

### Platform-Specific Installation

#### Windows
1. **Install Python:**
   - Download Python from https://python.org/downloads/
   - During installation, check "Add Python to PATH"
   - Verify installation: `python --version`

2. **Install MongoDB:**
   - Download MongoDB Community Server from https://mongodb.com/try/download/community
   - Run the installer and follow the setup wizard
   - Start MongoDB service: `net start MongoDB` (or use Services.msc)

3. **Install FFmpeg:**
   - Download FFmpeg from https://ffmpeg.org/download.html
   - Extract to `C:\ffmpeg\`
   - Add `C:\ffmpeg\bin` to your system PATH
   - Verify installation: `ffmpeg -version`

4. **Clone and Setup:**
   ```cmd
   git clone https://github.com/your-username/CAP_COV_WEB.git
   cd CAP_COV_WEB
   pip install -r requirements.txt
   ```

#### Linux (Ubuntu/Debian)
1. **Install Python and pip:**
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip python3-venv
   ```

2. **Install MongoDB:**
   ```bash
   wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
   echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
   sudo apt update
   sudo apt install mongodb-org
   sudo systemctl start mongod
   sudo systemctl enable mongod
   ```

3. **Install FFmpeg:**
   ```bash
   sudo apt install ffmpeg
   ```

4. **Clone and Setup:**
   ```bash
   git clone https://github.com/your-username/CAP_COV_WEB.git
   cd CAP_COV_WEB
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

#### macOS
1. **Install Homebrew (if not already installed):**
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install Python and MongoDB:**
   ```bash
   brew install python mongodb-community
   brew services start mongodb-community
   ```

3. **Install FFmpeg:**
   ```bash
   brew install ffmpeg
   ```

4. **Clone and Setup:**
   ```bash
   git clone https://github.com/your-username/CAP_COV_WEB.git
   cd CAP_COV_WEB
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### Google Drive Setup (Optional)
For cloud video storage, you'll need to set up Google Drive API access:

1. **Create a Google Cloud Project** and enable the Google Drive API
2. **Create a Service Account** and download the JSON credentials file
3. **Create a Google Drive folder** for video storage and get the folder ID
4. **Place the credentials file** in your project directory (e.g., `credentials/service-account.json`)
5. **Configure environment variables**:
   - `VIDEO_STORAGE_MODE=gdrive` (or `both` for local + cloud)
   - `GDRIVE_FOLDER_ID=your_folder_id_here`
   - `GOOGLE_CREDENTIALS_PATH=credentials/service-account.json`

### Configuration
1. Copy `.env.example` to `.env` and configure your settings:
   - Configure MongoDB connection settings
   - Set CAPWATCH file locations
   - Configure Google Workspace domain for OAuth
   - Set your Wing's identifier (e.g., "PAWG", "CAWG", "NYWG")
   - Configure admin access settings
   - Set FFmpeg path for video processing
   - Configure video storage options (local, Google Drive, or both)
   - Set Google Drive API credentials (if using cloud storage)
2. Set up CAPWATCH data files in the specified directory
3. Ensure MongoDB is running on your system

### Running the Application
```bash
# Development mode
python cov_web.py

# Production mode (if using serve.py)
python serve.py
```

The application will be available at `http://localhost:5000` (or your configured port).

## Usage

### Authentication
The application supports two authentication methods:
1. **Google OAuth** (recommended): Secure login with Google Workspace domain restriction
2. **CAPID + Date of Birth**: Direct CAPID verification using CAPWATCH data for environments without Google OAuth

### Starting an Inspection
1. **Login**: Sign in with Google OAuth or enter your CAPID
2. **Event Selection**: Choose an existing event or create a new one
3. **Vehicle Information**: Fill in van number, license plate, odometer
4. **Arrival Fluids**: Record initial fluid levels using sliders
5. **Inspection Checklist**: Complete the 3-page inspection checklist
6. **Final Notes**: Add comments and upload inspection video
7. **Submit**: Complete the inspection

### Managing Videos
- View list of all inspected vans
- Attach videos to inspections that don't have them
- Videos are automatically named: `{VAN_NUMBER}_INSPECTION_VIDEO.{EXT}`
- Automatic MP4 conversion for mobile compatibility
- Thumbnail generation for quick video preview

### Admin Dashboard
Access the admin dashboard at `/admin` (requires admin privileges):

#### Admin Access
- **Admin Access Card**: Shows user info and admin privileges
- **System Health**: Database, video processing, and authentication status
- **Quick Stats**: Total inspections, COVs inspected, events, and video issues

#### Management Features
- **Inspection Management**: View and manage all COV inspections
- **Data Export**: Download comprehensive CSV files with all inspection data
- **Event Management**: Lock/unlock events and prevent duplicate event names

#### Admin Privileges
Admin access is granted based on duty positions in CAPWATCH:
- Wing-level positions (Commander, Vice Commander, etc.)
- Director-level positions (Director of IT, Director of Operations, etc.)
- Default superadmin CAPID (configurable in `.env`)

### Data Storage
- All inspections stored in MongoDB `cov_inspections` database
- Collection: `inspections`
- Includes timestamps, inspector info, vehicle details, and all checklist items

## File Structure

```
cov_web/
├── cov_web.py              # Main application
├── serve.py                # Production server
├── .env                    # Configuration file
├── requirements.txt        # Python dependencies
├── data/                   # Data storage
│   └── thumbnails/         # Video thumbnails
├── templates/              # HTML templates
│   ├── index.html          # Main application interface
│   ├── admin_dashboard.html # Admin dashboard
│   ├── admin.html          # Inspection management page
│   └── cov_details.html    # Individual COV details page
├── static/                 # Images and assets
│   ├── images/             # Application images and logos
│   └── css/                # Stylesheets (if any)
├── uploads/                # Video files
└── reports/                # Generated reports
```

## Inspection Process

### Page 1: Vehicle Information
- Date/Time (auto-filled)
- Inspector ID (from CAPID verification)
- Van Number (validated against CAPWATCH)
- License Plate
- Odometer Reading
- Inspection Sticker (MM/YY format)

### Page 2: Arrival Fluid Levels
- Fuel Level (0-8 scale)
- Oil Level (0-4 scale)
- Wiper Fluid Level (0-4 scale)
- Power Steering Fluid Level (0-4 scale)

### Pages 3-5: Inspection Checklist
- Body condition
- CAP branding
- Tire pressure stickers
- State inspection
- Registration
- Inspection card
- Van book
- Form 73
- Shell card
- Oil level
- Antifreeze level
- Power steering
- Battery
- Horn
- Backup lights
- Backup camera
- Backup alarm
- Head lights
- Brake lights
- Turn signals
- Windshield
- Hazard lights

### Page 6: Final Notes
- Engine oil added (quarts)
- Transmission fluid added (quarts)
- Wiper fluid added (gallons)
- Inspection video upload
- Comments

## Responsive Design

The application is fully responsive and optimized for all device types:

### Mobile Devices
- **Vertical card layouts**: Admin dashboard cards stack vertically
- **Touch-friendly buttons**: Large, easy-to-tap interface elements
- **Optimized headers**: Badge and title stack vertically to save space
- **Full-width controls**: Sorting dropdowns use full screen width
- **Proper spacing**: No element overflow or bunching

### Tablets
- **Flexible grid layouts**: Cards adapt to screen size
- **Touch-optimized**: Large buttons and touch targets
- **Landscape support**: Layouts work in both orientations

### Desktop
- **Multi-column layouts**: Efficient use of screen real estate
- **Hover effects**: Interactive elements with visual feedback
- **Keyboard navigation**: Full keyboard accessibility support

## CAPWATCH Integration

The tool integrates with CAPWATCH data files to provide validation and user information:
- `Member.txt`: Validates inspector CAPIDs and displays rank/name information
- `MbrContact.txt`: Email address validation for Google OAuth authentication
- `Organization.txt`: Organization structure validation
- `DutyPosition.txt`: Determines administrative privileges
- `vehicles.txt`: Validates vehicle numbers against CAPWATCH data

**Note**: If CAPWATCH files are not available, the tool will still function but without data validation capabilities.

## MongoDB Collections

The application uses four MongoDB collections for data storage:

### Inspections Collection
Stores all inspection data with the following key fields:
- `date`: Inspection date/time
- `inspector_id`: CAPID of inspector
- `van_number`: Vehicle identifier
- `license_plate`: License plate number
- `odometer_in`: Odometer reading
- `event_name`: Associated event name
- `video_filename`: Original uploaded video file
- `converted_video_filename`: MP4 converted video file
- `video_status`: Video processing status (ready, processing, failed)
- `created_at`: MongoDB timestamp
- `updated_at`: Last modified timestamp
- `event_locked`: Event lock status
- `event_locked_by`: User who locked the event
- `event_locked_at`: Event lock timestamp
- Plus all checklist and fluid level fields

### Events Collection
Stores event information:
- `name`: Event name
- `created_at`: Event creation timestamp

### Users Collection
Stores user authentication and profile data:
- `email`: User email address
- `capid`: CAP member ID
- `first_name`: Member first name
- `last_name`: Member last name
- `rank`: CAP rank
- `created_at`: User creation timestamp

### Activity Log Collection
Stores administrative activity for audit purposes:
- `type`: Activity type (inspection, deletion, event_locked, event_unlocked, events_merged, event_deleted)
- `user_capid`: CAPID of user performing action
- `user_name`: Full name and rank of user
- `description`: Human-readable description of action
- `timestamp`: When the action occurred
- `details`: Additional context (event names, inspection IDs, etc.)

## Troubleshooting

### MongoDB Connection Issues
- Ensure MongoDB is running on localhost:27017
- Check `.env` file for correct MongoDB URI
- Verify database permissions

### CAPWATCH File Issues
- Ensure files exist at configured paths
- Check file permissions
- Tool will work without these files (no validation)

### Video Upload Issues
- Check file type (mp4, avi, mov, wmv only)
- Verify upload folder permissions
- Ensure sufficient disk space

## Development

### Running in Development Mode
```bash
python cov_web.py
```

### Running in Production Mode
```bash
python serve.py
```

### Environment Variables
All configuration is in `.env` file:
- `FLASK_HOST`: Server host (default: 0.0.0.0)
- `FLASK_PORT`: Server port (default: 5000)
- `MONGODB_URI`: MongoDB connection string
- `MONGODB_DATABASE`: Database name
- `UPLOAD_FOLDER`: Video upload directory
- `APP_IMAGE`: Application logo and favicon image path (default: static/images/pawg_patch.png)
- `VIDEO_STORAGE_MODE`: Video storage mode ("local", "gdrive", or "both")
- `GDRIVE_FOLDER_ID`: Google Drive folder ID for video storage
- `GOOGLE_CREDENTIALS_PATH`: Path to Google Drive service account JSON file
- `GOOGLE_CLIENT_ID`: Google OAuth client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret
- `GOOGLE_REDIRECT_URI`: OAuth redirect URI
- `GOOGLE_WORKSPACE_DOMAIN`: Restricted domain for OAuth
- `DEFAULT_SUPERADMIN_CAPID`: Default admin CAPID
- `WING_ADMIN_DUTY_POSITIONS`: Comma-separated list of admin duty positions
- And many more...

## Recent Updates

### Version 2.1 Features
- **Google Drive Integration**: Flexible video storage with local, cloud, or hybrid options
- **Smart Video Serving**: Automatic fallback between local and cloud storage
- **Enhanced Video Management**: Track video locations and storage status
- **Improved Footer Layout**: Consistent footer positioning across all pages
- **Configurable Branding**: Application logo and favicon controlled via APP_IMAGE environment variable

### Version 2.0 Features
- **Google OAuth Integration**: Secure authentication with domain restriction
- **Admin Dashboard**: Comprehensive management interface
- **Event Management**: Lock/unlock events and prevent duplicates
- **Mobile Optimization**: Full responsive design for all devices
- **Video Processing**: Automatic MP4 conversion and thumbnail generation
- **Data Export**: CSV export functionality
- **Dark/Light Mode**: User-selectable themes
- **Background Processing**: Asynchronous video handling
- **Improved UX**: Better navigation, spacing, and touch interfaces

## Support

For technical support or questions about the COV Inspection Tool, contact your Wing's IT department or the development team.

## License

This tool is developed for Civil Air Patrol Wings with CAPWATCH and Google Workspace integration capabilities.
