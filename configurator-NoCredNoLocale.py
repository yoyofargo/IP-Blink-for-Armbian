#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import re
import getpass
import stat
import logging
from pathlib import Path

# Attempt to import PyYAML, handle if not installed
try:
    import yaml
except ImportError:
    # PyYAML not installed, prompt user to install
    print("PyYAML is not installed.")
    install = input("Would you like to install it now? (Y/n): ").strip().lower()
    if install in ['y', 'yes', '']:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "PyYAML"])
            import yaml
            print("PyYAML installed successfully.")
        except subprocess.CalledProcessError:
            print("Failed to install PyYAML. Please install it manually and rerun the script.")
            sys.exit(1)
    else:
        print("PyYAML is required to run this script. Please install it and rerun the script.")
        sys.exit(1)

# Configure logging
script_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
log_filename = f"{script_name}.log"
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'  # Append mode
)

# Constants
MOUNT_POINT = '/mnt/orangepi_root'
BACKUP_SUFFIX = '.bak'
NETWORK_WAIT_OVERRIDE_DIR = 'etc/systemd/system/systemd-networkd-wait-online.service.d'
NETWORK_WAIT_OVERRIDE_FILE = 'override.conf'
NETWORK_WAIT_TIMEOUT = '30'  # in seconds
WIFI_INTERFACE = 'wlan0'  # Adjust as needed

# Check for root privileges
if os.geteuid() != 0:
    print("This script must be run as root. Please run with sudo.")
    logging.error("Script not run as root.")
    sys.exit(1)

def prompt_input(prompt, allow_empty=False, validation_regex=None, error_message="Invalid input."):
    """
    Prompt the user for input with optional validation.
    """
    while True:
        try:
            value = input(prompt).strip()
            if value.lower() == 'back':
                return 'back'
            if not value and not allow_empty:
                print("Input cannot be empty.")
                continue
            if validation_regex:
                if not re.match(validation_regex, value):
                    print(error_message)
                    continue
            return value
        except KeyboardInterrupt:
            print("\nExiting.")
            logging.info("Script exited by user.")
            sys.exit(0)

def prompt_password(prompt):
    """
    Prompt the user for a password without echoing.
    """
    while True:
        try:
            pwd = getpass.getpass(prompt)
            if pwd.lower() == 'back':
                return 'back'
            if not pwd:
                print("Password cannot be empty.")
                continue
            return pwd
        except KeyboardInterrupt:
            print("\nExiting.")
            logging.info("Script exited by user.")
            sys.exit(0)

def prompt_password_twice(prompt):
    """
    Prompt the user to enter a password twice and confirm they match.
    """
    while True:
        pwd1 = prompt_password(prompt)
        if pwd1 == 'back':
            return 'back'
        pwd2 = prompt_password("Confirm WiFi Password: ")
        if pwd2 == 'back':
            return 'back'
        if pwd1 != pwd2:
            print("Passwords do not match. Please try again.")
            logging.warning("User entered mismatching passwords.")
            continue
        return pwd1

def menu_select(options, prompt="Select an option:"):
    """
    Display a menu of options and prompt the user to select one.
    """
    for idx, option in enumerate(options, 1):
        print(f"{idx}. {option}")
    while True:
        choice = input(prompt).strip()
        if choice.lower() == 'back':
            return 'back'
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        else:
            print(f"Please enter a number between 1 and {len(options)} or 'back' to return.")

