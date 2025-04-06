import sqlite3
import csv
import os

# 确保输出目录存在
os.makedirs('data/sqlite2csv', exist_ok=True)

# 连接数据库
conn = sqlite3.connect('data_base/water_quality.db')
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
    with open('data/sqlite2csv/output.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(column_names)  # 写入列标题
        writer.writerows(rows)         # 写入数据行

finally:
    # 确保连接关闭
    conn.close()