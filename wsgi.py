import sys
import os as _os
_path = _os.path.dirname(_os.path.abspath(__file__))
if _path not in sys.path:
    sys.path.insert(0, _path)
from app import app as application, init_db
init_db()
