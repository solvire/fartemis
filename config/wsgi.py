# ruff: noqa
"""
WSGI config for fartemis project.

This module contains the WSGI application used by Django's development server
and any production WSGI deployments. It should expose a module-level variable
named ``application``. Django's ``runserver`` and ``runfcgi`` commands discover
this application via the ``WSGI_APPLICATION`` setting.

Usually you will have the standard Django WSGI application here, but it also
might make sense to replace the whole Django WSGI application with a custom one
that later delegates to the Django one. For example, you could introduce WSGI
middleware here, or combine a Django application with an application of another
framework.

"""
import os
import sys
from pathlib import Path
import environ
from django.core.wsgi import get_wsgi_application

# Calculate the project root directory (assuming wsgi.py is in 'config/')
# Adjust if your structure is different (e.g., if wsgi.py is at the top level)
ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent
env = environ.Env()

# --- Optional: Only if your apps are in a non-standard location ---
# If your apps are inside 'fartemis' at the root level:
# APP_DIR = ROOT_DIR / "fartemis"
# sys.path.insert(0, str(APP_DIR))
# Remove this section if unsure or if it causes problems.
# -----------------------------------------------------------------

# Define the default settings module for WSGI (production)
PRODUCTION_SETTINGS = "config.settings.production"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", PRODUCTION_SETTINGS)

# --- .env Loading ---
# Look for .env in the project root
env_file_path = ROOT_DIR / ".env"
if env_file_path.is_file():
    print(f"Loading WSGI environment from: {env_file_path}")
    # Load .env variables into os.environ, potentially overwriting DJANGO_SETTINGS_MODULE
    # if it's defined within .env
    env.read_env(str(env_file_path), overwrite=True)
    # Ensure the setting module from .env or the default is set
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", env("DJANGO_SETTINGS_MODULE", default=PRODUCTION_SETTINGS))
else:
    print(f".env file not found at {env_file_path}, using default settings module.")
    # If .env is missing, ensure the default production setting is definitely used.
    os.environ["DJANGO_SETTINGS_MODULE"] = PRODUCTION_SETTINGS


# print(f"WSGI using settings: {os.environ['DJANGO_SETTINGS_MODULE']}") # Optional: Debug print

application = get_wsgi_application()