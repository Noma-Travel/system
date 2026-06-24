"""
Application Entry Point for Production

Use this with production WSGI servers like Gunicorn, uWSGI, or Zappa.

Example usage:
    gunicorn application:app -w 4 -b 0.0.0.0:8000
    zappa deploy <project>  # Uses application.app

Set URL_PREFIX in the environment to strip path segments before the app routes.
Examples: "x_prod", "x/y", "x/k/q/w" — supports any deployment path depth.
"""

from renglo_api import create_app
from renglo_api.apigw_stage_middleware import strip_url_prefix

# Create application instance
# Config will be loaded from env_config.py in this directory
app = create_app()

# Strip URL prefix from path when present (works with any deployment service)
app = strip_url_prefix(app)

if __name__ == '__main__':
    # This is only for testing; use gunicorn/uwsgi in production
    app.run(host='0.0.0.0', port=8000)

