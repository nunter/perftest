#!/bin/bash
##############################################################################
# Name        : run_testing.sh
# Description : 一键执行性能脚本并保存报告，支持可选参数，并实时输出日志
# Author      : 醉逍遥
# Version     : 1.4
##############################################################################
# 使用方法：
#  ./run_test.sh [-f JMX文件名] [-n 并发用户数] [-t 压测时间(秒)] [-b 后台运行]
#
# 示例：
#  ./run_test.sh -f xiaocao -n 100 -t 300            # 前台运行，实时查看日志
#  ./run_test.sh -f xiaocao -n 100 -t 300 -b         # 后台运行，日志写入文件
##############################################################################

# 后台运行标志
BACKGROUND_MODE=false
# 后台日志文件
BACKGROUND_LOG="./run_test_background.log"

# --------------------- 日志函数定义 ---------------------
# 日志级别定义
LOG_LEVEL_DEBUG=0
LOG_LEVEL_INFO=1
LOG_LEVEL_WARN=2
LOG_LEVEL_ERROR=3

# 设置当前日志级别（可通过环境变量覆盖）
CURRENT_LOG_LEVEL=${LOG_LEVEL:-$LOG_LEVEL_INFO}

# 日志输出函数
log_debug() {
    if [ $CURRENT_LOG_LEVEL -le $LOG_LEVEL_DEBUG ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $*"
    fi
}

log_info() {
    if [ $CURRENT_LOG_LEVEL -le $LOG_LEVEL_INFO ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
    fi
}

log_warn() {
    if [ $CURRENT_LOG_LEVEL -le $LOG_LEVEL_WARN ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*"
    fi
}

log_error() {
    if [ $CURRENT_LOG_LEVEL -le $LOG_LEVEL_ERROR ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
    fi
}

# --------------------- 参数解析部分 ---------------------
# 默认 JMX 文件名
JMX_FILE="xiaocao"

# 默认并发用户数
THREAD_NUM=100
# 默认负载时间（秒）
TIM=30

# 解析命令行参数
while getopts "f:n:t:b" opt; do
    case $opt in
        f)
            JMX_FILE=$OPTARG
            ;;
        n)
            THREAD_NUM=$OPTARG
            ;;
        t)
            TIM=$OPTARG
            ;;
        b)
            BACKGROUND_MODE=true
            ;;
        \?)
            log_error "无效的选项: -$OPTARG"
            echo "用法: $0 [-f JMX文件名] [-n 并发用户数] [-t 压测时间(秒)] [-b 后台运行]"
            echo "  -f: JMX文件名，默认为 ${JMX_FILE}"
            echo "  -n: 并发用户数，默认为 ${THREAD_NUM}"
            echo "  -t: 压测时间(秒)，默认为 ${TIM}"
            echo "  -b: 后台运行模式，日志将写入 ${BACKGROUND_LOG}"
            exit 1
            ;;
    esac
done

# 参数验证
if ! [[ "$THREAD_NUM" =~ ^[0-9]+$ ]]; then
    log_error "并发用户数必须是正整数"
    exit 1
fi

if ! [[ "$TIM" =~ ^[0-9]+$ ]]; then
    log_error "压测时间必须是正整数"
    exit 1
fi

log_info "设置并发用户数：${THREAD_NUM}"
log_info "设置压测时间：${TIM}秒"
log_info "使用 JMX 文件：${JMX_FILE}.jmx"

# 启动后台运行模式
run_in_background() {
    log_info "启动后台运行模式，日志将写入: ${BACKGROUND_LOG}"
    # 移除-b参数，防止无限循环
    ARGS=""
    for arg in "$@"; do
        if [ "$arg" != "-b" ]; then
            ARGS="${ARGS} ${arg}"
        fi
    done
    nohup "$0" ${ARGS} > "${BACKGROUND_LOG}" 2>&1 &
    echo "进程已在后台启动 (PID: $!)，日志文件: ${BACKGROUND_LOG}"
    echo "可以使用命令查看进度: tail -f ${BACKGROUND_LOG}"
    exit 0
}

# 检查是否启用后台运行模式
if [ "$BACKGROUND_MODE" = true ]; then
    run_in_background "$@"
fi

# 默认远程服务器列表（用逗号分隔的IP地址）
REMOTE_SERVERS="192.168.1.36,192.168.89.176"

# 测试报告URL的基础地址
REPORT_URL="http://192.168.89.157:5001"
# 企业微信机器人webhook地址
WECHAT_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=95bd68a8-d01d-4c82-b4d4-e08e41293ec7"

