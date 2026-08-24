#!/usr/bin/env python3
"""
Smoke the Noma factory: config, create_app, /v1 routes, /ping.

Run from system/ with the backend package on PYTHONPATH (venv + noma_env
launcher already set this). Optional: python test_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_system_dir = Path(__file__).resolve().parent
_root = _system_dir.parent
for _rel in ("extensions/backend/package", str(_system_dir)):
    _p = str(_root / _rel)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from noma.runtime import create_app
from noma.runtime.env_config import load_env_config


def test_configuration():
    """Test that configuration loads correctly."""
    print("=" * 60)
    print("Testing Application Configuration")
    print("=" * 60)

    config = load_env_config()

    print(f"\n✓ Loaded {len(config)} configuration values")

    required_configs = [
        "DYNAMODB_ENTITY_TABLE",
        "DYNAMODB_CHAT_TABLE",
        "COGNITO_REGION",
        "COGNITO_USERPOOL_ID",
        "OPENAI_API_KEY",
        "BASE_URL",
    ]

    missing = []
    for key in required_configs:
        if key in config and config[key] and config[key] != "your-secret-key-here":
            value = str(config[key])
            print(f"  ✓ {key}: {value[:20]}{'...' if len(value) > 20 else ''}")
        else:
            print(f"  ✗ {key}: NOT SET")
            missing.append(key)

    if missing:
        print(f"\n⚠️  Warning: {len(missing)} required config(s) not properly set")
        print("   Update env_config.py with real values for production use")
    else:
        print("\n✓ All required configurations are set")

    return len(missing) == 0


def test_app_creation():
    """Test that Flask app can be created."""
    print("\n" + "=" * 60)
    print("Testing Flask App Creation")
    print("=" * 60)

    try:
        app = create_app()
        print("\n✓ Flask app created successfully")
        print(f"  - Environment: {'Lambda' if app.config.get('IS_LAMBDA') else 'Local'}")
        print(f"  - Debug mode: {app.debug}")
        print(f"  - Config loaded: {len(app.config)} keys")
        return True
    except Exception as e:
        print(f"\n✗ Failed to create Flask app: {e}")
        return False


def test_routes():
    """Test that Noma /v1 routes and /ping are registered."""
    print("\n" + "=" * 60)
    print("Testing Route Registration")
    print("=" * 60)

    try:
        app = create_app()

        rules = [rule.rule for rule in app.url_map.iter_rules()]
        print(f"\n✓ {len(rules)} routes registered")

        has_ping = any(r == "/ping" or r.endswith("/ping") for r in rules)
        v1_rules = [r for r in rules if r.startswith("/v1/")]
        print(f"  - /ping present: {has_ping}")
        print(f"  - /v1 routes: {len(v1_rules)}")

        print("\n  Sample /v1 routes:")
        for route in sorted(v1_rules)[:10]:
            print(f"    {route}")

        return has_ping and bool(v1_rules)
    except Exception as e:
        print(f"\n✗ Failed to test routes: {e}")
        return False


def test_health_endpoint():
    """Test the health check endpoint."""
    print("\n" + "=" * 60)
    print("Testing Health Check Endpoint")
    print("=" * 60)

    try:
        app = create_app()
        client = app.test_client()

        response = client.get("/ping")

        if response.status_code == 200:
            print("\n✓ Health check endpoint working")
            print(f"  - Status: {response.status_code}")
            print(f"  - Response: {response.get_json()}")
            return True
        print(f"\n✗ Health check failed with status {response.status_code}")
        return False
    except Exception as e:
        print(f"\n✗ Failed to test health endpoint: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("NOMA APPLICATION TEST SUITE")
    print("=" * 60 + "\n")

    results = {
        "Configuration": test_configuration(),
        "App Creation": test_app_creation(),
        "Routes": test_routes(),
        "Health Check": test_health_endpoint(),
    }

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed. Application is ready to run.")
        print("\nNext steps:")
        print("  1. Update env_config.py with your actual AWS credentials")
        print("  2. Run the application: python main.py")
        print("  3. Visit http://localhost:5000/ping to verify")
    else:
        print("\nSome tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
