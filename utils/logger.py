import logging
import sys
from pathlib import Path
from datetime import datetime

def get_logger(name: str) -> logging.Logger:
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    log_file = log_dir / f'{name}_{today}.log'
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
