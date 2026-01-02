import logging
import sys
from datetime import datetime

# Create logger
logger = logging.getLogger("eqio")
logger.setLevel(logging.DEBUG)

# Console Handler (INFO+)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter(
    '%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%H:%M:%S'
)
console_handler.setFormatter(console_format)

# File Handler (DEBUG+)
file_handler = logging.FileHandler('eqio.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_format = logging.Formatter(
    '%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_format)

# Add handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)

def get_logger(name: str = "atom") -> logging.Logger:
    """Get a child logger with the given name."""
    return logging.getLogger(f"atom.{name}")
