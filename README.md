# 水质监测数据发布网站爬虫脚本

## 使用步骤
- 安装依赖包：`fake-useragent`、 `playwright`；
- 在脚本配置常量那里设置好常量；
- 直接在终端输入命令 `py water_monitor.py` 运行脚本即可看到 `data` 目录生成了数据。

## 自动化运行
使用系统级调度（推荐）：
输入 `crontab -e` ，添加如下命令。

```bash
# 每天每4小时执行一次，# 每4小时的15分钟运行（例如 0:15, 4:15, 8:15, 12:15, 16:15, 20:15）
15 */4 * * * /home/hansel/ssd/test-water-data/.venv/bin/python /home/hansel/ssd/test-water-data/water_monitor.py
```

## 数据库的使用
1. 数据库维护：

```bash
# 定期执行数据库优化
sqlite3 water_quality.db "VACUUM; REINDEX;"
```

2. 查询示例：

```bash
# 1. 进入项目目录（根据你的实际路径调整）
cd ~/ssd/test-water-data

# 2. 连接数据库（假设你的数据库文件是 water_quality.db）
sqlite3 data/water_quality.db

# 3. 执行 SQL 查询
.header on       # 显示列名
.mode column    # 列式显示
SELECT * FROM water_data LIMIT 3;

# 4. 检查监测时间字段（示例输出）
/*
监测时间          省份                断面名称    水温(pH)...
---------------  ------------------  ----------  --------
2025-03-27 16:00 广西壮族自治区       阳朔        22.7
2025-03-27 16:00 广西壮族自治区       水库出水口   21.7
2025-03-27 16:00 广西壮族自治区       交州        19.6
*/

# 5. 退出
.quit
```

```SQL
-- 查询最新10条桂林市数据
SELECT 断面名称, 监测时间, 水质类别, pH, 溶解氧 
FROM water_data
WHERE 省份 = '广西壮族自治区' 
  AND 断面名称 LIKE '桂林%'
ORDER BY 监测时间 DESC
LIMIT 10;
```
