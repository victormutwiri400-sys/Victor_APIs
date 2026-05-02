import os
import sys

# This tells the server exactly where your installed packages are
venv_path = '/home/victordesigner/www/venv/lib/python3.13/site-packages'
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

# This tells the server where your api.py file is
app_path = '/home/victordesigner/www'
if app_path not in sys.path:
    sys.path.insert(0, app_path)

from api import app as application