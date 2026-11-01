import logging
import os
from datetime import datetime

class TestLogger:
    def __init__(self, test_name: str):
        self._test_name = test_name
        self._handlers = []
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """
        הגדרת הלוגר עם פורמט מותאם וכתיבה לקובץ
        """
        # יצירת תיקיית הלוגים
        log_dir = "results/logs"
        os.makedirs(log_dir, exist_ok=True)

        # הגדרת שם הקובץ עם תאריך ומזהה הבדיקה
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"{log_dir}/{timestamp}_{self._test_name}.log"
        self.log_path = log_file

        # הגדרת הלוגר
        logger = logging.getLogger(f"test_{self._test_name}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        # A named logger alone does not write output; this handler persists each log record.
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        logger.addHandler(handler)
        self._handlers.append(handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        logger.addHandler(console_handler)
        self._handlers.append(console_handler)
        return logger

    def close(self):
        """Flush and remove this logger's file handlers."""
        for handler in self._handlers:
            handler.flush()
            handler.close()
            self.logger.removeHandler(handler)
        self._handlers.clear()

    def info(self, message: str):
        self.logger.info(message)

    def error(self, message: str):
        self.logger.error(message)

    def debug(self, message: str):
        self.logger.debug(message)

    def warning(self, message: str):
        self.logger.warning(message)
