# JMeter Web Runner

A web application to run and monitor distributed JMeter tests, view real-time logs, and manage test reports.

## Features

- Web interface to configure and execute JMeter tests
- Real-time logging display
- Test progress tracking
- Report management
- WeChat notification integration

## Prerequisites

- Python 3.7+
- Apache JMeter installed in `apache-jmeter` directory
- Remote JMeter servers set up for distributed testing

## Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Ensure your JMeter installation is in the `apache-jmeter` directory.

4. Make sure the required directories exist (automatically created by the app):
   - `testplan/`: Place your JMX files here
   - `report/html/`: Test reports will be stored here
   - `jtl/`: JTL result files will be stored here
   - `log/`: JMeter log files will be stored here

## Configuration

The following configuration parameters can be found at the top of `app.py`:

- `REMOTE_SERVERS`: Comma-separated list of JMeter server IP addresses
- `REPORT_URL`: Base URL for accessing test reports
- `WECHAT_WEBHOOK`: WeChat robot webhook URL (optional)

## Running the Application

Start the web application:

```
python app.py
```

The application will run on port 5001 by default. Access it at:

```
http://localhost:5001
```

## Usage

1. **Home Page**
   - The main page shows the test runner interface

2. **Running a Test**
   - Select a JMX file from the dropdown
   - Set the number of concurrent users (per server)
   - Set the test duration in seconds
   - Click "Start Test"
   - View real-time logs on the right side

3. **Test Status**
   - When a test is running, the progress and status are shown
   - You can monitor elapsed time and completion percentage
   - Tests can be manually stopped using the "Stop Test" button

4. **Test Reports**
   - Click the "View Reports" tab to see all completed tests
   - Click on "View Report" to open the JMeter HTML report

## Logs

Logs are displayed in real-time in the web interface. They include:
- JMeter server status checks
- Test start/stop events
- Error messages
- Test completion information

## Notes

- Only one test can run at a time
- The application automatically calculates the actual thread count based on the number of JMeter servers
- WeChat notifications are sent upon test completion with test summary information 