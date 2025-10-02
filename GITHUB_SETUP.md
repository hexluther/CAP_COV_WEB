# GitHub Repository Setup - CAP COV Web

## Repository Information
- **Repository**: https://github.com/hexluther/CAP_COV_WEB.git
- **Purpose**: Corporate Owned Vehicle Inspection Tool for Civil Air Patrol Pennsylvania Wing
- **Technology**: Flask + MongoDB + Touch-Friendly Web Interface

## Repository Structure
```
CAP_COV_WEB/
├── .gitignore                 # Git ignore rules
├── README.md                  # Main documentation
├── GITHUB_SETUP.md           # This file
├── requirements.txt           # Python dependencies
├── .env.example              # Environment configuration template
├── cov_web.py                # Main application
├── serve.py                  # Production server launcher
├── templates/
│   ├── index.html            # Main application interface
│   ├── admin_dashboard.html  # Administrative dashboard
│   ├── cov_details.html      # Individual COV details page
│   ├── admin.html            # Inspection management page
│   ├── admin_login.html      # Admin authentication page
│   ├── login.html            # User authentication page
│   └── inspection.html       # Inspection form interface
├── static/
│   ├── css/                  # Stylesheets
│   └── images/               # CAP emblems and icons
├── uploads/                  # Video upload storage (gitignored)
├── data/                     # CSV data files (gitignored)
└── reports/                  # Generated reports (gitignored)
```

## Quick Start for New Users

### 1. Clone the Repository
```bash
git clone https://github.com/hexluther/CAP_COV_WEB.git
cd CAP_COV_WEB
```

### 2. Set Up Environment
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# - Update file paths
# - Configure MongoDB connection
# - Set CAPWATCH file locations
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up MongoDB
- Ensure MongoDB is running on localhost:27017
- The app will create the `cov_inspections` database automatically

### 5. Run the Application
```bash
# Development mode
python cov_web.py

# Production mode
python serve.py
```

## Environment Configuration

Create a `.env` file based on `.env.example`:

```env
# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=False

# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=cov_inspections

# File Paths (adjust for your system)
UPLOAD_FOLDER=uploads
THUMB_FOLDER=thumbnails

# CAPWATCH Data Files (optional)
CAPWATCH_PATH=/path/to/capwatch/unload
CAPWATCH_FILE=/path/to/capwatch/unload/Member.txt
VEHICLES_FILE=/path/to/capwatch/unload/vehicles.txt

# Wing Configuration
APPLICABLE_WING=PAWG

# Google OAuth (optional)
GOOGLE_OAUTH=False
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_WORKSPACE_DOMAIN=pawg.cap.gov

# Admin Configuration
DEFAULT_SUPERADMIN_CAPID=621633
DEFAULT_SUPERADMIN_PASSWORD=your-password

# Media Configuration
ALLOWED_VIDEO_EXTENSIONS=mp4,avi,mov,wmv
PLACEHOLDER_THUMB=images/video_placeholder.png
```

## Features

- **Touch-Friendly Interface**: Designed for tablet and touch-screen use
- **MongoDB Storage**: Reliable data storage with full inspection history
- **CAPWATCH Integration**: Validates inspector CAPIDs and vehicle numbers
- **Video Documentation**: Upload walk-around inspection videos with automatic MP4 conversion
- **Multi-Step Process**: 6-page guided inspection covering all vehicle aspects
- **Administrative Dashboard**: Event management, system health monitoring, and data export
- **Event Management**: Lock/unlock events, merge duplicate events, prevent duplicate names
- **Responsive Design**: Works on both touch devices and traditional input
- **System Monitoring**: Real-time CPU, memory, and disk usage monitoring
- **Activity Logging**: Comprehensive audit trail of all administrative actions

## Development

### Branching Strategy
- `main`: Production-ready code
- `develop`: Development branch for new features
- `feature/*`: Feature branches

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Code Standards
- Follow PEP 8 for Python code
- Use meaningful commit messages
- Update documentation for new features
- Test on both touch and desktop interfaces

## Deployment

### Production Deployment
1. Set up MongoDB on production server
2. Configure environment variables in `.env`
3. Use `serve.py` for production server with Waitress
4. Set up reverse proxy (nginx/Apache) if needed
5. Configure SSL certificates
6. Ensure uploads directory has proper permissions

### Docker Deployment (Future)
- Dockerfile and docker-compose.yml can be added
- MongoDB container configuration
- Volume mounts for data persistence

## Security Considerations

- Change default secret key in production
- Use environment variables for sensitive data
- Implement proper authentication if needed
- Regular security updates
- Backup MongoDB data regularly

## Support

- **Documentation**: See README.md and GITHUB_SETUP.md
- **Issues**: Use GitHub Issues for bug reports
- **Discussions**: Use GitHub Discussions for questions
- **Contact**: Development team for CAP Pennsylvania Wing

## License

This project is developed for Civil Air Patrol Pennsylvania Wing internal use.

## Changelog

### v1.0.0 (Current Version)
- Flask-based web application with MongoDB backend
- Touch-friendly responsive interface
- CAPWATCH integration for user validation
- Video upload with automatic MP4 conversion
- Administrative dashboard with system monitoring
- Event management with locking and merging capabilities
- Comprehensive activity logging and audit trails
- System health monitoring (CPU, memory, disk usage)
- Data export functionality (CSV format)
- Professional UI with dark/light theme support
- Mass inspection mode for efficient workflow
- Super admin capabilities for data management
