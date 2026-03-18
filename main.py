#!/usr/bin/env python3

from renglo_api import create_app
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_aws_credentials():
    """
    Setup AWS credentials from environment variables.
    
    This ensures boto3 can authenticate with AWS services.
    Checks for AWS_PROFILE or standard AWS credentials.
    """
    # Check if AWS_PROFILE is set
    aws_profile = os.getenv('AWS_PROFILE')
    if aws_profile:
        logger.info(f"✓ Using AWS Profile: {aws_profile}")
        return True
    
    # Check if standard AWS credentials are set
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    if aws_access_key and aws_secret_key:
        logger.info("✓ Using AWS credentials from environment variables")
        return True
    
    # Check if AWS credentials file exists
    aws_credentials_file = os.path.expanduser('~/.aws/credentials')
    if os.path.exists(aws_credentials_file):
        logger.info("✓ AWS credentials file found at ~/.aws/credentials")
        logger.info("  Using default profile (set AWS_PROFILE to use a different profile)")
        return True
    
    # No credentials found - warn but don't fail (app might not need AWS)
    logger.warning("⚠️  No AWS credentials found!")
    logger.warning("   AWS services (S3, DynamoDB, Cognito) will fail.")
    logger.warning("   To fix, either:")
    logger.warning("   1. Run: aws configure")
    logger.warning("   2. Set: export AWS_PROFILE=your_profile")
    logger.warning("   3. Set: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    return False


def setup_aws_region():
    """
    Setup AWS region from environment or config.
    """
    # Check environment variable first
    aws_region = os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
    
    if not aws_region:
        # Try to get from config
        try:
            from env_config import AWS_REGION
            aws_region = AWS_REGION
            os.environ['AWS_DEFAULT_REGION'] = aws_region
            logger.info(f"✓ AWS Region set from config: {aws_region}")
        except (ImportError, AttributeError):
            # Default to us-east-1
            aws_region = 'us-east-1'
            os.environ['AWS_DEFAULT_REGION'] = aws_region
            logger.info(f"✓ AWS Region defaulted to: {aws_region}")
    else:
        logger.info(f"✓ AWS Region: {aws_region}")
    
    return aws_region


def main():
    """
    Main application entry point.
    
    Option 1: Load config from env_config.py in current directory (this example)
    Option 2: Pass config dict directly (see example below)
    """
    
    logger.info("=" * 60)
    logger.info("Starting Renglo System")
    logger.info("=" * 60)
    
    # Setup AWS credentials and region
    setup_aws_credentials()
    setup_aws_region()
    
    logger.info("-" * 60)
    
    # Option 1: Load from env_config.py in current directory
    # The env_config.py file is in this application directory, not in renglo-api
    app = create_app()
    
    # Option 2: Pass config directly (uncomment to use)
    # config = {
    #     'DYNAMODB_CHAT_TABLE': 'my_app_chat',
    #     'OPENAI_API_KEY': 'sk-...',
    #     'COGNITO_REGION': 'us-east-1',
    #     # ... all your config
    # }
    # app = create_app(config=config)
    
    # Option 3: Load from custom path (uncomment to use)
    # app = create_app(config_path='/path/to/custom/env_config.py')
    
    logger.info("Application configured successfully")
    logger.info(f"Running in {'Lambda' if app.config.get('IS_LAMBDA') else 'Local'} mode")

    # Pin log level to LOG_LEVEL so Flask debug=True does not enable DEBUG logs
    level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, level_name, logging.INFO)
    app.logger.setLevel(log_level)
    logging.getLogger('renglo').setLevel(log_level)
    
    # Run the Flask development server
    # For production, use a proper WSGI server like gunicorn
    port = int(os.getenv('PORT', 5001))  # Port 5000 is often used by macOS AirPlay
    
    logger.info(f"Starting server on port {port}...")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )


if __name__ == '__main__':
    main()

