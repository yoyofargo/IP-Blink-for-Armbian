#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import re
import getpass
import logging

# Constants
SCRIPT_NAME = os.path.basename(__file__)
LOG_FILENAME = os.path.splitext(SCRIPT_NAME)[0] + '.log'
MOUNT_POINT = '/mnt/orangepi_root'
BACKUP_SUFFIX = '.bak'
NETWORK_WAIT_OVERRIDE_DIR = 'etc/systemd/system/systemd-networkd-wait-online.service.d'
NETWORK_WAIT_OVERRIDE_FILE = 'override.conf'
NETWORK_WAIT_TIMEOUT = '30'  # in seconds
WIFI_INTERFACE = 'wlan0'  # Adjust as needed
NETPLAN_CONF_FILENAME = '30-wifis-dhcp.yaml'

# Configure logging to append to the log file
logging.basicConfig(
    filename=LOG_FILENAME,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'  # Append to the log file
)

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
            continue
        return pwd1

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
        # Check if the mount point is already mounted
        mount_output = subprocess.check_output(['mount'], universal_newlines=True)
        if any(mount_point in line for line in mount_output.strip().split('\n')):
            logging.info(f"{mount_point} is already mounted.")
            print(f"{mount_point} is already mounted.")
            return mount_point
        # Find the root partition (commonly last partition)
        lsblk = subprocess.check_output(['lsblk', '-ln', '-o', 'NAME,TYPE,MOUNTPOINT'], universal_newlines=True)
        partitions = []
        device_basename = os.path.basename(device).replace('/dev/', '')
        for line in lsblk.strip().split('\n'):
            cols = line.strip().split()
            if len(cols) >= 2:
                name, ptype = cols[:2]
                mountpoint = cols[2] if len(cols) > 2 else ''
                if ptype == 'part' and name.startswith(device_basename):
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

def create_network_wait_override(mount_point):
    """
    Create an override for systemd-networkd-wait-online.service to wait only for WiFi.
    """
    override_dir = os.path.join(mount_point, NETWORK_WAIT_OVERRIDE_DIR)
    override_file = os.path.join(override_dir, NETWORK_WAIT_OVERRIDE_FILE)
    try:
        os.makedirs(override_dir, exist_ok=True)
        with open(override_file, 'w') as f:
            f.write(f"""[Service]
ExecStart=
ExecStart=/usr/bin/systemd-networkd-wait-online --timeout={NETWORK_WAIT_TIMEOUT} --interface={WIFI_INTERFACE}
""")
        logging.info(f"Created systemd-networkd-wait-online.service override at {override_file}")
        print("Modified systemd-networkd-wait-online.service to wait only for WiFi.")
    except Exception as e:
        logging.error(f"Failed to create network wait override: {e}")
        print("Failed to create network wait override. Check logs for details.")
        sys.exit(1)

def update_netplan_configuration(netplan_conf_path, ssid, wifi_pwd):
    """
    Update the Netplan configuration file with the new WiFi settings by directly editing strings.
    """
    try:
        # Backup the existing Netplan configuration
        backup_file(netplan_conf_path)

        if os.path.exists(netplan_conf_path):
            with open(netplan_conf_path, 'r') as f:
                lines = f.readlines()
        else:
            lines = []

        # Flags to check if 'wifis' and 'wlan0' sections exist
        wifis_found = False
        wlan0_found = False

        # New configuration lines to add or replace
        new_wlan0_config = [
            f"  {WIFI_INTERFACE}:\n",
            f"    dhcp4: true\n",
            f"    access-points:\n",
            f"      \"{ssid}\":\n",
            f"        password: \"{wifi_pwd}\"\n"
        ]

        # Iterate through lines to find and modify the 'wifis' section
        for idx, line in enumerate(lines):
            if re.match(r'^\s*wifis:', line):
                wifis_found = True
                # Look for 'wlan0' under 'wifis'
                for j in range(idx + 1, len(lines)):
                    if re.match(r'^\s+\S+:', lines[j]):
                        interface_match = re.match(r'^\s+(\S+):', lines[j])
                        if interface_match:
                            interface = interface_match.group(1)
                            if interface == WIFI_INTERFACE:
                                wlan0_found = True
                                # Replace existing wlan0 configuration
                                # Find the start and end of the wlan0 block
                                start = j
                                end = j + 1
                                for k in range(j + 1, len(lines)):
                                    if re.match(r'^\s+\S+:', lines[k]):
                                        end = k
                                        break
                                # Replace the wlan0 block with new configuration
                                lines[start:end] = new_wlan0_config
                                logging.info(f"Updated existing wlan0 configuration in {netplan_conf_path}")
                                print("Updated existing wlan0 configuration in Netplan.")
                                break
                break

        if not wifis_found:
            # If 'wifis' section does not exist, add it
            lines.append("wifis:\n")
            lines.extend(new_wlan0_config)
            logging.info(f"Added new wifis section with wlan0 configuration in {netplan_conf_path}")
            print("Added new wifis section with wlan0 configuration in Netplan.")
        elif not wlan0_found:
            # If 'wlan0' section does not exist under 'wifis', add it
            # Find the end of 'wifis' section
            for idx, line in enumerate(lines):
                if re.match(r'^\s*wifis:', line):
                    insertion_idx = idx + 1
                    break
            lines[insertion_idx:insertion_idx] = new_wlan0_config
            logging.info(f"Added new wlan0 configuration under existing wifis section in {netplan_conf_path}")
            print("Added new wlan0 configuration under existing wifis section in Netplan.")

        # Write the updated configuration back to the file
        with open(netplan_conf_path, 'w') as f:
            f.writelines(lines)

        logging.info(f"Updated Netplan configuration at {netplan_conf_path}")
        print("Netplan configuration updated successfully.")

    except Exception as e:
        logging.error(f"Failed to update Netplan configuration: {e}")
        print("Failed to update Netplan configuration. Check logs for details.")
        sys.exit(1)

