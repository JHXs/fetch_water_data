import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from config import DATA_BASE_DIR,LOG_DIR

# DATA_BASE_DIR = Path("data_base")
db_back_dir = DATA_BASE_DIR / f"backups"
db_path = DATA_BASE_DIR / "water_quality.db"
log_file = LOG_DIR / "backup_db.log"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(log_file)),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MAX_BACKUPS = 5          # 最多保留的备份数

# 添加定期数据库备份功能
def backup_db():
    backup_path = db_back_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    with closing(sqlite3.connect(db_path)) as src:
        with closing(sqlite3.connect(backup_path)) as dest:
            src.backup(dest)
    logger.info(f"数据库备份完成：{backup_path}")

    # 2. 清理旧备份
    backups = sorted(db_back_dir.glob("backup_*.db"),
                     key=lambda p: p.stat().st_mtime,
                     reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink(missing_ok=True)
        logger.info(f"删除旧备份：{old}")

if __name__ == "__main__":
    backup_db()
