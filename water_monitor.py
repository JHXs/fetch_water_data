import csv
import json
import logging
import random
import time
import sqlite3
from contextlib import closing
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
DATA_BASE_DIR = Path("data_base")
RETRY_TIMES = 5
WAIT_TIMEOUT = 30000  # 30秒


class WaterQualityMonitor:
    def __init__(self):
        self.user_agent = UserAgent().random
        self.data_dir = DATA_DIR / datetime.now().strftime("%Y-%m-%d")
        self.data_base_dir = DATA_BASE_DIR
        self.db_back_dir = DATA_BASE_DIR / f"backups"
        self._setup_directories()
        self.db_path = self.data_base_dir / "water_quality.db"
        self._init_db()

    def _setup_directories(self):
        """创建数据存储目录"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_base_dir.mkdir(parents=True, exist_ok=True)
        self.db_back_dir.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        """初始化数据库表结构"""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS water_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
            省份 TEXT NOT NULL,                  -- 监测点所在省份
            流域 TEXT,                           -- 所属流域信息
            断面名称 TEXT NOT NULL,              -- 监测断面名称
            监测时间 TEXT NOT NULL,              -- 数据唯一性标识（格式：YYYY-MM-DD HH:MM）
            水质类别 TEXT NOT NULL,              -- 水质分类等级
            水温 REAL CHECK(水温 >= 0),          -- 摄氏度
            pH REAL CHECK(pH BETWEEN 0 AND 14), -- 酸碱度
            溶解氧 REAL CHECK(溶解氧 >= 0),      -- mg/L
            电导率 REAL CHECK(电导率 >= 0),      -- μS/cm
            浊度 REAL CHECK(浊度 >= 0),          -- NTU
            高锰酸盐指数 REAL CHECK(高锰酸盐指数 >= 0),  -- mg/L
            氨氮 REAL CHECK(氨氮 >= 0),          -- mg/L
            总磷 REAL CHECK(总磷 >= 0),          -- mg/L
            总氮 REAL CHECK(总氮 >= 0),          -- mg/L
            叶绿素α REAL CHECK(叶绿素α >= 0),    -- μg/L
            藻密度 REAL CHECK(藻密度 >= 0),      -- cells/L
            站点情况 TEXT,                       -- 站点状态描述
            raw_json TEXT NOT NULL,              -- 原始数据备份
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')

            # 创建联合索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_断面_时间 
                ON water_data (断面名称, 监测时间 DESC)
            ''')

            conn.commit()

    # 添加定期数据库备份功能
    def backup_db(self):
        backup_path = self.db_back_dir / f"backup_{datetime.now().strftime('%Y%m%d')}.db"
        with closing(sqlite3.connect(self.db_path)) as src:
            with closing(sqlite3.connect(backup_path)) as dest:
                src.backup(dest)
        logger.info(f"数据库备份完成：{backup_path}")

    def _convert_value(self, value, field_name):
        """安全类型转换（处理空值和异常）"""
        try:
            if value is None or str(value).strip() == "":
                return None
            return float(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"字段 [{field_name}] 值转换失败: {value} | 错误: {str(e)}")
            return None
        
    def _validate_data(self, item):
        """数据有效性校验"""
        if not item["监测时间"]["显示值"]:
            raise ValueError("监测时间缺失")
        
        # 示例校验：监测时间格式应为 "YYYY-MM-DD HH:MM"
        try:
            datetime.strptime(item["监测时间"]["显示值"], "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError(f"无效监测时间格式: {item['监测时间']['显示值']}")

    def _save_to_db(self, data):
        """优化后的数据库存储"""
        if not data:
            logger.warning("无有效数据需要存储")
            return
        success_count = 0
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # 开启事务
                conn.execute("BEGIN TRANSACTION")
                
                for item in data:
                    try:
                        self._validate_data(item)
                        
                        insert_data = (
                            item["省份"]["显示值"],
                            item["流域"]["显示值"],
                            item["断面名称"]["显示值"],
                            item["监测时间"]["显示值"],
                            item["水质类别"]["显示值"],
                            self._convert_value(item["水温"]["原始值"], "水温"),
                            self._convert_value(item["pH"]["原始值"], "pH"),
                            self._convert_value(item["溶解氧"]["原始值"], "溶解氧"),
                            self._convert_value(item["电导率"]["原始值"], "电导率"),
                            self._convert_value(item["浊度"]["原始值"], "浊度"),
                            self._convert_value(item["高锰酸盐指数"]["原始值"], "高锰酸盐指数"),
                            self._convert_value(item["氨氮"]["原始值"], "氨氮"),
                            self._convert_value(item["总磷"]["原始值"], "总磷"),
                            self._convert_value(item["总氮"]["原始值"], "总氮"),
                            self._convert_value(item["叶绿素α"]["原始值"], "叶绿素α"),
                            self._convert_value(item["藻密度"]["原始值"], "藻密度"),
                            item["站点情况"]["显示值"],
                            json.dumps(item, ensure_ascii=False)
                        )
                        
                        cursor.execute('''INSERT OR IGNORE INTO water_data 
                            (省份, 流域, 断面名称, 监测时间, 水质类别,
                            水温, pH, 溶解氧, 电导率, 浊度,
                            高锰酸盐指数, 氨氮, 总磷, 总氮,
                            叶绿素α, 藻密度, 站点情况, raw_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            insert_data)
                        if cursor.rowcount > 0:
                            success_count += 1
                        else:
                            logger.warning(f"数据重复被忽略 - 时间+断面: {insert_data[3]} ({insert_data[2]})")  # 显示时间和断面名称
                    except Exception as e:
                        logger.error(f"数据校验/插入失败: {str(e)} | 数据: {json.dumps(item)}")
                
                # 批量提交
                conn.commit()
                logger.info(f"数据库写入完成，成功 {success_count}/{len(data)} 条")
                
        except sqlite3.Error as e:
            logger.error(f"数据库操作失败: {str(e)}")

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

        # 添加随机屏幕分辨率
        VIEWPORT_SIZES = [
            {"width": 1366, "height": 768},
            {"width": 1920, "height": 1080},
            {"width": 1536, "height": 864}
        ]
        
        context = browser.new_context(
            ignore_https_errors=True,
            user_agent=self.user_agent,
            viewport=random.choice(VIEWPORT_SIZES)
        )
        # 屏蔽部分特征
        context.add_init_script("""
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh']
            });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ? 
                    Promise.resolve({ state: 'denied' }) :
                    originalQuery(parameters)
            );
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

    def _complete_year(self, time_str: str) -> str:
        """补全年份到监测时间（2025-03-27 16:00 格式）"""
        if not time_str:
            return None
        
        try:
            # 如果已经是完整格式直接返回
            datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            return time_str
        except ValueError:
            try:
                # 补全年份并验证
                current_year = datetime.now().year
                full_time = f"{current_year}-{time_str}"
                datetime.strptime(full_time, "%Y-%m-%d %H:%M")
                return full_time
            except (ValueError, TypeError) as e:
                logger.warning(f"时间格式无效: {time_str} ({str(e)})")
                return None  # 让后续校验捕获这个错误

    # 数据解析函数
    def _parse_row(self, row) -> Dict:
        """解析单行数据"""
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
        # row_data = {}
        # for key, element in cells.items():
            # if element:
            #     display_value = element.inner_text().strip()
            #     raw_value = element.get_attribute("data-original-title")
            #     # 处理原始值（仅当存在tooltip时）
            #     if raw_value and "原始值" in raw_value:
            #         raw_value = raw_value.split("：")[-1].strip()
            #     else:
            #         raw_value = None
            #     row_data[key] = {"显示值": display_value, "原始值": raw_value}
            # else:
            #     row_data[key] = {"显示值": None, "原始值": None}
        parsed_data = {}
        for key, element in cells.items():
            try:
                display_value = element.inner_text().strip() if element else None
                raw_value = element.get_attribute("data-original-title") if element else None
                # 特殊处理监测时间
                if key == "监测时间":
                    display_value = self._complete_year(display_value)
                    if raw_value and "原始值" in raw_value:  # 如果原始值也需要处理
                        raw_value = self._complete_year(raw_value.split("：")[-1].strip())

                if raw_value and "原始值" in raw_value:
                    raw_value = raw_value.split("：")[-1].strip()
                parsed_data[key] = {"显示值": display_value, "原始值": raw_value}
            except Exception as e:
                logger.warning(f"解析字段 {key} 失败: {str(e)}")
                parsed_data[key] = {"显示值": None, "原始值": None}
        return parsed_data

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
                water_data.append(self._parse_row(row))
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
        
        ### 保存到数据库
        self._save_to_db(data)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            # CSV保存
            csv_path = self.data_dir / f"water_quality_{timestamp}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # 写入表头（根据字段顺序调整）
                headers = ["省份", "流域", "断面名称", "监测时间", "水质类别", 
                        "水温_显示值", "水温_原始值", "pH_显示值", "pH_原始值", 
                        "溶解氧_显示值", "溶解氧_原始值", "电导率_显示值", "电导率_原始值",
                        "浊度_显示值", "浊度_原始值", "高锰酸盐指数_显示值", "高锰酸盐指数_原始值",
                        "氨氮_显示值", "氨氮_原始值", "总磷_显示值", "总磷_原始值",
                        "总氮_显示值", "总氮_原始值", "叶绿素α_显示值", "叶绿素α_原始值",
                        "藻密度_显示值", "藻密度_原始值", "站点情况"]
                writer.writerow(headers)
                
                # 写入数据行
                for item in data:
                    row = [
                        item["省份"]["显示值"], item["流域"]["显示值"], item["断面名称"]["显示值"],
                        item["监测时间"]["显示值"], item["水质类别"]["显示值"],
                        item["水温"]["显示值"], item["水温"]["原始值"],
                        item["pH"]["显示值"], item["pH"]["原始值"],
                        item["溶解氧"]["显示值"], item["溶解氧"]["原始值"],
                        item["电导率"]["显示值"], item["电导率"]["原始值"],
                        item["浊度"]["显示值"], item["浊度"]["原始值"],
                        item["高锰酸盐指数"]["显示值"], item["高锰酸盐指数"]["原始值"],
                        item["氨氮"]["显示值"], item["氨氮"]["原始值"],
                        item["总磷"]["显示值"], item["总磷"]["原始值"],
                        item["总氮"]["显示值"], item["总氮"]["原始值"],
                        item["叶绿素α"]["显示值"], item["叶绿素α"]["原始值"],
                        item["藻密度"]["显示值"], item["藻密度"]["原始值"],
                        item["站点情况"]["显示值"]
                    ]
                    writer.writerow(row)
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
        logger.info(f"########-----------------------爬取开始----------------###########：{datetime.now()}")
        success = False
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

                    # 备份数据库
                    self.backup_db()
                    
                    # 关闭浏览器
                    browser.close()
                    return True
            except Exception as e:
                logger.error(f"第 {attempt+1} 次尝试失败，错误类型：{type(e).__name__}")
                if attempt < RETRY_TIMES - 1:
                    wait_time = (2 ** attempt) * 10  # 指数退避
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
        if not success:
            logger.critical(f"连续 {RETRY_TIMES} 次尝试失败，任务终止！")
        return success

if __name__ == "__main__":
    monitor = WaterQualityMonitor()
    if monitor.run():
        logger.info("数据抓取任务执行成功")
    else:
        logger.error("数据抓取任务执行失败")
