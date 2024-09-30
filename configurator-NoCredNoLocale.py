#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import re
import getpass
import stat
import logging

# Configure logging
logging.basicConfig(
    filename='configurator.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Constants
MOUNT_POINT = '/mnt/orangepi_root'
BACKUP_SUFFIX = '.bak'

# Check for root privileges
if os.geteuid() != 0:
    print("This script must be run as root. Please run with sudo.")
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
            sys.exit(0)

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
        # Find the root partition (commonly last partition)
        lsblk = subprocess.check_output(['lsblk', '-ln', '-o', 'NAME,TYPE'], universal_newlines=True)
        partitions = [line.split()[0] for line in lsblk.strip().split('\n') if line.split()[1] == 'part' and line.startswith(os.path.basename(device))]
        if not partitions:
            logging.error("No partitions found on the device.")
            print("No partitions found on the device.")
            sys.exit(1)
        # Assuming the last partition is the root
        root_partition = f"/dev/{partitions[-1]}"
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

def modify_file_safely(original_path, modify_func):
    """
    Safely modify a file by creating a backup and applying the modification function.
    """
    try:
        backup_file(original_path)
        with open(original_path, 'r') as f:
            content = f.read()
        new_content = modify_func(content)
        with open(original_path, 'w') as f:
            f.write(new_content)
        logging.info(f"Successfully modified {original_path}")
    except Exception as e:
        logging.error(f"Error modifying {original_path}: {e}")
        print(f"Failed to modify {original_path}. Check logs for details.")
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
            wifi_pwd = prompt_input(
                "Enter WiFi Password: ",
                allow_empty=False,
                validation_regex=r'^[^\'"]+$',
                error_message="Password cannot contain quotes."
            )
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
        netplan_dir = os.path.join(mount_point, 'etc/netplan')
        netplan_conf = os.path.join(netplan_dir, '30-wifis-dhcp.yaml')
        try:
            os.makedirs(netplan_dir, exist_ok=True)
            with open(netplan_conf, 'w') as f:
                # Escape double quotes in SSID and password
                ssid_escaped = inputs['ssid'].replace('"', '\\"')
                wifi_pwd_escaped = inputs['wifi_pwd'].replace('"', '\\"')
                f.write(f"""network:
    version: 2
    renderer: networkd
    wifis:
      wlan0:
        dhcp4: true
        access-points:
          "{ssid_escaped}":
            password: "{wifi_pwd_escaped}"
""")
            logging.info(f"Configured Netplan with SSID: {inputs['ssid']}")
            print("Netplan configuration updated successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Netplan: {e}")
            print("Failed to configure Netplan. Check logs for details.")
            sys.exit(1)

        # Step 4: Install ip_blink.sh Script
        blink_script_path = os.path.join(mount_point, 'usr/local/bin/ip_blink.sh')
        try:
            os.makedirs(os.path.dirname(blink_script_path), exist_ok=True)
            with open(blink_script_path, 'w') as f:
                f.write("""#!/bin/bash

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

blink_subtractive() {  # Represents subtractive notation ('IV' for 4, 'IX' for 9)
  led_on
  sleep 0.1
  led_off
  sleep 0.1
  led_on
  sleep 0.4
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
    result="IV"
  elif [ $n -eq 9 ]; then
    result="IX"
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
""")
            os.chmod(blink_script_path, 0o750)
            logging.info(f"Installed ip_blink.sh script at {blink_script_path}")
            print("ip_blink.sh script installed successfully.")

        except Exception as e:
            logging.error(f"Failed to install ip_blink.sh: {e}")
            print("Failed to install ip_blink.sh. Check logs for details.")
            sys.exit(1)

        # Step 5: Create systemd Service
        service_file = os.path.join(mount_point, 'etc/systemd/system/ipblink.service')
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

        # Step 6: Enable the systemd Service
        try:
            wants_dir = os.path.join(mount_point, 'etc/systemd/system/multi-user.target.wants')
            os.makedirs(wants_dir, exist_ok=True)
            service_symlink = os.path.join(wants_dir, 'ipblink.service')
            if not os.path.exists(service_symlink):
                os.symlink('/etc/systemd/system/ipblink.service', service_symlink)
                logging.info(f"Enabled ipblink.service by creating symlink at {service_symlink}")
                print("Systemd service enabled to run on boot.")
            else:
                logging.info("Systemd service symlink already exists.")
        except Exception as e:
            logging.error(f"Failed to enable systemd service: {e}")
            print("Failed to enable systemd service. Check logs for details.")
            sys.exit(1)

        # Step 7: Ensure Correct Permissions for ip_blink.sh
        try:
            os.chmod(blink_script_path, 0o750)
            logging.info(f"Set correct permissions for {blink_script_path}")
        except Exception as e:
            logging.warning(f"Failed to set permissions for {blink_script_path}: {e}")

    finally:
        # Cleanup: Unmount the SD card
        unmount_partitions(mount_point)

    print("Configuration complete. You can now insert the SD card into your Orange Pi Zero 2W and boot it.")
    logging.info("Script completed successfully.")

if __name__ == '__main__':
    main()
