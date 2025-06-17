import os
import time
import json
import socket
import subprocess
from datetime import datetime
from pathlib import Path
import threading
import queue
import sys
import traceback

from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_from_directory

# 导入配置文件
from config import (
    SEND_WECHAT_NOTIFICATIONS,  # 添加此行
    BASE_DIR, JMETER_HOME, JMETER_BIN, JMX_DIR, HTML_DIR, JTL_DIR, LOG_DIR,
    REMOTE_SERVERS, REPORT_URL, get_wechat_webhook,
    LOG_LEVEL_DEBUG, LOG_LEVEL_INFO, LOG_LEVEL_WARN, LOG_LEVEL_ERROR, CURRENT_LOG_LEVEL,
    create_required_directories
)

# 创建必要的目录
create_required_directories()

app = Flask(__name__)

# Import performance analysis module
sys.path.append(str(BASE_DIR / "reportdiff" / "analysis"))
try:
    from performance_analysis import generate_comparison_report
except ImportError:
    print("Warning: Could not import performance_analysis module, comparison functionality may not work.")

# Create directories if they don't exist
for directory in [JMX_DIR, HTML_DIR, JTL_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Ensure the web report directory exists
os.makedirs(BASE_DIR / 'reportdiff' / 'analysis' / 'web_report', exist_ok=True)

# Log levels
LOG_LEVEL_DEBUG = 0
LOG_LEVEL_INFO = 1
LOG_LEVEL_WARN = 2
LOG_LEVEL_ERROR = 3
CURRENT_LOG_LEVEL = int(os.environ.get('LOG_LEVEL', LOG_LEVEL_INFO))

# Global test process and log queue
active_test = None
log_queue = queue.Queue()

def log_message(level, message):
    """Add a log message to the queue with timestamp and level"""
    if level >= CURRENT_LOG_LEVEL:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        level_name = {
            LOG_LEVEL_DEBUG: "DEBUG",
            LOG_LEVEL_INFO: "INFO",
            LOG_LEVEL_WARN: "WARN",
            LOG_LEVEL_ERROR: "ERROR"
        }.get(level, "INFO")
        
        log_entry = f"[{timestamp}] [{level_name}] {message}"
        log_queue.put(log_entry)
        print(log_entry)  # Also print to console for debugging
        return log_entry
    return None

def log_debug(message):
    return log_message(LOG_LEVEL_DEBUG, message)

def log_info(message):
    return log_message(LOG_LEVEL_INFO, message)

def log_warn(message):
    return log_message(LOG_LEVEL_WARN, message)

def log_error(message):
    return log_message(LOG_LEVEL_ERROR, message)

def check_jmeter_servers(servers):
    """Check if JMeter servers are running"""
    log_info("Starting to check remote JMeter Server status...")
    server_list = servers.split(',')
    for server in server_list:
        log_info(f"Checking JMeter Server status on {server}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((server, 1099))
            sock.close()
            if result != 0:
                log_error(f"JMeter Server on {server} is not running or cannot be connected")
                return False
            log_info(f"JMeter Server on {server} is running normally")
        except Exception as e:
            log_error(f"Error checking JMeter Server on {server}: {str(e)}")
            return False
    
    log_info("All remote JMeter Slave Server status checks completed")
    return True

def send_wechat_message(message, script_name=None):
    """Send a message to WeChat robot
    
    Args:
        message: 要发送的消息内容
        script_name: 脚本名称，用于确定使用哪个webhook地址
    """
    # 检查是否需要发送微信通知
    if not SEND_WECHAT_NOTIFICATIONS:
        log_debug("微信通知功能已关闭，不发送消息。")
        return True # 或者 False，根据实际需求决定返回值

    try:
        import requests
        import json
        
        # 根据脚本名称获取对应的webhook地址
        webhook_url = get_wechat_webhook(script_name)
        
        # 记录发送内容以便调试
        log_debug(f"WeChat message content: {message}")
        log_debug(f"Using webhook for script: {script_name if script_name else 'default'}")
        
        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": message
            }
        }
        
        # 记录JSON数据以便调试
        log_debug(f"WeChat request data: {json.dumps(data)}")
        
        response = requests.post(webhook_url, headers=headers, json=data)
        log_debug(f"WeChat notification response: {response.status_code}")
        log_debug(f"WeChat notification response content: {response.text}")
        
        return True
    except Exception as e:
        log_error(f"Failed to send WeChat notification: {str(e)}")
        return False

