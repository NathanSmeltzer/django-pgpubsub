# pgpubsub Logging Configuration

This document explains how to configure logging for the pgpubsub package.

## Overview

The pgpubsub package provides multiple ways to configure logging to capture all pgpubsub-related log messages to a file.

## Method 1: Using the Management Command (Automatic)

When you run the `listen` management command, logging is automatically configured:

```bash
python manage.py listen --channels my_channel --loglevel DEBUG --logformat "%(asctime)s %(levelname)s %(message)s"
```

**Options:**
- `--loglevel`: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--logformat`: Set the log message format

**Environment Variables:**
- `PGPUBSUB_LOG_DIR`: Directory to store log files (defaults to `/app/logs`)

## Method 2: Programmatic Setup

If you're using pgpubsub programmatically or want to set up logging before running the management command:

```python
from pgpubsub.logging_utils import setup_pgpubsub_logging

# Basic setup
setup_pgpubsub_logging()

# Custom setup
setup_pgpubsub_logging(
    log_dir="/path/to/logs",
    log_level="DEBUG",
    log_format="%(asctime)s %(levelname).4s %(message)s",
    propagate=False
)
```

## Method 3: Django Settings Integration

For Django projects, you can integrate pgpubsub logging with your existing `LOGGING` configuration:

```python
# In your settings.py
import os
from pgpubsub.logging_utils import configure_django_logging_for_pgpubsub

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
    },
}

# Merge pgpubsub logging configuration
pgpubsub_config = configure_django_logging_for_pgpubsub()
LOGGING['handlers'].update(pgpubsub_config['handlers'])
LOGGING['loggers'].update(pgpubsub_config['loggers'])
LOGGING['formatters'].update(pgpubsub_config['formatters'])
```

## Log Files

All methods create a log file at:
- `{PGPUBSUB_LOG_DIR}/pgpubsub.log` (default: `./logs/pgpubsub.log`)

The log file captures all log messages from:
- `pgpubsub.listen` module
- `pgpubsub.management.commands.listen` module
- All other `pgpubsub.*` modules

## Log Levels

- **DEBUG**: Detailed information, typically of interest only when diagnosing problems
- **INFO**: General information about program execution (default)
- **WARNING**: Something unexpected happened, but the software is still working
- **ERROR**: Due to a more serious problem, the software has not been able to perform some function
- **CRITICAL**: A serious error, indicating that the program itself may be unable to continue running

## Example Log Output

```
2024-01-15 10:30:45 INFO  Listening on AuthorChannel
2024-01-15 10:30:47 INFO  Processing notification for AuthorChannel
2024-01-15 10:30:47 INFO  Obtained lock on Notification: channel=author_channel, payload={"id": 123}
2024-01-15 10:30:47 DEBUG Executing callback: create_post_from_author
```

## Troubleshooting

**Log file not created:**
- Check that the log directory exists and is writable
- Verify `PGPUBSUB_LOG_DIR` environment variable is set correctly
- Ensure you're using one of the setup methods above

**No log messages:**
- Check that the log level is set appropriately
- Verify that pgpubsub code is actually being executed
- Make sure you're not filtering out pgpubsub logs in your Django logging configuration

**Duplicate log messages:**
- This usually happens when logging is configured multiple times
- Use `propagate=False` in the setup to prevent propagation to parent loggers