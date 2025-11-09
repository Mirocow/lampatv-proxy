import logging

class ColorFilter(logging.Filter):
    COLOR_CODES = {
        "DEBUG": "\033[90m",     # Серый
        "INFO": "\033[94m",      # Синий
        "WARNING": "\033[93m",   # Желтый
        "ERROR": "\033[91m",     # Красный
        "CRITICAL": "\033[95m",  # Фиолетовый
        "RESET": "\033[0m",      # Сброс цвета
    }

    def filter(self, record):
        # Добавляем цветовые коды в запись
        record.color_code = self.COLOR_CODES.get(record.levelname, self.COLOR_CODES["RESET"])
        record.reset_code = self.COLOR_CODES["RESET"]
        return True

def get_logger(logger_name: str = __name__, log_level: int = None, filter=None):
    logger = logging.getLogger(logger_name)

    if log_level:
        logger.setLevel(log_level)

    logger.propagate = False

    handler = logging.StreamHandler()
    #handler.setLevel(log_level)

    # Форматтер использует color_code и reset_code
    formatter = logging.Formatter(
        "%(color_code)s[%(asctime)s] [%(levelname)s] [%(name)s.%(funcName)s:%(lineno)d]: %(message)s %(reset_code)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Добавляем фильтр цвета
    handler.addFilter(ColorFilter())

    # Добавляем дополнительный фильтр если передан
    if filter:
        handler.addFilter(filter)

    logger.addHandler(handler)

    return logger