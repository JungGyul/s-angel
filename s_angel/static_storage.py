"""Static files storage that never takes the site down.

If `collectstatic` has not run on the host (no manifest), `{% static %}` falls back to the
plain, unhashed URL instead of raising, and WhiteNoise serves the file straight from the
app's static directories (WHITENOISE_USE_FINDERS). When the manifest exists, hashed,
compressed, long-cached URLs are used as usual.
"""
from django.contrib.staticfiles.storage import StaticFilesStorage
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SafeCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False

    def url(self, name, force=False):
        try:
            return super().url(name, force)
        except ValueError:
            return StaticFilesStorage.url(self, name)
