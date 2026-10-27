import logging


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logging.basicConfig(
        level=getattr(
            logging, level.upper(), logging.INFO
        ),  # ← 这里有个新知识点：level 是字符串 "INFO"，要换成 logging.INFO
        handlers=[handler],
        force=True,
    )
