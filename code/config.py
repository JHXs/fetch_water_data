# config.py
from pathlib import Path

# 网络配置
BASE_URL = "https://szzdjc.cnemc.cn:8070/GJZ/Business/Publish/RealDatas.html"
WAIT_TIMEOUT = 30000  # 30秒（单位：毫秒）
RETRY_TIMES = 3

# 获取当前脚本所在目录（假设脚本在 code/ 下）
SCRIPT_DIR = Path(__file__).parent
# 项目根目录（code 的父目录）
PROJECT_ROOT = SCRIPT_DIR.parent

# 存储配置
# DATA_DIR = Path("../data")
# DATA_BASE_DIR = Path("../data_base")
DATA_DIR = PROJECT_ROOT / "data"
DATA_BASE_DIR = PROJECT_ROOT / "data_base"
LOG_DIR = PROJECT_ROOT / "logs"

# 目标区域配置（当单独运行时生效）
DEFAULT_REGION = "广西壮族自治区"
DEFAULT_CITY = ""

# ## 使用少数几个省份
# PROVINCES = [
#     "广东省", "广西壮族自治区", "海南省"
# ]

## 省份列表（用于全国爬取）
PROVINCES = [
    "广西壮族自治区",
    "广东省", 
    "海南省", 
    "北京市",
    "天津市", 
    "河北省", 
    "山西省", 
    "内蒙古自治区",
    "辽宁省", 
    "吉林省", 
    "黑龙江省", 
    "上海市", 
    "江苏省",
    "浙江省", 
    "安徽省", 
    "福建省", 
    "江西省", 
    "山东省",
    "河南省", 
    "湖北省", 
    "湖南省", 
    "重庆市", 
    "四川省", 
    "贵州省", 
    "云南省",
    "西藏自治区", 
    "陕西省", 
    "甘肃省", 
    "青海省", 
    "宁夏回族自治区",
    "新疆维吾尔自治区"
]

PROVINCE_MAPPING = {
    # 直辖市
    "北京市": "beijing",
    "天津市": "tianjin",
    "上海市": "shanghai",
    "重庆市": "chongqing",
    
    # 自治区
    "内蒙古自治区": "neimenggu",
    "广西壮族自治区": "guangxi",
    "西藏自治区": "xizang",
    "宁夏回族自治区": "ningxia",
    "新疆维吾尔自治区": "xinjiang",
    
    # 省份（去掉"省"字）
    "河北省": "hebei",
    "山西省": "shanxi",
    "辽宁省": "liaoning",
    "吉林省": "jilin",
    "黑龙江省": "heilongjiang",
    "江苏省": "jiangsu",
    "浙江省": "zhejiang",
    "安徽省": "anhui",
    "福建省": "fujian",
    "江西省": "jiangxi",
    "山东省": "shandong",
    "河南省": "henan",
    "湖北省": "hubei",
    "湖南省": "hunan",
    "广东省": "guangdong",
    "海南省": "hainan",
    "四川省": "sichuan",
    "贵州省": "guizhou",
    "云南省": "yunnan",
    "陕西省": "shanxi1",  # 山西和陕西拼音冲突，添加数字区分
    "甘肃省": "gansu",
    "青海省": "qinghai"
}
