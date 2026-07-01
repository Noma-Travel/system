"""Fetch secrets from AWS Secrets Manager."""

from __future__ import annotations

import json
import logging
from typing import Any

from noma_env.aws_ssl import bootstrap_aws_ssl

logger = logging.getLogger(__name__)


def fetch_secrets(
    secret_id: str,
    *,
    region: str = "us-east-1",
    profile: str | None = None,
) -> dict[str, str]:
    try:
        import boto3
    except ImportError as exc:
        logger.warning("boto3 not available: %s", exc)
        return {}

    bootstrap_aws_ssl()

    try:
        import os

        prof = profile or os.environ.get("AWS_PROFILE") or "noma"
        session = boto3.Session(profile_name=prof)
        client = session.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_id)
        raw = response.get("SecretString") or ""
        if not raw:
            return {}
        parsed: Any = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items()}
    except Exception as exc:
        logger.warning("Could not load secret %s: %s", secret_id, exc)
        return {}
