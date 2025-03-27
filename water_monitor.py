import csv
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from playwright.sync_api import sync_playwright, expect, TimeoutError
from fake_useragent import UserAgent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("water_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置常量
BASE_URL = "https://szzdjc.cnemc.cn:8070/GJZ/Business/Publish/RealDatas.html"
TARGET_REGION = "广西壮族自治区"
TARGET_CITY = "桂林市"
DATA_DIR = Path("data")
RETRY_TIMES = 3
WAIT_TIMEOUT = 30000  # 30秒


class WaterQualityMonitor:
    def __init__(self):
        self.user_agent = UserAgent().random
        self.data_dir = DATA_DIR / datetime.now().strftime("%Y-%m-%d")
        self._setup_directories()

    def _setup_directories(self):
        """创建数据存储目录"""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_browser_context(self, playwright):
        """创建浏览器上下文并设置反爬措施"""
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                f"--user-agent={self.user_agent}"
            ]
        )
        context = browser.new_context(
            ignore_https_errors=True,
            user_agent=self.user_agent,
            viewport={"width": 1366, "height": 768}
        )
        # 屏蔽部分特征
        context.add_init_script("""
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3]
            });
        """)
        return browser, context

    def _select_region(self, page):
        """选择目标区域"""
        try:
            # 省份选择
            page.click("#ddm_Area")
            page.wait_for_timeout(random.uniform(500, 1500))
            
            # 模拟人类操作：移动鼠标到目标区域
            region_locator = page.locator(f"text={TARGET_REGION}")
            region_locator.hover(timeout=WAIT_TIMEOUT)
            page.wait_for_timeout(random.uniform(1000, 2000))
            
            # 等待城市选项可见
            city_locator = page.locator(f"text={TARGET_CITY}")
            expect(city_locator).to_be_visible(timeout=WAIT_TIMEOUT)
            
            # 随机延迟后点击
            page.wait_for_timeout(random.uniform(500, 1500))
            city_locator.click()
            logger.info("区域选择成功")
        except Exception as e:
            logger.error("区域选择失败", exc_info=True)
            raise

    def _scrape_data(self, page) -> List[Dict]:
        """抓取并解析数据"""
        try:
            # 等待数据加载
            page.wait_for_selector("#gridDatas li.news-item", timeout=WAIT_TIMEOUT)
            
            # 随机滚动页面模拟人类行为
            page.mouse.wheel(0, random.randint(100, 300))
            page.wait_for_timeout(random.uniform(500, 1500))
            
            data_rows = page.query_selector_all("#gridDatas li.news-item")
            logger.info(f"发现 {len(data_rows)} 条数据记录")
            
            water_data = []
            for row in data_rows:
                cells = {
                    "省份": row.query_selector("td.dq"),
                    "流域": row.query_selector("td.ly"),
                    "断面名称": row.query_selector("td.MN span"), 
                    "监测时间": row.query_selector("td.dt"),
                    "水质类别": row.query_selector("td.wt .sp_wt"),
                    # 按HTML列顺序严格匹配（从第6个td开始为参数）
                    "水温": row.query_selector("td.parm:nth-child(6) span"),  # 第6列
                    "pH": row.query_selector("td.parm:nth-child(7) span"),
                    "溶解氧": row.query_selector("td.parm:nth-child(8) span"),
                    "电导率": row.query_selector("td.parm:nth-child(9) span"),
                    "浊度": row.query_selector("td.parm:nth-child(10) span"),
                    "高锰酸盐指数": row.query_selector("td.parm:nth-child(11) span"),
                    "氨氮": row.query_selector("td.parm:nth-child(12) span"),
                    "总磷": row.query_selector("td.parm:nth-child(13) span"),
                    "总氮": row.query_selector("td.parm:nth-child(14) span"),
                    "叶绿素α": row.query_selector("td.parm:nth-child(15) span"),
                    "藻密度": row.query_selector("td.parm:nth-child(16) span"),
                    "站点情况": row.query_selector("td.parm1")  # 无tooltip，直接取文本
                }
                
                # 提取文本内容（处理可能为空的情况）
                row_data = {}
                for key, element in cells.items():
                    if element:
                        display_value = element.inner_text().strip()
                        raw_value = element.get_attribute("data-original-title")
                        # 处理原始值（仅当存在tooltip时）
                        if raw_value and "原始值" in raw_value:
                            raw_value = raw_value.split("：")[-1].strip()
                        else:
                            raw_value = None
                        row_data[key] = {"显示值": display_value, "原始值": raw_value}
                    else:
                        row_data[key] = {"显示值": None, "原始值": None}

                water_data.append(row_data)
            return water_data
        except TimeoutError:
            logger.warning("数据加载超时")
            return []
        except Exception as e:
            logger.error("数据解析失败", exc_info=True)
            return []

    def _save_data(self, data: List[Dict]):
        """保存数据到文件"""
        if not data:
            logger.warning("未获取到有效数据，跳过保存")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            # CSV保存
            csv_path = self.data_dir / f"water_quality_{timestamp}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # 写入逻辑...
            logger.info(f"CSV文件保存成功：{csv_path}")
            
            # JSON保存
            json_path = self.data_dir / f"water_quality_{timestamp}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON文件保存成功：{json_path}")
        except Exception as e:
            logger.error("文件保存失败", exc_info=True)

    def run(self):
        """执行主流程"""
        for attempt in range(RETRY_TIMES):
            try:
                with sync_playwright() as p:
                    browser, context = self._get_browser_context(p)
                    page = context.new_page()
                    
                    # 访问页面
                    page.goto(BASE_URL, timeout=WAIT_TIMEOUT)
                    logger.info(f"成功访问页面：{BASE_URL}")
                    
                    # 区域选择
                    self._select_region(page)
                    
                    # 数据抓取
                    water_data = self._scrape_data(page)
                    
                    # 保存数据
                    self._save_data(water_data)
                    
                    # 关闭浏览器
                    browser.close()
                    return True
            except Exception as e:
                logger.error(f"第 {attempt+1} 次尝试失败，等待重试...")
                time.sleep((attempt+1)*10)  # 指数退避
        logger.error(f"连续 {RETRY_TIMES} 次尝试均失败")
        return False


if __name__ == "__main__":
    monitor = WaterQualityMonitor()
    if monitor.run():
        logger.info("数据抓取任务执行成功")
    else:
        logger.error("数据抓取任务执行失败")
