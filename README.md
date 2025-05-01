# Email Relay Project

A flexible Python script for processing and relaying emails with advanced PDF attachment handling.

## Features
- Email fetching and relaying
- PDF attachment merging
- Configurable invoice processing
- Simulation mode
- Debug logging

## Prerequisites
- Python 3.8+
- Email Account

## Setup
1. Clone the repository
2. Create a virtual environment
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies
   ```
   pip install -r requirements.txt
   ```
4. Configure `.env` file
   - Copy `.env.example` to `.env`
   - Fill in your email configuration
   - Optionally set `INVOICE_STRING` to prioritize specific PDFs

## Usage
```bash
# Normal mode
python email_relay.py

# Debug mode
DEBUG_EMAIL_RELAY=true python email_relay.py
```

## Configuration
- `SOURCE_EMAIL_*`: Source mailbox credentials
- `RELAY_EMAIL_*`: SMTP relay configuration
- `INVOICE_STRING`: Optional prefix to identify invoice PDFs
- `DEBUG_EMAIL_RELAY`: Enable detailed logging
- Destination email (SMTP settings)
- Relay email addresses

## Installation

### 1. System Prerequisites
- Python 3.8+ installed
- `pip` package manager
- `crontab` access (for scheduling)

#### macOS Specific Setup
- Recommended: Install Python via Homebrew
  ```bash
  # Install Homebrew (if not already installed)
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Install Python
  brew install python
  ```
- Verify Python path: `which python3`
- Ensure full disk access for email operations in System Preferences

### 2. Virtual Environment Setup
```bash
# Navigate to project directory
cd /path/to/py_email_relay

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your email credentials
nano .env
```

### 4. Cronjob Setup
To run the email relay automatically at intervals:

```bash
# Find your Python path (macOS)
which python3

# Open crontab editor
crontab -e

# Add a job to run every 15 minutes
# Use the full path to Python and the script
*/15 * * * * /opt/homebrew/bin/python3 /full/path/to/py_email_relay/email_relay.py >> /full/path/to/py_email_relay/email_relay.log 2>&1
```

#### Alternative: macOS Launchd
For more robust scheduling on macOS, consider using `launchd`:

1. Create a plist file in `~/Library/LaunchAgents/`
2. Example `com.emailrelay.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.emailrelay</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>/full/path/to/py_email_relay/email_relay.py</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>StandardOutPath</key>
    <string>/full/path/to/py_email_relay/email_relay.log</string>
    <key>StandardErrorPath</key>
    <string>/full/path/to/py_email_relay/email_relay_error.log</string>
</dict>
</plist>
```

3. Load the service:
```bash
launchctl load ~/Library/LaunchAgents/com.emailrelay.plist
```

### 5. Logging
- The cronjob redirects output to `email_relay.log`
- Check this file for any errors or issues

## Usage
### Standard Mode
- Manually run: `./venv/bin/python email_relay.py`
- Automatic: Managed by cronjob

### Simulation Mode
- Run with simulation flag to save emails as .eml files instead of sending:
  ```bash
  # Simulate email relay (saves emails to ~/Desktop/email_relay_simulation)
  ./venv/bin/python email_relay.py --simulate
  ```
- Useful for testing and debugging
- Each email gets a unique folder with:
  - `email.eml`: Full email message
  - Original attachments preserved
- Folder name format: `YYYYMMDD_HHMMSS_email_subject`
- No actual emails are sent in simulation mode

#### Simulation Folder Structure
```
email_relay_simulation/
├── 20250501_120000_Important_Project_Details/
│   ├── email.eml
│   ├── document.pdf
│   └── image.jpg
└── 20250501_130000_Meeting_Notes/
    ├── email.eml
    └── presentation.pptx
```

## Security Notes
- Never commit your `.env` file
- Use strong, unique passwords
- Protect the log file with appropriate permissions
- Consider using app-specific passwords if available

### macOS Security Considerations
- Set restrictive file permissions:
  ```bash
  # Secure .env file
  chmod 600 .env
  
  # Secure log files
  chmod 640 email_relay.log
  ```
- Use Keychain for storing sensitive credentials
- Enable FileVault disk encryption
- Regularly update macOS and Python
- Consider using `chmod -R go-rwx` on the project directory
