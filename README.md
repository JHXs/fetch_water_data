# 水质监测数据发布网站爬虫脚本

## 使用步骤
- 安装依赖包：`fake-useragent`、 `playwright`；
- 在脚本配置常量那里设置好常量；
- 直接在终端输入命令 `py water_monitor.py` 运行脚本即可看到 `data` 目录生成了数据。

## 自动化运行
使用系统级调度（推荐）：
输入 `crontab -e` ，添加如下命令。

```bash
# 每天每小时执行一次
0 * * * * /usr/bin/python3 /path/to/fetch_water_data.py
```
