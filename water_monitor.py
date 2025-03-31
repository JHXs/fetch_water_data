import csv
import json
import logging
import random
import sys
import time
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from config import PROVINCE_MAPPING

from playwright.sync_api import sync_playwright, expect, TimeoutError
from fake_useragent import UserAgent

# # 配置日志
# logging.basicConfig(
#     level=logging.INFO,
#     # level=logging.DEBUG,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.FileHandler("water_monitor.log"),
#         logging.StreamHandler()
#     ]
# )
logger = logging.getLogger(__name__) ##  # 继承根日志器配置

### 从配置文件导入配置变量
from config import (
    BASE_URL,
    DEFAULT_REGION,
    DEFAULT_CITY,
    DATA_DIR,
    DATA_BASE_DIR,
    RETRY_TIMES,
    WAIT_TIMEOUT
)

class WaterQualityMonitor:
    def __init__(self, target_region=DEFAULT_REGION, target_city=DEFAULT_CITY):
        logger.debug(f"__init__()")
        try:
            self.user_agent = UserAgent().random
            logger.info(f"初始化水质监测器，目标区域：{target_region}")
            
            self.TARGET_REGION = target_region
            self.TARGET_CITY = target_city
            self.data_dir = DATA_DIR / datetime.now().strftime("%Y-%m-%d")
            self.data_base_dir = DATA_BASE_DIR

            # 记录目录初始化过程
            logger.debug("正在创建数据存储目录...")
            self._setup_directories()
            
            # 记录数据库初始化过程
            logger.debug("正在初始化数据库...")
            self.db_path = self.data_base_dir / "water_quality.db"
            self._init_db(province=target_region)
            
            logger.info("水质监测器初始化完成--__init__()--")
        except Exception as e:
            logger.critical("水质监测器初始化失败！--__init__()--", exc_info=True)
            raise

    def _setup_directories(self):
        """创建数据存储目录"""
        logger.debug(f"_setup_directories()")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_base_dir.mkdir(parents=True, exist_ok=True)

    def _init_db(self, province):
        """初始化数据库表结构"""
        """根据省份初始化数据库表"""
        logger.debug(f"_init_db()")
        self.table_name = PROVINCE_MAPPING[province]
        logger.debug(f"生成表名：{self.table_name}")  # 添加调试日志
        
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()

            # # 删除旧表（仅在开发环境或首次部署时执行），执行前请先手动备份数据库
            # cursor.execute("DROP TABLE IF EXISTS water_data")

            cursor.execute(f'''CREATE TABLE IF NOT EXISTS "{self.table_name}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                省份 TEXT NOT NULL,                  -- 监测点所在省份
                流域 TEXT,                           -- 所属流域信息
                所在地市 TEXT,                       -- 所在地市信息
                所属河流 TEXT,                       -- 所属河流信息
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- 添加联合唯一约束 --
                UNIQUE (监测时间, 断面名称)
            )''')

            # 创建联合索引
            cursor.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_断面_时间
                ON {self.table_name} (断面名称, 监测时间 DESC)
            ''')

            conn.commit()

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
        """数据有效性校验（允许维护状态数据）"""
        site_status = item.get("站点情况", {}).get("显示值", "")
        
        # 如果站点在维护，跳过时间校验
        if site_status != "正常":
            logger.debug(f"断面 {item['断面名称']['显示值']} 处于维护状态，跳过数据校验")
            return

        if not item["监测时间"]["显示值"]:
            raise ValueError("监测时间缺失")
        
        # 示例校验：监测时间格式应为 "YYYY-MM-DD HH:MM"
        try:
            datetime.strptime(item["监测时间"]["显示值"], "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError(f"无效监测时间格式: {item['监测时间']['显示值']}")

    def _save_to_db(self, data, province):
        """优化后的数据库存储"""
        logger.debug(f"_save_to_db()")

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
                            item["所在地市"]["显示值"],
                            item["所属河流"]["显示值"],
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
                        
                        cursor.execute(f'''INSERT OR IGNORE INTO {self.table_name} 
                            (省份, 流域, 所在地市, 所属河流, 断面名称, 监测时间, 水质类别,
                            水温, pH, 溶解氧, 电导率, 浊度,
                            高锰酸盐指数, 氨氮, 总磷, 总氮,
                            叶绿素α, 藻密度, 站点情况, raw_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            insert_data)
                        if cursor.rowcount > 0:
                            success_count += 1
                        else:
                            logger.debug(f"数据重复被忽略 - 时间+断面: {insert_data[3]} ({insert_data[2]})")  # 显示时间和断面名称
                    except Exception as e:
                        logger.error(f"数据校验/插入失败: {str(e)} | 数据: {json.dumps(item)}")
                
                # 批量提交
                conn.commit()
                logger.info(f"数据库写入完成，成功 {success_count}/{len(data)} 条")
                
        except sqlite3.Error as e:
            logger.error(f"数据库操作失败: {str(e)}")

    def _get_browser_context(self, playwright):
        """创建浏览器上下文并设置反爬措施"""
        logger.debug(f"_get_browser_context()")
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
        logger.debug(f"_select_region()")
        try:
            if self.TARGET_REGION == "全国":
                # 直接搜索空
                # 全国模式：清空搜索框并点击搜索按钮
                # 输入搜索前等待随机时间
                page.wait_for_timeout(random.uniform(500, 1500))
                # 清空搜索输入框
                search_input = page.locator("#txt_SeachName")
                search_input.fill("")

                # 点击前等待随机时间
                page.wait_for_timeout(random.uniform(500, 1000))
                
                # 点击搜索按钮
                search_btn = page.locator("button:has-text('搜索')")
                search_btn.click(timeout=WAIT_TIMEOUT)

                # 等待加载（优化后的智能等待）
                page.wait_for_timeout(random.uniform(30000, 40000))
                
                # 额外随机等待（1~3秒）
                page.wait_for_timeout(random.uniform(1000, 3000))
                logger.info("全国数据搜索成功")
            else:
                # 原有省份-城市选择逻辑
                page.click("#ddm_Area")
                page.wait_for_timeout(random.uniform(500, 1500))
                # 定位省份元素
                # 使用组合选择器定位唯一元素
                region_locator = page.locator(
                    f"ul.dropdown-menu >> li.dropdown-submenu >> a.area-item:has-text('{self.TARGET_REGION}')"
                )
                # 增加可见性断言
                expect(region_locator).to_be_visible(timeout=WAIT_TIMEOUT)
                logger.debug(f"定位到省份：{self.TARGET_REGION}")

                if not self.TARGET_CITY:
                    # 如果城市为空，直接点击省份
                    region_locator.click(timeout=WAIT_TIMEOUT)
                    page.wait_for_timeout(random.uniform(500, 1500))
                    logger.info(f"区域选择成功：{self.TARGET_REGION}")
                else:
                    # 模拟人类操作：悬停并选择城市
                    region_locator.hover(timeout=WAIT_TIMEOUT)
                    page.wait_for_timeout(random.uniform(1000, 2000))
                    
                    # 等待城市选项可见并点击
                    city_locator = page.locator(f"text={self.TARGET_CITY}")
                    expect(city_locator).to_be_visible(timeout=WAIT_TIMEOUT)
                    page.wait_for_timeout(random.uniform(500, 1500))
                    city_locator.click()
                    page.wait_for_timeout(random.uniform(500, 1500))
                    logger.info(f"区域选择成功：{self.TARGET_REGION} -> {self.TARGET_CITY}")
                
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
            "断面名称": row.query_selector("td.MN span span"), 
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

        parsed_data = {}
        for key, element in cells.items():
            try:
                display_value = element.inner_text().strip() if element else None
                raw_value = element.get_attribute("data-original-title") if element else None
                # 特殊处理监测时间，添加年
                if key == "监测时间":
                    display_value = self._complete_year(display_value)
                    if raw_value and "原始值" in raw_value:  # 如果原始值也需要处理
                        raw_value = self._complete_year(raw_value.split("：")[-1].strip())
                
                if key == "断面名称":
                    parsed_data[key] = {"显示值": display_value, "原始值": raw_value}
                    parts = raw_value.split("\n")  # 按换行分割文本
                    # 解析所在地市
                    if len(parts) >= 1:
                        city_parts = parts[0].split(":")
                        city = city_parts[1].strip() if len(city_parts) > 1 else ""  # 取冒号后内容
                        parsed_data["所在地市"] = {"显示值": city, "原始值": None}
                    # 解析所属河流
                    if len(parts) >= 2:
                        river_parts = parts[1].split(":")
                        river = river_parts[1].strip() if len(river_parts) > 1 else ""
                        parsed_data["所属河流"] = {"显示值": river, "原始值": None}
                
                if raw_value and "原始值" in raw_value:
                    raw_value = raw_value.split("：")[-1].strip()
                parsed_data[key] = {"显示值": display_value, "原始值": raw_value}
            except Exception as e:
                logger.warning(f"解析字段 {key} 失败: {str(e)}")
                parsed_data[key] = {"显示值": None, "原始值": None}
        return parsed_data

    def _scrape_data(self, page) -> List[Dict]:
        """抓取并解析数据"""
        logger.debug(f"_scrape_data()")
        try:
            # 主等待（确保元素存在）
            page.wait_for_selector("#gridDatas li.news-item", timeout=WAIT_TIMEOUT)
            
            # 人类化滚动
            for _ in range(random.randint(2,4)):
                page.mouse.wheel(0, random.randint(50, 150))
                page.wait_for_timeout(random.uniform(800, 2500))  # 0.8-2.5秒

            # 自适应等待
            loaded_count = len(page.query_selector_all("#gridDatas li.news-item"))
            base_wait = loaded_count * 500  # 每项基准500ms
            adaptive_wait = random.uniform(
                max(base_wait*0.5, 10000),  # 下限10秒
                min(base_wait*1.5, 40000)   # 上限40秒
            )
            page.wait_for_timeout(adaptive_wait)
            
            data_rows = page.query_selector_all("#gridDatas li.news-item")

            if not data_rows:
                logger.error("数据加载失败：未找到任何数据记录")
                raise ValueError("数据记录为空")  # 新增：抛出异常

            logger.info(f"发现 {len(data_rows)} 条数据记录")
            logger.info(f"解析数据.....................")
            
            water_data = []
            logger.debug(f"_parse_row()")
            for row in data_rows:
                water_data.append(self._parse_row(row))
            return water_data
        except TimeoutError as e:
            logger.warning("数据加载超时")
            raise e  # 修改：重新抛出异常，而非仅记录日志
        except Exception as e:
            logger.error("数据解析失败", exc_info=True)
            raise e  # 确保所有异常被抛出

    def _save_data(self, data: List[Dict]):
        """保存数据到文件"""
        logger.debug(f"_save_data()")
        if not data:
            logger.warning("未获取到有效数据，跳过保存")
            raise ValueError("有效数据为空")  # 新增：抛出异常
        
        ### 保存到数据库
        self._save_to_db(data,self.TARGET_REGION)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            # CSV保存
            csv_path = self.data_dir / f"water_quality_{timestamp}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # 写入表头（根据字段顺序调整）
                headers = ["省份", "流域", "所在地市", "所属河流", "断面名称", "监测时间", "水质类别", 
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
                        item["省份"]["显示值"], item["流域"]["显示值"], 
                        item["所在地市"]["显示值"], item["所属河流"]["显示值"], item["断面名称"]["显示值"],
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
        """执行主流程（优化版本）"""
        logger.info(f"run()")
        logger.info(f"######## 爬虫启动，时间：{datetime.now()} ########")
        success = False  # 初始化成功标志

        for attempt in range(RETRY_TIMES):
            try:
                with sync_playwright() as playwright:
                    # 初始化浏览器和页面
                    browser, context = self._get_browser_context(playwright)
                    page = context.new_page()
                    
                    try:
                        # 访问页面
                        page.goto(BASE_URL, timeout=WAIT_TIMEOUT)
                        logger.info(f"成功访问页面：{BASE_URL}")
                        
                        # 区域选择
                        self._select_region(page)
                        
                        # 数据抓取（可能抛出异常）
                        water_data = self._scrape_data(page)
                        
                        # 保存数据（可能抛出异常）
                        self._save_data(water_data)
                        
                        success = True  # 标记为成功
                        logger.info("数据抓取成功！")
                        break  # 成功则跳出重试循环

                    except Exception as inner_e:
                        logger.error(f"第 {attempt+1} 次尝试失败，错误类型：{type(inner_e).__name__}，错误信息：{str(inner_e)}")
                        raise  # 重新抛出异常以触发外层重试

                    finally:
                        # 确保每次运行后关闭浏览器
                        browser.close()
                        logger.info(f"第 {attempt+1} 次运行结束，浏览器已关闭")

            except Exception as outer_e:
                logger.error(f"第 {attempt+1} 次尝试失败，错误类型：{type(outer_e).__name__}，错误信息：{str(outer_e)}")
                if attempt < RETRY_TIMES - 1:
                    wait_time = (2 ** attempt) * 10  # 指数退避
                    logger.warning(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)

        # 最终状态处理
        if success:
            logger.info("######## 任务执行成功 ########")
        else:
            logger.critical(f"######## 连续 {RETRY_TIMES} 次尝试失败，任务终止！########")
        
        return success  # 返回实际成功状态

if __name__ == "__main__":
    monitor = WaterQualityMonitor()
    try:
        result = monitor.run()
        if result:
            logger.info("数据抓取任务执行成功")
        else:
            logger.error("数据抓取任务执行失败")
    except Exception as e:
        logger.critical(f"程序发生未捕获的异常：{str(e)}", exc_info=True)
        sys.exit(1)  # 非零退出码表示异常终止
