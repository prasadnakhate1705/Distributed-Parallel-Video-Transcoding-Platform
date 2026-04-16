import os
from dotenv import load_dotenv

load_dotenv()

FLASK_URL = os.getenv("FLASK_URL", "http://localhost:5000")
API_KEY   = os.getenv("API_KEY", "")

FORMATS     = ["mp4", "mov", "avi"]
RESOLUTIONS = ["640x360", "1280x720", "1920x1080", "3840x2160"]
CODECS      = ["libx264", "libx265", "libvpx-vp9", "libaom-av1"]
MODES       = ["single", "parallel"]