# 发送企业微信机器人消息
send_wechat_message() {
    local message="$1"
    # 对消息内容进行JSON转义
    message=$(echo "$message" | sed 's/"/\\"/g')
    curl -s -H "Content-Type: application/json" -X POST -d "{\"msgtype\":\"markdown\",\"markdown\":{\"content\":\"$message\"}}" "${WECHAT_WEBHOOK}"
}


# --------------------- 基础路径设置 ---------------------
# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 设置 JMeter 相关目录
JMETER_HOME="${SCRIPT_DIR}/apache-jmeter"  # JMeter 主目录
JMETER_BIN="${JMETER_HOME}/bin"          # JMeter bin 目录

# 其他目录设置                   # 源目录
JMX_DIR="${SCRIPT_DIR}/testplan"              # 存放 JMX 文件的目录
HTML_DIR="${SCRIPT_DIR}/report/html"            # HTML 报告目录
JTL_DIR="${SCRIPT_DIR}/jtl"              # jtl 文件存放目录
LOG_DIR="${SCRIPT_DIR}/log"              # JMeter 日志存放目录
LOCAL_LOG="jmeter.log"                   # 当前脚本输出的日志文件

# --------------------- 检查远程JMeter Server状态 ---------------------
log_info "开始检查远程JMeter Server状态..."
IFS=',' read -ra SERVERS <<< "${REMOTE_SERVERS}"
for server in "${SERVERS[@]}"; do
    log_info "检查 ${server} 的JMeter Server状态..."
    if ! nc -z -w5 "${server}" 1099 >/dev/null 2>&1; then
        log_error "${server} 的JMeter Server未启动或无法连接"
        exit 1
    fi
    log_info "${server} 的JMeter Server运行正常"
done
log_info "所有远程JMeter Slave Server状态检查完成"

# 目标文件路径
TARGET_JMX="${JMX_DIR}/${JMX_FILE}"
log_debug "JMX文件路径：${TARGET_JMX}"

