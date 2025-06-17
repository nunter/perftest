# -*- coding: utf-8 -*-
# 性能测试平台配置文件

import os
from pathlib import Path

# 基础目录配置
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
JMETER_HOME = BASE_DIR / "apache-jmeter"
JMETER_BIN = JMETER_HOME / "bin"
JMX_DIR = BASE_DIR / "testplan"
HTML_DIR = BASE_DIR / "report" / "html"
JTL_DIR = BASE_DIR / "jtl"
LOG_DIR = BASE_DIR / "log"

# 远程服务器配置
REMOTE_SERVERS = "192.168.89.158,192.168.89.176"
REPORT_URL = "http://192.168.89.157:5001"

# 微信机器人配置
# 不同脚本对应的微信webhook地址
WECHAT_WEBHOOKS = {
    # 默认webhook地址
    "default": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=95bd68a8-d01d-4c82-b4d4-e08e41293ec7",
    # 小草脚本专用webhook地址 - 根据要求使用特定地址
    "小草": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=49a8a698-78e0-4d8b-bffc-4b6299a9b6c5",
    # YHD脚本专用webhook地址
    "壹合道": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=21555eb4-3427-47c1-851e-6684bdd1bfe1",
}

# 是否发送微信通知
SEND_WECHAT_NOTIFICATIONS = True  # True表示发送, False表示不发送

# 日志级别配置
LOG_LEVEL_DEBUG = 0
LOG_LEVEL_INFO = 1
LOG_LEVEL_WARN = 2
LOG_LEVEL_ERROR = 3
CURRENT_LOG_LEVEL = int(os.environ.get('LOG_LEVEL', LOG_LEVEL_INFO))

# 创建必要的目录
def create_required_directories():
    """创建必要的目录结构"""
    for directory in [JMX_DIR, HTML_DIR, JTL_DIR, LOG_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # 确保web报告目录存在
    os.makedirs(BASE_DIR / 'reportdiff' / 'analysis' / 'web_report', exist_ok=True)

# 获取脚本对应的微信webhook地址
def get_wechat_webhook(script_name):
    """根据脚本名称获取对应的微信webhook地址"""
    # 如果提供了脚本名称且在配置中存在，则返回对应的webhook地址
    if script_name and script_name in WECHAT_WEBHOOKS:
        return WECHAT_WEBHOOKS[script_name]
    # 否则返回默认webhook地址
    return WECHAT_WEBHOOKS["default"]