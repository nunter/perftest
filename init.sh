#!/bin/bash

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 切换到项目根目录
cd "$SCRIPT_DIR"

# 创建必要的目录结构
directories=(
    "apache-jmeter/backups"
    "file"
    "jtl"
    "log"
    "report"
    "report/html"
    "reportdiff/analysis/web_report/uploads"
    "reportdiff/analysis/web_report/web_report"
    "reportdiff/analysis/web_report/templates"
    "reportdiff/uploads"
    "testplan"
    "uploads"
)

echo "开始创建目录结构..."

for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "创建目录: $dir"
    else
        echo "目录已存在: $dir"
    fi
done

echo "目录结构创建完成！"

# 设置执行权限
chmod +x "$SCRIPT_DIR/init.sh"