def run_jmeter_test(jmx_file, thread_num, test_duration, step_num=None, remote_servers=REMOTE_SERVERS):
    """Run a JMeter test with the given parameters"""
    global active_test
    
    # Log level is now globally controlled, not per test
        
    if not Path(f"{JMX_DIR}/{jmx_file}.jmx").exists():
        log_error(f"JMX file not found: {jmx_file}.jmx")
        return False
    
    # Check if remote servers are available
    if not check_jmeter_servers(remote_servers):
        return False
    
    # Calculate actual thread count
    server_count = len(remote_servers.split(','))
    threads_per_server = -(-thread_num // server_count)  # Ceiling division to round up
    actual_thread_num = threads_per_server * server_count
    
    # Create test name and report directory
    test_name = f"{jmx_file}-{actual_thread_num}Vuser"
    date_dir = datetime.now().strftime('%Y%m%d%H%M%S')
    report_dir = HTML_DIR / f"{test_name}_{date_dir}"
    
    try:
        os.makedirs(report_dir, exist_ok=True)
        log_info(f"Created report directory: {report_dir}")
    except Exception as e:
        log_error(f"Failed to create report directory: {str(e)}")
        return False
    
    # Construct JMeter command
    target_jmx = f"{JMX_DIR}/{jmx_file}.jmx"
    jtl_file = f"{JTL_DIR}/report-{actual_thread_num}_{date_dir}.jtl"
    jmeter_log = f"{LOG_DIR}/report-{actual_thread_num}_{date_dir}.log"
    
    cmd = [
        f"{JMETER_BIN}/jmeter",
        "-n",
        "-t", target_jmx,
        "-Gusers", str(threads_per_server),
        "-Ghold_time", str(test_duration),
        "-Gserver.rmi.ssl.disable=true",
        "-R", remote_servers,
        "-l", jtl_file,
        "-e",
        "-o", str(report_dir),
        "-j", jmeter_log
    ]

    if step_num is not None:
        cmd.extend([
            "-Gstepnum", str(step_num)
        ])
    
    log_info(f"Executing command: {' '.join(cmd)}")
    test_start_time = datetime.now()
    log_info(f"Test start time: {test_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Start JMeter process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # 添加输出读取线程
    def read_output(process):
        for line in process.stdout:
            line = line.strip()
            if line:
                # Process JMeter output with appropriate log level
                if "ERROR" in line or "FATAL" in line:
                    log_error(f"JMeter: {line}")
                elif "WARN" in line:
                    log_warn(f"JMeter: {line}")
                elif "DEBUG" in line or "INFO" in line or CURRENT_LOG_LEVEL <= LOG_LEVEL_DEBUG:
                    # Always show DEBUG lines if in debug mode
                    log_debug(f"JMeter: {line}")
                else:
                    # Default to INFO for other lines
                    log_info(f"JMeter: {line}")
    
    # 启动读取输出的线程
    output_thread = threading.Thread(target=read_output, args=(process,))
    output_thread.daemon = True
    output_thread.start()
    
    active_test = {
        'process': process,
        'start_time': test_start_time,
        'jmx_file': jmx_file,
        'thread_num': thread_num,
        'actual_thread_num': actual_thread_num,
        'test_duration': test_duration,
        'test_name': test_name,
        'date_dir': date_dir,
        'jtl_file': jtl_file,
        'jmeter_log': jmeter_log,
        'report_dir': str(report_dir)
    }
    
    # Start a thread to monitor the process and tail the log
    monitor_thread = threading.Thread(
        target=monitor_jmeter_process,
        args=(process, jmeter_log, jtl_file, test_name, date_dir, test_start_time, actual_thread_num)
    )
    monitor_thread.daemon = True
    monitor_thread.start()
    
    return True

def validate_jtl_file(jtl_file):
    """验证JTL文件的完整性"""
    try:
        if not os.path.exists(jtl_file):
            return False, "文件不存在"
        
        file_size = os.path.getsize(jtl_file)
        if file_size == 0:
            return False, "文件大小为0"
        
        with open(jtl_file, 'r') as f:
            # 检查第一行（标题行）
            header = f.readline().strip()
            if not header or 'timeStamp' not in header:
                return False, "文件格式不正确，缺少timeStamp列"
            
            # 计算数据行数
            data_lines = sum(1 for _ in f)
            
            # 回到文件开头
            f.seek(0)
            
            # 检查最后一行是否包含完整数据
            lines = f.readlines()
            if lines and len(lines) > 1:
                last_line = lines[-1].strip()
                if not last_line or len(last_line.split(',')) < 5:  # 简单检查CSV格式是否完整
                    return False, "最后一行数据不完整"
            
            return True, f"文件验证通过，包含{data_lines}条数据记录"
            
    except Exception as e:
        return False, f"验证过程出错: {str(e)}"

def monitor_jmeter_process(process, log_file, jtl_file, test_name, date_dir, start_time, actual_thread_num):
    """Monitor JMeter process and handle completion"""
    global active_test
    
    # 创建诊断日志文件
    transfer_log_file = f"{LOG_DIR}/transfer_{test_name}_{date_dir}.log"
    try:
        with open(transfer_log_file, 'w') as tf:
            tf.write(f"JMeter数据回传诊断日志\n")
            tf.write(f"测试名称: {test_name}\n")
            tf.write(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            tf.write(f"JTL文件: {jtl_file}\n\n")
    except Exception as e:
        log_warn(f"无法创建数据回传诊断日志: {str(e)}")
    
    # 记录诊断信息的函数
    def write_transfer_log(message):
        try:
            with open(transfer_log_file, 'a') as tf:
                tf.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except:
            pass  # 忽略记录诊断日志的错误
    
    # Wait for process to complete
    exit_code = process.wait()
    log_info(f"JMeter process completed with exit code: {exit_code}")
    write_transfer_log(f"JMeter进程退出，退出码: {exit_code}")
    
    # Read the JMeter log file and output important lines
    if os.path.exists(log_file) and CURRENT_LOG_LEVEL <= LOG_LEVEL_DEBUG:
        try:
            log_debug(f"Reading JMeter log file: {log_file}")
            with open(log_file, 'r') as f:
                log_debug(f"===== JMeter Log File Contents ({log_file}) =====")
                for line in f:
                    line = line.strip()
                    if line:
                        # Filter only important or error-related lines
                        if "ERROR" in line or "FATAL" in line:
                            log_error(f"JMeter Log: {line}")
                        elif "WARN" in line:
                            log_warn(f"JMeter Log: {line}")
                        elif any(term in line for term in ["threads", "sample", "duration", "summary", "throughput"]):
                            # Log important performance-related lines
                            log_info(f"JMeter Log: {line}")
                log_debug(f"===== End of JMeter Log File =====")
        except Exception as e:
            log_warn(f"Could not read JMeter log file: {str(e)}")
    
    # Wait for JTL file to stabilize (data transfer completion)
    log_info("Waiting for slave data transfer to complete...")
    write_transfer_log("开始等待从节点数据回传...")
    
    prev_size = 0
    stable_count = 0
    wait_count = 0  # 添加等待计数
    max_wait = 60   # 最多等待60次，约120秒
    jtl_file_exists = False
    transfer_start_time = datetime.now()
    
    # JTL文件回传检测
    while True:
        try:
            if os.path.exists(jtl_file):
                jtl_file_exists = True
                current_size = os.path.getsize(jtl_file)
                log_info(f"JTL file size: {current_size} bytes (previous: {prev_size} bytes)")
                write_transfer_log(f"JTL文件大小: {current_size} 字节 (之前: {prev_size} 字节)")
                
                # 定期备份JTL文件
                if wait_count % 10 == 0 and current_size > 0:
                    try:
                        backup_file = f"{jtl_file}.{wait_count}.bak"
                        import shutil
                        shutil.copy2(jtl_file, backup_file)
                        write_transfer_log(f"创建JTL文件备份: {backup_file}")
                    except Exception as e:
                        write_transfer_log(f"创建JTL文件备份失败: {str(e)}")
                
                if current_size == prev_size:
                    stable_count += 1
                    log_info(f"JTL file size stable for {stable_count} checks")
                    write_transfer_log(f"JTL文件大小已稳定 {stable_count} 次检查")
                    
                    if stable_count >= 3:
                        log_info(f"Data transfer complete, final file size: {current_size} bytes")
                        write_transfer_log(f"数据回传完成，最终文件大小: {current_size} 字节")
                        
                        # 验证JTL文件完整性
                        is_valid, message = validate_jtl_file(jtl_file)
                        write_transfer_log(f"JTL文件验证: {message}")
                        
                        if is_valid:
                            log_info(f"JTL file validation: {message}")
                            # 通过所有检查，数据回传完成
                            break
                        else:
                            log_warn(f"JTL file validation failed: {message}")
                            write_transfer_log(f"警告: JTL文件验证失败: {message}")
                            
                            if wait_count < max_wait:
                                # 继续等待
                                stable_count = 0
                                wait_count += 1
                                time.sleep(2)
                                continue
                            else:
                                log_warn("Max wait time reached, proceeding with potentially incomplete JTL file")
                                write_transfer_log("已达到最大等待时间，将继续处理可能不完整的JTL文件")
                                break
                else:
                    # 文件大小变化，重置稳定计数
                    stable_count = 0
                    # 如果文件在增长，重置等待计数
                    if current_size > prev_size:
                        wait_count = 0
                        
                prev_size = current_size
            else:
                # JTL文件不存在
                wait_count += 1
                log_info(f"Waiting for JTL file to be created... ({wait_count}/{max_wait})")
                write_transfer_log(f"等待JTL文件创建... ({wait_count}/{max_wait})")
                
                if wait_count >= max_wait:
                    log_warn(f"JTL file {jtl_file} not found after {max_wait} attempts, giving up")
                    write_transfer_log(f"在{max_wait}次尝试后仍未找到JTL文件，放弃等待")
                    break
        except Exception as e:
            log_warn(f"Failed to get file size: {str(e)}")
            write_transfer_log(f"获取文件大小失败: {str(e)}")
            
            wait_count += 1
            if wait_count >= max_wait:
                log_warn(f"Failed to get file size after {max_wait} attempts, giving up")
                write_transfer_log(f"在{max_wait}次尝试后仍无法获取文件大小，放弃等待")
                break
        
        time.sleep(2)
    
    # 计算数据回传总时间
    transfer_end_time = datetime.now()
    transfer_duration = (transfer_end_time - transfer_start_time).total_seconds()
    log_info(f"Data transfer monitoring completed in {transfer_duration:.1f} seconds")
    write_transfer_log(f"数据回传监控完成，耗时 {transfer_duration:.1f} 秒")
    
    # JTL数据回传处理完毕，检查是否成功
    if not jtl_file_exists and exit_code == 0:
        log_warn("JMeter process completed successfully, but JTL file was not created")
        write_transfer_log("警告: JMeter进程成功完成，但未创建JTL文件")
        # 这种情况可能是JMeter配置问题，或者存储权限问题
    
    # Test completed
    end_time = datetime.now()
    duration_seconds = (end_time - start_time).total_seconds()
    duration_min = int(duration_seconds // 60)
    duration_sec = int(duration_seconds % 60)
    
    if exit_code == 0:
        log_info("Distributed load test completed!")
        log_info(f"Test end time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        log_info(f"Test report location: {REPORT_URL}/report/html/{test_name}_{date_dir}")
        log_info(f"Test result file: {REPORT_URL}/report/html/{test_name}_{date_dir}/statistics.json")
        log_info("All steps completed!")
        
        # 报告URL
        report_url = f"{REPORT_URL}/report/html/{test_name}_{date_dir}/index.html"
        report_list_url = f"{REPORT_URL}/report-list"
        
        # Send WeChat notification - 使用与run_test.sh相同的格式
        wechat_message = f"### {test_name} 分布式压测报告\n\n"
        wechat_message += "- 服务器状态：<font color=\"info\">所有slave服务器正常</font>\n"
        wechat_message += "- 压测状态：<font color=\"info\">分布式压测成功完成</font>\n"
        wechat_message += f"- 实际总并发用户数：{actual_thread_num}\n"
        wechat_message += f"- 压测开始时间：{start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        wechat_message += f"- 压测结束时间：{end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        wechat_message += f"- 压测持续时长：{duration_min}分钟{duration_sec}秒\n"
        wechat_message += f"- 本次压测报告：[点击查看]({report_url})\n"
        wechat_message += f"- 查看所有报告：[报告列表]({report_list_url})\n"
        
        # 从测试名称中提取脚本名称 for WeChat webhook routing
        # Default to 'default' if jmx_file is not found or is empty
        jmx_file_for_notification = active_test.get('jmx_file') if active_test else None
        script_name_for_notification = jmx_file_for_notification if jmx_file_for_notification else 'default'
        
        # 使用提取或默认的脚本名称发送微信通知
        send_wechat_message(wechat_message, script_name_for_notification)
        log_info(f"WeChat notification sent using webhook for script: {script_name_for_notification}")
    else:
        log_error(f"JMeter execution failed, exit code: {exit_code}")
        log_error(f"Please check log file: {log_file}")
        
        # 添加执行失败的JMeter日志分析
        try:
            if os.path.exists(log_file):
                # 读取JMeter日志文件的最后20行
                with open(log_file, 'r') as f:
                    log_lines = f.readlines()
                    last_lines = log_lines[-20:] if len(log_lines) > 20 else log_lines
                    log_error("JMeter log file last lines:")
                    for line in last_lines:
                        log_error(line.strip())
            else:
                log_error(f"JMeter log file not found: {log_file}")
                
            # 检查JMeter权限
            jmeter_path = f"{JMETER_BIN}/jmeter"
            if os.path.exists(jmeter_path):
                import stat
                jmeter_stat = os.stat(jmeter_path)
                is_executable = bool(jmeter_stat.st_mode & stat.S_IXUSR)
                log_error(f"JMeter executable permissions: {'Executable' if is_executable else 'Not executable'}")
                if not is_executable:
                    log_error("Please run: chmod +x " + jmeter_path)
        except Exception as e:
            log_error(f"Error analyzing JMeter failure: {str(e)}")
            
        # 发送失败通知 - 使用中文与run_test.sh保持一致
        wechat_message = f"### {test_name} 分布式压测失败\n\n"
        wechat_message += f"- 测试时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        wechat_message += f"- 失败原因: JMeter进程异常终止，退出码: {exit_code}\n"
        wechat_message += f"- 请检查日志文件: {log_file}\n"
        send_wechat_message(wechat_message)
    
    active_test = None

def tail_log_file(log_file):
    """Generator to tail a log file and yield new lines"""
    try:
        with open(log_file, 'r') as f:
            # Move to the end of file
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    yield line
                else:
                    time.sleep(0.1)
    except Exception as e:
        yield f"Error tailing log file: {str(e)}"

@app.route('/')
def index():
    """Render the main page"""
    # Get list of available JMX files
    jmx_files = []
    for file in os.listdir(JMX_DIR):
        if file.endswith('.jmx'):
            jmx_files.append(file[:-4])  # Remove .jmx extension
    
    return render_template('index.html', jmx_files=jmx_files)

@app.route('/report-list')
def report_list():
    """Render the report list page"""
    # 直接读取HTML文件内容并返回，这样可以避免静态文件路径问题
    try:
        with open('reportdiff/analysis/web_report/report_list.html', 'r') as f:
            content = f.read()
        return content
    except Exception as e:
        log_error(f"Failed to read report_list.html: {str(e)}")
        return "Error loading report list page", 500

@app.route('/result.html')
def result():
    """Serve the result.html page for report comparison"""
    try:
        with open('reportdiff/analysis/web_report/result.html', 'r') as f:
            content = f.read()
        return content
    except Exception as e:
        log_error(f"Failed to read result.html: {str(e)}")
        return "Error loading result page", 500

@app.route('/table-style.css')
def table_style():
    """Serve the table-style.css file for the report list"""
    try:
        with open('reportdiff/analysis/web_report/table-style.css', 'r') as f:
            content = f.read()
        return Response(content, mimetype='text/css')
    except Exception as e:
        log_error(f"Failed to read table-style.css: {str(e)}")
        return "Error loading CSS", 500

@app.route('/script.js')
def script_js():
    """Serve the script.js file for the report list"""
    try:
        with open('reportdiff/analysis/web_report/script.js', 'r') as f:
            content = f.read()
        return Response(content, mimetype='application/javascript')
    except Exception as e:
        log_error(f"Failed to read script.js: {str(e)}")
        return "Error loading JavaScript", 500

@app.route('/performance_data.json')
def get_performance_data():
    """Serve the performance_data.json file"""
    # Add cache control headers to ensure the latest data is fetched
    response = send_from_directory('reportdiff/analysis/web_report', 'performance_data.json')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/performance_data_<timestamp>.json')
def get_timestamped_performance_data(timestamp):
    """Serve timestamped performance data files"""
    filename = f'performance_data_{timestamp}.json'
    
    # First look in the reportdiff web_report directory
    file_path = f'reportdiff/analysis/web_report/{filename}'
    if os.path.exists(file_path):
        response = send_from_directory('reportdiff/analysis/web_report', filename)
    else:
        # Try nested web_report directory as fallback
        nested_file_path = f'reportdiff/analysis/web_report/web_report/{filename}'
        if os.path.exists(nested_file_path):
            response = send_from_directory('reportdiff/analysis/web_report/web_report', filename)
        else:
            return jsonify({'error': f'File {filename} not found'}), 404
    
    # Add cache control headers
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/compare', methods=['POST'])
def compare():
    """Endpoint to compare two JMeter test reports"""
    data = request.get_json()
    if not data or 'report1_path' not in data or 'report2_path' not in data:
        return jsonify({'error': '请提供两个报告的路径'}), 400

    # Get relative paths from request
    report1_relative_path = data['report1_path']
    report2_relative_path = data['report2_path']

    # Debug log the input paths
    print(f"Report 1 path: {report1_relative_path}")
    print(f"Report 2 path: {report2_relative_path}")

    # Extract directory names from paths
    # Path format is like /report/html/reportname_timestamp/index.html
    # We need to extract reportname_timestamp
    report1_dir = report1_relative_path.split('/')[-2]  # Get the second last segment
    report2_dir = report2_relative_path.split('/')[-2]  # Get the second last segment

    # Build absolute paths to statistics.json files
    file1_path = HTML_DIR / report1_dir / "statistics.json"
    file2_path = HTML_DIR / report2_dir / "statistics.json"

    # Debug log the constructed paths
    print(f"Statistics file 1: {file1_path}")
    print(f"Statistics file 2: {file2_path}")

    if not os.path.exists(file1_path) or not os.path.exists(file2_path):
        error_msg = f'报告的 statistics.json 文件未找到. 路径1: {file1_path}, 路径2: {file2_path}'
        print(error_msg)
        return jsonify({'error': error_msg}), 404

    try:
        # Create output directory in reportdiff/analysis/web_report
        output_dir = BASE_DIR / 'reportdiff' / 'analysis'
        
        # Use timestamp for unique output filename
        timestamp = int(time.time())
        output_filename = f'performance_data_{timestamp}.json'
        
        # Generate comparison report
        performance_data_path = generate_comparison_report(
            file1_path=str(file1_path),
            file2_path=str(file2_path),
            output_dir=str(output_dir),
            output_filename=output_filename
        )
        
        # Return success response
        return jsonify({
            'success': True, 
            'redirect': f'result.html?t={timestamp}&data_file=performance_data_{timestamp}.json'
        })
    
    except Exception as e:
        print(f"Error in comparison: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-test', methods=['POST'])
def start_test():
    """API endpoint to start a JMeter test"""
    global active_test
    
    if active_test:
        return jsonify({"success": False, "message": "A test is already running"}), 400
    
    data = request.json
    jmx_file = data.get('jmx_file')
    thread_num = int(data.get('thread_num', 100))
    test_duration = int(data.get('test_duration', 30))
    step_num = data.get('step_num') # Get step_num from request
    
    if not jmx_file:
        return jsonify({"success": False, "message": "JMX file name is required"}), 400
    
    # Convert step_num to int if it exists, otherwise pass None
    if step_num is not None:
        try:
            step_num = int(step_num)
        except ValueError:
            log_warn(f"Invalid step_num value: {step_num}. Ignoring.")
            step_num = None

    success = run_jmeter_test(jmx_file, thread_num, test_duration, step_num=step_num) # Pass step_num
    
    if success:
        return jsonify({
            "success": True, 
            "message": "Test started successfully",
            "test_info": {
                "jmx_file": jmx_file,
                "thread_num": thread_num,
                "test_duration": test_duration,
                "start_time": active_test['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    else:
        return jsonify({"success": False, "message": "Failed to start test"}), 500

@app.route('/api/test-status')
def test_status():
    """API endpoint to get the status of the current test"""
    if active_test:
        return jsonify({
            "running": True,
            "test_info": {
                "jmx_file": active_test['jmx_file'],
                "thread_num": active_test['thread_num'],
                "test_duration": active_test['test_duration'],
                "start_time": active_test['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    else:
        return jsonify({"running": False})

@app.route('/api/stop-test', methods=['POST'])
def stop_test():
    """API endpoint to stop the current test"""
    global active_test
    
    if not active_test:
        return jsonify({"success": False, "message": "No test is running"}), 400
    
    try:
        active_test['process'].terminate()
        log_warn("Test was manually terminated")
        return jsonify({"success": True, "message": "Test terminated"})
    except Exception as e:
        log_error(f"Failed to terminate test: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to terminate test: {str(e)}"}), 500

@app.route('/api/logs')
def stream_logs():
    """Stream logs to the client"""
    def generate():
        while True:
            try:
                # Get message from queue if available, otherwise wait
                log_message = log_queue.get(timeout=1)
                yield f"data: {json.dumps({'message': log_message})}\n\n"
            except queue.Empty:
                # If queue is empty, send a heartbeat
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@app.route('/api/jmx-files')
def get_jmx_files():
    """API endpoint to get a list of available JMX files"""
    jmx_files = []
    for file in os.listdir(JMX_DIR):
        if file.endswith('.jmx'):
            jmx_files.append(file[:-4])  # Remove .jmx extension
    
    return jsonify({"jmx_files": jmx_files})

@app.route('/api/reports')
def get_reports():
    """API endpoint to get a list of test reports"""
    reports = []
    for dir_name in os.listdir(HTML_DIR):
        dir_path = HTML_DIR / dir_name
        if os.path.isdir(dir_path) and os.path.exists(dir_path / "index.html"):
            # 处理不同的目录命名格式
            if '-' in dir_name and '_' in dir_name:  # 格式为 "jmx-200Vuser_20250506165136"
                # 提取测试名称和日期
                name_parts = dir_name.split('_')
                if len(name_parts) >= 2:
                    test_name = name_parts[0]  # 例如 "xiaocao-200Vuser"
                    date_str = name_parts[1]   # 例如 "20250506165136"
                    reports.append({
                        "name": test_name,
                        "date": date_str,
                        "path": f"/report/html/{dir_name}/index.html"
                    })
            elif '_' in dir_name:  # 格式为 "xiaocao_20250417174523"
                name_parts = dir_name.split('_')
                if len(name_parts) >= 2:
                    test_name = name_parts[0]  # 例如 "xiaocao"
                    date_str = name_parts[1]   # 例如 "20250417174523"
                    reports.append({
                        "name": test_name,
                        "date": date_str,
                        "path": f"/report/html/{dir_name}/index.html"
                    })
    
    # Sort reports by date (newest first)
    reports.sort(key=lambda x: x['date'], reverse=True)
    # Return array directly to match report_list.html's expected format
    return jsonify(reports)

@app.route('/report/html/<path:report_path>')
def serve_report_files(report_path):
    """Serve files from the report/html directory"""
    try:
        # 构建完整路径，但检查是否包含不安全的路径元素
        if '..' in report_path or report_path.startswith('/'):
            return "Access denied: Invalid path", 403
        
        full_path = os.path.join(HTML_DIR, report_path)
        
        # 如果是目录，尝试找到index.html
        if os.path.isdir(full_path):
            full_path = os.path.join(full_path, 'index.html')
            
        # 检查文件是否存在
        if not os.path.exists(full_path):
            log_error(f"Report file not found: {full_path}")
            return f"Report file not found: {report_path}", 404
            
        # 读取文件内容
        with open(full_path, 'rb') as f:
            content = f.read()
            
        # 根据文件扩展名设置合适的MIME类型
        mime_types = {
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.json': 'application/json',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
            '.eot': 'application/vnd.ms-fontobject',
            '.otf': 'font/otf',
            '.txt': 'text/plain'
        }
        
        # 获取文件扩展名并设置MIME类型
        _, ext = os.path.splitext(full_path)
        mime_type = mime_types.get(ext.lower(), 'application/octet-stream')
        
        return Response(content, mimetype=mime_type)
    except Exception as e:
        log_error(f"Error serving report file {report_path}: {str(e)}")
        return f"Error serving report file: {str(e)}", 500

@app.route('/api/check-servers')
def check_servers_api():
    """API endpoint to check the status of JMeter servers"""
    try:
        remote_servers = REMOTE_SERVERS
        server_statuses = []
        
        log_info("API: Starting to check remote JMeter Server status...")
        server_list = remote_servers.split(',')
        all_success = True
        
        for server in server_list:
            log_info(f"API: Checking JMeter Server status on {server}...")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((server, 1099))
                sock.close()
                
                status = result == 0
                server_statuses.append({
                    "server": server, 
                    "status": status, 
                    "message": "正常" if status else "无法连接"
                })
                
                if not status:
                    all_success = False
                    log_error(f"API: JMeter Server on {server} is not running or cannot be connected")
                else:
                    log_info(f"API: JMeter Server on {server} is running normally")
            except Exception as e:
                server_statuses.append({
                    "server": server, 
                    "status": False, 
                    "message": str(e)
                })
                all_success = False
                log_error(f"API: Error checking JMeter Server on {server}: {str(e)}")
        
        error_message = None
        if not all_success:
            error_message = "无法连接一个或多个JMeter服务器，请检查网络或服务器状态"
            
        return jsonify({
            "success": all_success,
            "servers": server_statuses,
            "message": error_message
        })
    except Exception as e:
        log_error(f"API: Error checking server status: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"检查服务器状态时出错: {str(e)}",
            "servers": []
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, threaded=True, debug=True)