def detect_sd_card():
    """
    Detect removable SD card devices connected via USB or MMC.
    """
    logging.info("Detecting SD card devices...")
    devices = []
    try:
        lsblk_output = subprocess.check_output(['lsblk', '-S', '-o', 'NAME,MODEL,TRAN,SIZE'], universal_newlines=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to execute lsblk: {e}")
        print("Failed to detect block devices.")
        sys.exit(1)

    lines = lsblk_output.strip().split('\n')
    device_lines = lines[1:]
    for line in device_lines:
        parts = re.split(r'\s+', line.strip())
        if len(parts) < 4:
            continue
        name, model, tran, size = parts
        device_path = f"/dev/{name}"
        if tran.lower() in ['usb', 'mmc']:
            devices.append((device_path, model, size))

    if not devices:
        print("No removable devices detected. Please insert the SD card and try again.")
        logging.error("No removable devices detected.")
        sys.exit(1)

    print("Available devices:")
    for idx, dev in enumerate(devices, 1):
        device_path, model, size = dev
        print(f"{idx}. {device_path} - {model} - {size}")

    while True:
        choice = input("Select the SD card device to configure: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(devices):
            selected_device = devices[int(choice)-1][0]
            logging.info(f"Selected device: {selected_device}")
            return selected_device
        else:
            print(f"Please enter a number between 1 and {len(devices)}.")

def mount_partitions(device):
    """
    Mount the root partition of the SD card to the specified mount point.
    """
    logging.info(f"Mounting partitions for device {device}")
    mount_point = MOUNT_POINT
    try:
        if not os.path.exists(mount_point):
            os.makedirs(mount_point)
            logging.info(f"Created mount point directory: {mount_point}")

        # Check if the mount point is already mounted
        mount_output = subprocess.check_output(['mount'], universal_newlines=True)
        if any(mount_point in line for line in mount_output.strip().split('\n')):
            logging.info(f"{mount_point} is already mounted.")
            print(f"{mount_point} is already mounted.")
            return mount_point

        # Find the root partition (commonly last partition)
        lsblk = subprocess.check_output(['lsblk', '-ln', '-o', 'NAME,TYPE,MOUNTPOINT'], universal_newlines=True)
        partitions = []
        for line in lsblk.strip().split('\n'):
            cols = line.strip().split()
            if len(cols) >= 2:
                name, ptype = cols[:2]
                mountpoint = cols[2] if len(cols) > 2 else ''
                if ptype == 'part' and name.startswith(os.path.basename(device).replace('/dev/', '')):
                    partitions.append((name, mountpoint))
        if not partitions:
            logging.error("No partitions found on the device.")
            print("No partitions found on the device.")
            sys.exit(1)
        # Assuming the last partition is the root
        root_partition_name, mountpoint = partitions[-1]
        root_partition = f"/dev/{root_partition_name}"
        # If already mounted, skip mounting
        if mountpoint:
            logging.info(f"Partition {root_partition} is already mounted at {mountpoint}")
            return mountpoint
        else:
            logging.info(f"Attempting to mount {root_partition} to {mount_point}")
            subprocess.run(['mount', root_partition, mount_point], check=True)
            return mount_point
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to mount partition: {e}")
        print(f"Failed to mount {root_partition}.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error during mounting: {e}")
        print("An unexpected error occurred while mounting the partition.")
        sys.exit(1)

def unmount_partitions(mount_point):
    """
    Unmount the mounted partition.
    """
    logging.info(f"Unmounting {mount_point}")
    try:
        subprocess.run(['umount', mount_point], check=True)
        logging.info(f"Successfully unmounted {mount_point}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to unmount {mount_point}: {e}")
        print(f"Failed to unmount {mount_point}. Please unmount it manually.")
    except Exception as e:
        logging.error(f"Unexpected error during unmounting: {e}")
        print("An unexpected error occurred while unmounting the partition.")

def backup_file(file_path):
    """
    Create a backup of the specified file.
    """
    if os.path.exists(file_path):
        backup_path = file_path + BACKUP_SUFFIX
        shutil.copy2(file_path, backup_path)
        logging.info(f"Backup created for {file_path} at {backup_path}")
    else:
        logging.warning(f"Attempted to backup non-existent file: {file_path}")

def validate_wifi_ssid(ssid):
    """
    Validate the WiFi SSID to prevent YAML injection.
    """
    # Basic validation to prevent YAML injection
    # Disallow quotes
    if '"' in ssid or "'" in ssid:
        return False
    return True

def validate_wifi_password(password):
    """
    Validate the WiFi password to prevent YAML injection.
    """
    # Basic validation to prevent YAML injection
    # Disallow quotes
    if '"' in password or "'" in password:
        return False
    return True

def modify_netplan_config(mount_point, ssid, wifi_pwd):
    """
    Modify or create the Netplan configuration file with the provided WiFi settings.
    """
    netplan_dir = Path(mount_point) / 'etc/netplan'
    netplan_conf = netplan_dir / '30-wifis-dhcp.yaml'
    try:
        netplan_dir.mkdir(parents=True, exist_ok=True)
        if netplan_conf.exists():
            # Load existing configuration
            with open(netplan_conf, 'r') as f:
                config = yaml.safe_load(f) or {}
            logging.info(f"Loaded existing Netplan configuration from {netplan_conf}")
        else:
            config = {}
            logging.info(f"Creating new Netplan configuration at {netplan_conf}")

        # Update Netplan configuration
        config['network'] = config.get('network', {})
        config['network']['version'] = 2
        config['network']['renderer'] = 'networkd'
        config['network']['wifis'] = config['network'].get('wifis', {})

        # Add or update wlan0 configuration
        config['network']['wifis']['wlan0'] = {
            'dhcp4': True,
            'access-points': {
                ssid: {
                    'password': wifi_pwd
                }
            }
        }

        # Write the updated configuration back to the file
        with open(netplan_conf, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        logging.info(f"Netplan configuration updated at {netplan_conf}")
        print("Netplan configuration updated successfully.")
    except Exception as e:
        logging.error(f"Failed to modify Netplan configuration: {e}")
        print("Failed to modify Netplan configuration. Check logs for details.")
        sys.exit(1)

def install_ip_blink_script(mount_point):
    """
    Install the ip_blink.sh script to /usr/local/bin/ and set appropriate permissions.
    """
    blink_script_path = Path(mount_point) / 'usr/local/bin/ip_blink.sh'
    try:
        blink_script_dir = blink_script_path.parent
        blink_script_dir.mkdir(parents=True, exist_ok=True)
        blink_script_content = """#!/bin/bash

# Disable the default trigger for the green LED
echo none > /sys/class/leds/green_led/trigger

# Function to turn the LED on
led_on() {
  echo 1 > /sys/class/leds/green_led/brightness
}

# Function to turn the LED off
led_off() {
  echo 0 > /sys/class/leds/green_led/brightness
}

# Functions to represent blink durations
blink_short() {  # Represents 'I' (1)
  led_on
  sleep 0.1
  led_off
  sleep 0.1
}

blink_medium() {  # Represents 'V' (5)
  led_on
  sleep 0.4
  led_off
  sleep 0.1
}

blink_long() {  # Represents 'X' (10) or 0
  led_on
  sleep 1.2
  led_off
  sleep 0.1
}

# Function to convert a digit to Roman numerals
digit_to_roman() {
  local n=$1
  local result=""

  if [ $n -eq 0 ]; then
    result="X"
  elif [ $n -eq 4 ]; then
    result="IIII"
  elif [ $n -eq 9 ]; then
    result="VIIII"
  else
    if [ $n -ge 5 ]; then
      result="V"
      n=$(( n - 5 ))
    fi
    if [ $n -ge 1 ]; then
      result="${result}$(printf 'I%.0s' $(seq 1 $n))"
    fi
  fi

  echo "$result"
}

# Function to blink a digit
blink_digit() {
  local digit=$1
  local roman=$(digit_to_roman $digit)

  for (( i=0; i<${#roman}; i++ )); do
    c=${roman:$i:1}
    if [ "$c" == "I" ]; then
      blink_short
    elif [ "$c" == "V" ]; then
      blink_medium
    elif [ "$c" == "X" ]; then
      blink_long
    fi
  done

  # Wait 1 second between digits
  sleep 1
}

# Function to blink the IP address
blink_ip() {
  for octet in "${digits[@]}"; do
    # Break down the octet into individual digits
    if [ $octet -ge 100 ]; then
      digit1=$(( octet / 100 ))
      digit2=$(( (octet % 100) / 10 ))
      digit3=$(( octet % 10 ))
      blink_digit $digit1
      blink_digit $digit2
      blink_digit $digit3
    elif [ $octet -ge 10 ]; then
      digit1=$(( octet / 10 ))
      digit2=$(( octet % 10 ))
      blink_digit $digit1
      blink_digit $digit2
    else
      blink_digit $octet
    fi
  done
}

# Get the default network interface
default_iface=$(ip route | awk '/default/ {print $5}')
if [ -z "$default_iface" ]; then
  # No network interface found
  digits=(0 0 0)
else
  # Get the IP address assigned to the default interface
  ip_address=$(ip -o -4 addr list $default_iface | awk '{print $4}' | cut -d/ -f1)
  if [ -z "$ip_address" ]; then
    # No IP address assigned
    digits=(0 0 0)
  else
    # Split the IP address into octets
    IFS='.' read -r octet1 octet2 octet3 octet4 <<< "$ip_address"

    # Decide which octets to blink
    if [ "$octet3" == "0" ]; then
      digits=($octet4)
    else
      digits=($octet3 $octet4)
    fi
  fi
fi

# Blink the IP address ten times
for (( count=0; count<10; count++ )); do
  blink_ip
  # Wait 2 seconds between each complete IP blink sequence
  sleep 2
done

# Set the trigger to "heartbeat" at the end
echo "heartbeat" > /sys/class/leds/green_led/trigger
"""
        with open(blink_script_path, 'w') as f:
            f.write(blink_script_content)
        blink_script_path.chmod(0o750)
        logging.info(f"Installed ip_blink.sh script at {blink_script_path}")
        print("ip_blink.sh script installed successfully.")

def create_systemd_service(mount_point):
    """
    Create the systemd service file for ipblink.service.
    """
    service_file = Path(mount_point) / 'etc/systemd/system/ipblink.service'
    try:
        with open(service_file, 'w') as f:
            f.write("""[Unit]
Description=Blink IP address on green LED
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ip_blink.sh
RemainAfterExit=no
ProtectSystem=full
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
""")
        logging.info(f"Created systemd service at {service_file}")
        print("Systemd service file created successfully.")
    except Exception as e:
        logging.error(f"Failed to create systemd service: {e}")
        print("Failed to create systemd service. Check logs for details.")
        sys.exit(1)

def enable_systemd_service(mount_point):
    """
    Enable the systemd service to run on boot by creating a symlink.
    """
    try:
        wants_dir = Path(mount_point) / 'etc/systemd/system/multi-user.target.wants'
        wants_dir.mkdir(parents=True, exist_ok=True)
        service_symlink = wants_dir / 'ipblink.service'
        service_path = '/etc/systemd/system/ipblink.service'
        if not service_symlink.exists():
            service_symlink.symlink_to(service_path)
            logging.info(f"Enabled ipblink.service by creating symlink at {service_symlink}")
            print("Systemd service enabled to run on boot.")
        else:
            logging.info("Systemd service symlink already exists.")
    except Exception as e:
        logging.error(f"Failed to enable systemd service: {e}")
        print("Failed to enable systemd service. Check logs for details.")
        sys.exit(1)

def modify_network_wait_override(mount_point):
    """
    Modify systemd-networkd-wait-online.service to wait only for WiFi.
    """
    override_dir = Path(mount_point) / NETWORK_WAIT_OVERRIDE_DIR
    override_file = override_dir / NETWORK_WAIT_OVERRIDE_FILE
    try:
        override_dir.mkdir(parents=True, exist_ok=True)
        override_content = f"""[Service]
ExecStart=
ExecStart=/usr/bin/systemd-networkd-wait-online --timeout={NETWORK_WAIT_TIMEOUT} --interface={WIFI_INTERFACE}
"""
        with open(override_file, 'w') as f:
            f.write(override_content)
        logging.info(f"Created systemd-networkd-wait-online.service override at {override_file}")
        print("Modified systemd-networkd-wait-online.service to wait only for WiFi.")
    except Exception as e:
        logging.error(f"Failed to create network wait override: {e}")
        print("Failed to create network wait override. Check logs for details.")
        sys.exit(1)

def main():
    print("Welcome to the Orange Pi Zero 2W IP Blink and WiFi Configurator")
    logging.info("Script started.")

    # Step 1: Detect and Mount SD Card
    device = detect_sd_card()
    mount_point = mount_partitions(device)

    try:
        # Step 2: Collect WiFi SSID and Password
        inputs = {}
        while True:
            ssid = prompt_input(
                "Enter WiFi SSID: ",
                validation_regex=r'^[^\'"]+$',
                error_message="SSID cannot contain quotes."
            )
            if ssid == 'back':
                print("Cannot go back from the first step.")
                continue
            if not validate_wifi_ssid(ssid):
                print("SSID contains invalid characters.")
                continue
            inputs['ssid'] = ssid
            break

        while True:
            wifi_pwd = prompt_password_twice("Enter WiFi Password: ")
            if wifi_pwd == 'back':
                # Allow going back to re-enter SSID
                print("To re-enter SSID, please restart the script.")
                continue
            if not validate_wifi_password(wifi_pwd):
                print("Password contains invalid characters.")
                continue
            inputs['wifi_pwd'] = wifi_pwd
            break

        # Step 3: Configure Netplan
        modify_netplan_config(mount_point, inputs['ssid'], inputs['wifi_pwd'])

        # Step 4: Install ip_blink.sh Script
        install_ip_blink_script(mount_point)

        # Step 5: Create systemd Service
        create_systemd_service(mount_point)

        # Step 6: Enable the systemd Service
        enable_systemd_service(mount_point)

        # Step 7: Modify systemd-networkd-wait-online.service to only wait for WiFi
        modify_network_wait_override(mount_point)

    finally:
        # Cleanup: Unmount the SD card
        unmount_partitions(mount_point)

    print("Configuration complete. You can now insert the SD card into your Orange Pi Zero 2W and boot it.")
    logging.info("Script completed successfully.")

if __name__ == '__main__':
    main()
