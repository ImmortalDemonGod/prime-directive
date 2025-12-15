import logging
import logging.config
import yaml
import os

def setup_logging(log_file="data/logs/pd.log"):
    """
    Configure logging to file and console.
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "level": "INFO",
                "formatter": "standard",
                "filename": log_file,
                "encoding": "utf8"
            },
            # We can add console handler if we want verbose output, 
            # but Typer/Rich handles console mostly.
        },
        "root": {
            "level": "INFO",
            "handlers": ["file"]
        }
    }
    logging.config.dictConfig(config)
