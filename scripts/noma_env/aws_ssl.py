"""AWS client helpers (SSL trust store on Windows)."""

from __future__ import annotations


def bootstrap_aws_ssl() -> None:
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
