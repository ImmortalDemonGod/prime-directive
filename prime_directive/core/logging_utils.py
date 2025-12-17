import logging
import logging.config
import os


def setup_logging(log_file="~/.prime-directive/logs/pd.log"):
    """
    Configure application logging to write INFO-level messages to a file.
    
    The provided `log_file` path is expanded (tilde resolution) and its directory is created if missing. A file handler using UTF-8 encoding is installed on the root logger at INFO level; console output is not configured here.
    
    Parameters:
        log_file (str): Path to the log file (tilde-expanded).
    """
    log_file = os.path.expanduser(log_file)
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": (
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            },
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "level": "INFO",
                "formatter": "standard",
                "filename": log_file,
                "encoding": "utf8",
            },
            # We can add console handler if we want verbose output,
            # but Typer/Rich handles console mostly.
        },
        "root": {"level": "INFO", "handlers": ["file"]},
    }
    logging.config.dictConfig(config)