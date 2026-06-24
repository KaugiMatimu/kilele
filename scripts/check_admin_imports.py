import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from importlib import import_module
modules = ['users.admin','members.admin','contributions.admin','loans.admin','notifications.admin']
for m in modules:
    try:
        import_module(m)
        print('Imported', m)
    except Exception as e:
        print('Error importing', m, type(e).__name__, e)
