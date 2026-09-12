import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.conf import settings
from django.test import SimpleTestCase


class ProductionStaticFilesTests(SimpleTestCase):
    def test_production_templates_use_existing_versioned_assets(self):
        # Load settings afresh: Django's test runner changes DEBUG after startup,
        # which would otherwise leave the development storage backend in place.
        with tempfile.TemporaryDirectory() as static_root:
            result = subprocess.run(
                [sys.executable, "-c", """
import django
from django.conf import settings
settings.STATIC_ROOT = __import__('os').environ['STATIC_TEST_ROOT']
django.setup()
from django.core.management import call_command
from django.contrib.staticfiles.storage import staticfiles_storage
from django.template import Context, Template
from pathlib import Path
call_command('collectstatic', interactive=False, verbosity=0)
for asset in ['trips/dashboard.css', 'trips/status.css', 'trips/task_queue.css', 'trips/task_queue.js']:
    url = Template('{% load static %}{% static asset %}').render(Context({'asset': asset}))
    assert url != settings.STATIC_URL + asset, f'Unversioned asset: {url}'
    collected_name = url.removeprefix(settings.STATIC_URL)
    assert (Path(settings.STATIC_ROOT) / collected_name).is_file(), f'Missing asset: {url}'
    assert staticfiles_storage.url(asset) == url
assert settings.STORAGES['default']['BACKEND'] == 'django.core.files.storage.FileSystemStorage'
"""],
                cwd=Path(settings.BASE_DIR),
                env={**os.environ, "DJANGO_SETTINGS_MODULE": "legit_dashboard.settings",
                     "DJANGO_DEBUG": "0", "DJANGO_DATABASE": "sqlite",
                     "DJANGO_SECRET_KEY": "production-static-test-only",
                     "STATIC_TEST_ROOT": static_root},
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
