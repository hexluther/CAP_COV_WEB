# serve.py
import logging
import socket
import os
from flask import request
from waitress import serve
from cov_web import app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

# -----------------------------
# Configure Waitress access logging
# -----------------------------
waitress_logger = logging.getLogger('waitress')
waitress_logger.setLevel(logging.INFO)

if not waitress_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    waitress_logger.addHandler(console_handler)

# -----------------------------
# Configure Flask application logging
# -----------------------------
app.logger.setLevel(logging.INFO)

if not app.logger.handlers:
    flask_console = logging.StreamHandler()
    flask_console.setLevel(logging.INFO)
    flask_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    )
    flask_console.setFormatter(flask_formatter)
    app.logger.addHandler(flask_console)

# -----------------------------
# Log every incoming request (client IP, method, path)
# -----------------------------
@app.before_request
def log_incoming_request():
    ip = request.remote_addr or 'unknown'
    app.logger.info(f"Incoming → {ip} : {request.method} {request.path}")

# -----------------------------
# Start Waitress on configured host:port
# -----------------------------
if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 8500))
    
    # Get local IP address
    local_ip = get_local_ip()
    
    print("=" * 60)
    print("🚀 COV Inspection Tool - Production Server")
    print("=" * 60)
    print(f"📱 Touch-Friendly Interface Ready")
    print(f"🗄️  MongoDB: {os.getenv('MONGODB_DATABASE', 'cov_inspections')}")
    print(f"🌐 Server: {host}:{port}")
    print("=" * 60)
    print("📍 Access URLs:")
    print(f"   • Local:    http://127.0.0.1:{port}")
    print(f"   • Network:  http://{local_ip}:{port}")
    print("=" * 60)
    print("📱 Perfect for tablets and touch devices!")
    print("🔧 Production server with Waitress")
    print("=" * 60)
    
    serve(app, host=host, port=port)