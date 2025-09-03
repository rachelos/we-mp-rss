from logging.handlers import RotatingFileHandler
import logging
try:
    import colorlog
except ImportError:
    colorlog = None
from core.config import cfg
global logger
# 创建logger对象
logger = logging.getLogger(__name__)
level=cfg.get("log.level", "INFO").upper()
log_filer=cfg.get("log.file", "")

if level=="DEBUG":
    logger.setLevel(logging.DEBUG)  # 设置最低日志级别
if level=="INFO":
    logger.setLevel(logging.INFO)  # 设置最低日志级别
if level=="ERROR":
    logger.setLevel(logging.ERROR)  # 设置最低日志级别
if level=="WARNING":
    logger.setLevel(logging.WARNING)  # 设置最低日志级别
if level=="CRITICAL":
    logger.setLevel(logging.CRITICAL)  # 设置最低日志级别



# 创建文件处理器，每天一个文件，保留7天备份
if len(log_filer)<=0:
    handler = logging.NullHandler()
else:
    handler = RotatingFileHandler(f'{log_filer}.log', maxBytes=1024*1024, backupCount=7)
handler.setLevel(logging.DEBUG)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建格式器并添加到处理器
file_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(file_formatter)

if colorlog:
    console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s  - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
else:
    console_formatter = file_formatter

console_handler.setFormatter(console_formatter)

# 将处理器添加到logger
logger.addHandler(handler)
logger.addHandler(console_handler)