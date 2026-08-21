"""
Application Entry Point for Production

Use this with production WSGI servers like Gunicorn, uWSGI, or Zappa.

Example usage:
    gunicorn application:app -w 4 -b 0.0.0.0:8000
    zappa deploy <project>  # Uses application.app
"""

from noma.runtime.boot import create_app_for_process

# Create application instance
# Config will be loaded from env_config.py in this directory.
# Default factory is still renglo_api.create_app; NOMA_OWN_APP=1 selects Noma.
app = create_app_for_process()

if __name__ == '__main__':
    # This is only for testing; use gunicorn/uwsgi in production
    app.run(host='0.0.0.0', port=8000)

