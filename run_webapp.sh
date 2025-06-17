#!/bin/bash
##############################################################################
# Name        : run_webapp.sh
# Description : Start the JMeter Web Runner application
# Author      : 醉逍遥
# Version     : 1.0
##############################################################################

echo "Starting JMeter Web Runner..."
echo "Make sure you have installed the required dependencies:"
echo "  pip install -r requirements.txt"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found. Please install Python 3."
    exit 1
fi

# Check if required directories exist, create if not
for dir in testplan report/html jtl log; do
    if [ ! -d "$dir" ]; then
        echo "Creating directory: $dir"
        mkdir -p "$dir"
    fi
done

# Check if JMeter is installed
if [ ! -d "apache-jmeter" ]; then
    echo "Warning: 'apache-jmeter' directory not found."
    echo "Please make sure Apache JMeter is installed in the 'apache-jmeter' directory."
fi

# Start the application
echo "Starting web application on http://localhost:5001"
python3 app.py 