#!/bin/bash
echo "启动 perfmance run 服务"
nohup sh run_webapp.sh >> perftest.log 2>&1 &
echo "服务已成功启动"