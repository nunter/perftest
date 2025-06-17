#!/bin/bash
##############################################################################
# Name        : update_reportdiff.sh
# Description : 更新 reportdiff 应用，添加 JMeter 测试运行器功能
# Author      : 醉逍遥
# Version     : 1.0
##############################################################################

# 设置颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}===== JMeter测试运行器集成更新脚本 =====${NC}"

# 检查工作目录
if [ ! -d "reportdiff" ]; then
    echo -e "${RED}错误: 'reportdiff' 目录不存在，请在正确的目录下运行此脚本${NC}"
    exit 1
fi

# 更新需求文件
echo -e "${GREEN}更新依赖项...${NC}"
if [ -f "reportdiff/requirements.txt" ]; then
    if ! grep -q "requests" "reportdiff/requirements.txt"; then
        echo "requests==2.31.0" >> reportdiff/requirements.txt
        echo -e "${GREEN}添加了 requests 依赖${NC}"
    else
        echo -e "${YELLOW}requests 依赖已存在${NC}"
    fi
else
    echo -e "${RED}错误: 找不到 reportdiff/requirements.txt 文件${NC}"
    exit 1
fi

# 创建 JMeter 测试运行器模块
echo -e "${GREEN}创建 JMeter 测试运行器模块...${NC}"
mkdir -p reportdiff/analysis/web_report/templates

# 备份原始 app.py
if [ -f "reportdiff/analysis/web_report/app.py" ]; then
    echo -e "${GREEN}备份原始 app.py 文件...${NC}"
    cp reportdiff/analysis/web_report/app.py reportdiff/analysis/web_report/app.py.bak
fi

# 复制新文件
echo -e "${GREEN}复制 JMeter 测试运行器文件...${NC}"
cp reportdiff/analysis/web_report/app_updated.py reportdiff/analysis/web_report/app.py

# 创建需要的目录
echo -e "${GREEN}创建必要的目录...${NC}"
mkdir -p testplan jtl log report/html

echo -e "${YELLOW}更新完成！${NC}"
echo -e "${YELLOW}请重启 reportdiff 服务以使更改生效${NC}"
echo -e "${YELLOW}  docker restart jmeter-report-diff${NC}"
echo -e "${YELLOW}或${NC}"
echo -e "${YELLOW}  ./reportdiff/deploy.sh${NC}"
echo -e "\n${GREEN}访问 http://localhost:5001/test-runner 使用 JMeter 测试运行器${NC}" 