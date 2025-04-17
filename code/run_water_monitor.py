# run_national.py
import random
import time
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
from config import PROVINCES,LOG_DIR
from water_monitor import WaterQualityMonitor

# 配置日志
def configure_logging():
    """统一日志配置（仅在主模块中调用一次）"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    # 1. 动态构建日志目录路径（确保目录存在）
    os.makedirs(LOG_DIR, exist_ok=True)  # 自动创建目录（如果不存在）
    log_file = Path(LOG_DIR) / f"run_water_monitor_{datetime.now().strftime('%Y%m%d')}.log"
    
    # 根日志器配置
    logging.basicConfig(
        level=logging.INFO,  ##  日志级别
        format=log_format,
        handlers=[
            TimedRotatingFileHandler(
                filename=str(log_file),
                when='midnight',  # 每天午夜轮转
                interval=7,       # 间隔7天
                backupCount=4,   # 保留28天日志
                encoding="utf-8"        # 显式指定编码（避免 Windows 下乱码）
            ),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)

class NationalMonitor:
    def __init__(self):
        self.proxies = []  # 可在此处添加代理池配置
    
    def _get_random_delay(self):
        """生成随机延迟防止封禁"""
        return random.uniform(10, 30)
    
    def run_province(self, province: str):
        """执行单个省份抓取"""
        try:
            monitor = WaterQualityMonitor(target_region=province)
            monitor.data_dir = monitor.data_dir / province  # 按省份分目录存储
            monitor.data_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"开始爬取省份：{province}")
            return monitor.run()
        except Exception as e:
            logger.error(f"省份 {province} 抓取失败: {str(e)}")
            return False
    
    def run_all(self):
        """遍历所有省份"""
        total = len(PROVINCES)
        for idx, province in enumerate(PROVINCES):
            logger.info(f"\n{'='*30} 进度：{idx+1}/{len(PROVINCES)} {'='*30}")
            
            # 执行爬取
            start_time = time.time()
            self.run_province(province)
            
            # 仅在非最后一项时等待
            if idx < total:
                # 计算延迟
                delay = self._get_random_delay()
                elapsed = time.time() - start_time
                remain_delay = max(delay - elapsed, 0)
                
                if remain_delay > 0:
                    logger.info(f"等待 {remain_delay:.1f} 秒后继续...")
                    time.sleep(remain_delay)
                else:
                    logger.debug("无需等待")

if __name__ == "__main__":
    configure_logging()  # ✅ 确保在导入其他模块前调用
    NationalMonitor().run_all()