import os
import logging

def get_logger(service_name: str = None):
    """
    Returns a logger configured with the service name and log level from environment variables.
    """
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    if service_name is None:
        service_name = os.environ.get('SERVICE_NAME', 'medina-incident-router')
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    return logger