def enable_systemd_service(mount_point):
    """
    Enable the ipblink.service by creating a symbolic link in multi-user.target.wants.
    Handles existing symlinks or files gracefully.
    """
    try:
        wants_dir = os.path.join(mount_point, 'etc', 'systemd', 'system', 'multi-user.target.wants')
        os.makedirs(wants_dir, exist_ok=True)
        service_symlink = os.path.join(wants_dir, 'ipblink.service')
        target_service = '/etc/systemd/system/ipblink.service'

        if os.path.islink(service_symlink):
            existing_target = os.readlink(service_symlink)
            if existing_target == target_service:
                logging.info("systemd service symlink already exists and points to the correct target.")
                print("Systemd service symlink already exists and is correctly configured.")
            else:
                logging.warning(f"systemd service symlink points to {existing_target}. Recreating symlink.")
                os.remove(service_symlink)
                os.symlink(target_service, service_symlink)
                logging.info("systemd service symlink recreated successfully.")
                print("systemd service symlink was incorrect and has been recreated.")
        elif os.path.exists(service_symlink):
            # It's a file, not a symlink. Backup and create symlink.
            backup_path = service_symlink + BACKUP_SUFFIX
            shutil.move(service_symlink, backup_path)
            logging.warning(f"Existing file {service_symlink} moved to backup {backup_path}.")
            os.symlink(target_service, service_symlink)
            logging.info("systemd service symlink created successfully after backing up existing file.")
            print(f"Existing file {service_symlink} was backed up and symlink created successfully.")
        else:
            # Symlink does not exist; create it.
            os.symlink(target_service, service_symlink)
            logging.info("systemd service symlink created successfully.")
            print("Systemd service enabled to run on boot.")

    except PermissionError as e:
        logging.error(f"Permission denied while creating symlink: {e}")
        print("Permission denied while enabling systemd service. Please check permissions.")
        sys.exit(1)
    except FileExistsError as e:
        logging.error(f"Failed to create symlink because it already exists: {e}")
        print("Failed to enable systemd service because the symlink already exists.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to enable systemd service: {e}")
        print("Failed to enable systemd service. Check logs for details.")
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

        # Step 3: Update Netplan Configuration
        netplan_dir = os.path.join(mount_point, 'etc', 'netplan')
        os.makedirs(netplan_dir, exist_ok=True)
        netplan_conf = os.path.join(netplan_dir, NETPLAN_CONF_FILENAME)
        update_netplan_configuration(netplan_conf, inputs['ssid'], inputs['wifi_pwd'])

        # Step 4: Install ip_blink.sh Script
        blink_script_path = os.path.join(mount_point, 'usr', 'local', 'bin', 'ip_blink.sh')
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
""")
            os.chmod(blink_script_path, 0o750)
            logging.info(f"Installed ip_blink.sh script at {blink_script_path}")
            print("ip_blink.sh script installed successfully.")

        except Exception as e:
            logging.error(f"Failed to install ip_blink.sh: {e}")
            print("Failed to install ip_blink.sh. Check logs for details.")
            sys.exit(1)

        # Step 5: Create systemd Service
        service_file = os.path.join(mount_point, 'etc', 'systemd', 'system', 'ipblink.service')
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

        # Step 6: Enable the systemd Service with Enhanced Handling
        enable_systemd_service(mount_point)

        # Step 7: Modify systemd-networkd-wait-online.service to only wait for WiFi
        try:
            create_network_wait_override(mount_point)
            logging.info("Modified systemd-networkd-wait-online.service to wait only for WiFi.")
            print("Configured systemd-networkd-wait-online.service to wait only for WiFi interfaces.")
        except Exception as e:
            logging.error(f"Failed to modify network wait-online service: {e}")
            print("Failed to modify network wait-online service. Check logs for details.")
            sys.exit(1)

    finally:
        # Cleanup: Unmount the SD card
        unmount_partitions(mount_point)

    print("Configuration complete. You can now insert the SD card into your Orange Pi Zero 2W and boot it.")
    logging.info("Script completed successfully.")

if __name__ == '__main__':
    main()
