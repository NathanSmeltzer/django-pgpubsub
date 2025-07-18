import logging
import os
from typing import Optional


def setup_pgpubsub_logging(
    log_dir: Optional[str] = None,
    log_level: str = "INFO",
    log_format: str = "%(asctime)s %(levelname).4s %(message)s",
    propagate: bool = False
) -> None:
    """
    Configure logging for the pgpubsub package.
    
    Args:
        log_dir: Directory to store log files. If None, uses PGPUBSUB_LOG_DIR env var 
                 or defaults to "./logs"
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format string for log messages
        propagate: Whether to propagate to parent loggers
    
    Example:
        # In your Django project's settings.py or management command:
        from pgpubsub.logging_utils import setup_pgpubsub_logging
        
        setup_pgpubsub_logging(
            log_dir="/path/to/logs",
            log_level="DEBUG"
        )
    """
    # Determine log directory
    if log_dir is None:
        log_dir = os.getenv("PGPUBSUB_LOG_DIR", "./logs")
    
    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)

    # Get the pgpubsub logger (parent of all pgpubsub.* loggers)
    pgpubsub_logger = logging.getLogger('pgpubsub')
    
    # Remove existing handlers to avoid duplicates
    pgpubsub_logger.handlers.clear()
    
    # Create file handler
    file_handler = logging.FileHandler(
        os.path.join(log_dir, "pgpubsub.log")
    )
    file_handler.setLevel(log_level.upper())
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    file_handler.setFormatter(formatter)
    
    # Add handler to pgpubsub logger
    pgpubsub_logger.addHandler(file_handler)
    pgpubsub_logger.setLevel(log_level.upper())
    
    # Configure propagation
    pgpubsub_logger.propagate = propagate


def configure_django_logging_for_pgpubsub() -> dict:
    """
    Return a Django LOGGING configuration dict that includes pgpubsub file logging.
    
    This can be merged with your existing Django LOGGING configuration.
    
    Example:
        # In settings.py
        from pgpubsub.logging_utils import configure_django_logging_for_pgpubsub
        
        LOGGING = {
            'version': 1,
            'disable_existing_loggers': False,
            # ... your existing logging config ...
        }
        
        # Merge pgpubsub logging config
        pgpubsub_config = configure_django_logging_for_pgpubsub()
        LOGGING['handlers'].update(pgpubsub_config['handlers'])
        LOGGING['formatters'].update(pgpubsub_config['formatters'])
        LOGGING['loggers'].update(pgpubsub_config['loggers'])
    """
    log_dir = os.getenv("PGPUBSUB_LOG_DIR", "./logs")
    os.makedirs(log_dir, exist_ok=True)
    
    return {
        'handlers': {
            'pgpubsub_file': {
                'level': 'INFO',
                'class': 'logging.FileHandler',
                'filename': os.path.join(log_dir, 'pgpubsub.log'),
                'formatter': 'pgpubsub_formatter',
            },
        },
        'formatters': {
            'pgpubsub_formatter': {
                'format': '%(asctime)s %(levelname).4s %(message)s',
            },
        },
        'loggers': {
            'pgpubsub': {
                'handlers': ['pgpubsub_file'],
                'level': 'INFO',
                'propagate': False,
            },
        },
    }


def integrate_pgpubsub_logging_with_django(logging_config: dict) -> dict:
    """
    Safely integrate pgpubsub logging with an existing Django LOGGING configuration.
    
    This function modifies the logging_config dict in-place and returns it.
    
    Args:
        logging_config: Your existing Django LOGGING configuration dict
        
    Returns:
        The updated logging configuration dict
        
    Example:
        # In settings.py
        from pgpubsub.logging_utils import integrate_pgpubsub_logging_with_django
        
        LOGGING = {
            'version': 1,
            'disable_existing_loggers': False,
            # ... your existing logging config ...
        }
        
        # Integrate pgpubsub logging
        LOGGING = integrate_pgpubsub_logging_with_django(LOGGING)
    """
    pgpubsub_config = configure_django_logging_for_pgpubsub()
    
    # Initialize sections if they don't exist
    if 'handlers' not in logging_config:
        logging_config['handlers'] = {}
    if 'formatters' not in logging_config:
        logging_config['formatters'] = {}
    if 'loggers' not in logging_config:
        logging_config['loggers'] = {}
    
    # Update with pgpubsub configuration
    logging_config['handlers'].update(pgpubsub_config['handlers'])
    logging_config['formatters'].update(pgpubsub_config['formatters'])
    logging_config['loggers'].update(pgpubsub_config['loggers'])
    
    return logging_config