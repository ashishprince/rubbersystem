import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rubber_system.settings")
django.setup()

from django.template.loader import get_template

try:
    get_template("dashboard_manager.html")
    print("Template compiled successfully")
except Exception as e:
    import traceback
    traceback.print_exc()
