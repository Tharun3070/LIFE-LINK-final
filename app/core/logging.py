import logging
import sys
from app.core.config import settings

# Configure standard structured logger for LifeLink
LOG_FORMAT = "%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s:%(lineno)d) - %(message)s"

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("lifelink")