# 计算实际并发用户数（THREAD_NUM * 服务器数量）
IFS=',' read -ra SERVERS <<< "${REMOTE_SERVERS}"
SERVER_COUNT=${#SERVERS[@]}
ACTUAL_THREAD_NUM=$((THREAD_NUM * SERVER_COUNT))
log_info "实际总并发用户数: ${ACTUAL_THREAD_NUM} (${THREAD_NUM} * ${SERVER_COUNT}台服务器)"

# 定义测试名称作为单独参数
TEST_NAME="${JMX_FILE}-${ACTUAL_THREAD_NUM}Vuser"
log_info "测试名称: ${TEST_NAME}"

# --------------------- 2. 创建以时间和并发用户数命名的目录 ---------------------
DATE_DIR=$(date +'%Y%m%d%H%M%S')
REPORT_DIR="${HTML_DIR}/${TEST_NAME}_${DATE_DIR}"
log_info "创建报告目录：${REPORT_DIR}"
if ! mkdir -p "${REPORT_DIR}"; then
    log_error "创建报告目录失败：${REPORT_DIR}"
    exit 1
fi
log_debug "报告目录创建成功"

# --------------------- 3. 启动 JMeter 压测（实时输出日志） ---------------------
log_info "准备执行性能脚本..."
# 构建JMeter命令基础部分
JMETER_CMD=("${JMETER_BIN}/jmeter" "-n" "-t" "${TARGET_JMX}.jmx" "-Gusers=${THREAD_NUM}" "-Ghold_time=${TIM}" "-Gserver.rmi.ssl.disable=true")

# 添加远程服务器配置
if [ -n "${REMOTE_SERVERS}" ]; then
    log_info "使用分布式模式，远程服务器列表: ${REMOTE_SERVERS}"
    JMETER_CMD+=("-R" "${REMOTE_SERVERS}")
    
    # 检查远程服务器是否可用
    IFS=',' read -ra SERVERS <<< "${REMOTE_SERVERS}"
    for server in "${SERVERS[@]}"; do
        log_debug "检查远程服务器连接性: ${server}:1099"
        if ! nc -z -w5 "${server}" 1099 >/dev/null 2>&1; then
            log_error "无法连接到远程服务器 ${server}:1099，请检查网络连接和JMeter Server状态"
            exit 1
        fi
        log_debug "远程服务器 ${server}:1099 连接正常"
    done
fi

# 添加其他参数
JTL_FILE="${JTL_DIR}/report-${ACTUAL_THREAD_NUM}_${DATE_DIR}.jtl"
JMETER_LOG="${LOG_DIR}/report-${ACTUAL_THREAD_NUM}_${DATE_DIR}.log"
JMETER_CMD+=("-l" "${JTL_FILE}" "-e" "-o" "${REPORT_DIR}" "-j" "${JMETER_LOG}")

# 打印完整的JMeter命令
log_info "执行的完整命令：${JMETER_CMD[*]}"
TEST_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
log_info "压测开始时间：${TEST_START_TIME}"

# 执行JMeter命令并实时显示日志
"${JMETER_CMD[@]}" > "${LOCAL_LOG}" 2>&1 &
JMETER_PID=$!

# 等待3秒钟让JMeter完全启动
sleep 3

# 使用tail命令实时显示日志
tail -f "${JMETER_LOG}" & 
TAIL_PID=$!

# 等待JMeter进程完成
wait ${JMETER_PID}
EXIT_CODE=$?

# 确保正确终止tail进程
if [ -n "${TAIL_PID}" ]; then
    kill ${TAIL_PID} 2>/dev/null
    wait ${TAIL_PID} 2>/dev/null
fi

# 等待jtl文件数据回传完成
log_info "等待slave数据回传完成..."
PREV_SIZE=0
STABLE_COUNT=0
while true; do
    if [ -f "${JTL_FILE}" ]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            CURRENT_SIZE=$(stat -f %z "${JTL_FILE}" 2>/dev/null)
        else
            CURRENT_SIZE=$(stat -c %s "${JTL_FILE}" 2>/dev/null)
        fi
        if [ -z "${CURRENT_SIZE}" ]; then
            log_warn "无法获取文件大小，可能文件尚未创建"
            CURRENT_SIZE=0
        fi
        if [ "${CURRENT_SIZE}" = "${PREV_SIZE}" ]; then
            STABLE_COUNT=$((STABLE_COUNT + 1))
            if [ ${STABLE_COUNT} -ge 3 ]; then
                log_info "数据回传完成，文件大小: ${CURRENT_SIZE} 字节"
                break
            fi
        else
            STABLE_COUNT=0
        fi
        PREV_SIZE=${CURRENT_SIZE}
    fi
    sleep 2
done

# 检查执行结果
if [ ${EXIT_CODE} -eq 0 ]; then
    log_info "分布式压测完成！"
    log_info "压测结束时间：$(date '+%Y-%m-%d %H:%M:%S')"
    log_info "并发用户数：${THREAD_NUM}"
    log_info "压测持续时间：${TIM}秒"
    log_info "测试报告位置：${REPORT_URL}/report/html/${TEST_NAME}_${DATE_DIR}"
    log_info "测试结果文件：${REPORT_URL}/report/html/${TEST_NAME}_${DATE_DIR}/statistics.json"
    log_info "所有步骤执行完毕！"
    
    # 计算实际压测持续时长
    START_TIME=$(date -d "${TEST_START_TIME}" +%s)
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    # 发送企业微信通知
    WECHAT_MESSAGE="### ${TEST_NAME} 分布式压测报告\n\n"
    WECHAT_MESSAGE+="- 服务器状态：<font color=\"info\">所有slave服务器正常</font>\n"
    WECHAT_MESSAGE+="- 压测状态：<font color=\"info\">分布式压测成功完成</font>\n"
    WECHAT_MESSAGE+="- 实际总并发用户数：${ACTUAL_THREAD_NUM}\n"
    WECHAT_MESSAGE+="- 压测开始时间：${TEST_START_TIME}\n"
    WECHAT_MESSAGE+="- 压测结束时间：$(date '+%Y-%m-%d %H:%M:%S')\n"
    DURATION_MIN=$((DURATION / 60))
    DURATION_SEC=$((DURATION % 60))
    WECHAT_MESSAGE+="- 压测持续时长：${DURATION_MIN}分钟${DURATION_SEC}秒\n"
    WECHAT_MESSAGE+="- 本次压测报告：[点击查看](${REPORT_URL}/report/html/${TEST_NAME}_${DATE_DIR}/index.html)\n"
    WECHAT_MESSAGE+="- 查看所有报告：[报告列表](${REPORT_URL})\n"
    
    send_wechat_message "${WECHAT_MESSAGE}"
    log_info "企业微信通知已发送"
else
    log_error "JMeter 执行失败，退出码：${EXIT_CODE}"
    log_error "请检查日志文件：${JMETER_LOG}"
    exit ${EXIT_CODE}
fi