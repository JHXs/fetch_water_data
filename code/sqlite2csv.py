import sqlite3
import logging
import csv
import os
from datetime import datetime
from config import DATA_DIR,DATA_BASE_DIR,LOG_DIR

### 路径及文件配置
OUT_DIR = DATA_DIR / "0_sqlite2csv"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out_file = OUT_DIR / f"water_quality_{timestamp}.csv"
db_file = DATA_BASE_DIR / "water_quality.db"
log_file = LOG_DIR / "sqlite2csv.log"


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


# 确保输出目录存在
os.makedirs(str(OUT_DIR), exist_ok=True)

# 连接数据库
conn = sqlite3.connect(str(db_file))
cursor = conn.cursor()

try:
    # 执行查询（使用三引号包裹多行SQL）
    cursor.execute("""
        SELECT 
            省份, 流域, 所在地市, 所属河流, 断面名称, 监测时间, 水质类别, 水温, pH, 溶解氧, 
            电导率, 浊度, 高锰酸盐指数, 氨氮, 总磷, 总氮, 叶绿素α, 藻密度, 站点情况 
        FROM guangxi
        WHERE 断面名称 = '龙岩滩水库'
        ORDER BY 监测时间 DESC;
    """)
    rows = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]

    # 写入CSV文件（自动添加BOM）
    with open(out_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(column_names)  # 写入列标题
        writer.writerows(rows)         # 写入数据行

finally:
    # 确保连接关闭
    logger.info(f"数据库导出完成：{out_file}")
    conn.close()
    