"""
Application Entry Point for Production

Use this with production WSGI servers like Gunicorn, uWSGI, or Zappa.

Example usage:
    gunicorn application:app -w 4 -b 0.0.0.0:8000
    zappa deploy <project>  # Uses application.app
"""

from noma.runtime.boot import create_app_for_process

# Zero env logic in this wrapper: config comes entirely from os.environ
# (Zappa `environment_variables` in zappa_settings.json). env_config.py is
# a local-dev-only file (see noma/__main__.py) and is never in the Lambda
# zip -- zappa_update.sh excludes it by basename.
# Process factory is noma.runtime.app.create_app (NOMA_OWN_APP is ignored).
app = create_app_for_process()

if __name__ == '__main__':
    # This is only for testing; use gunicorn/uwsgi in production
    app.run(host='0.0.0.0', port=8000)

