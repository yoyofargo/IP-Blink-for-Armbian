#!/usr/bin/env python3

import os
import sys
import subprocess
import re
import getpass

# Check for root privileges
if os.geteuid() != 0:
    print("This script must be run as root. Please run with sudo.")
    sys.exit(1)

def prompt_input(prompt, pattern=None, allow_empty=False):
    while True:
        try:
            value = input(prompt).strip()
            if value.lower() == 'back':
                return 'back'
            if not value and not allow_empty:
                print("Input cannot be empty.")
                continue
            if pattern and not re.match(pattern, value):
                print("Input contains invalid characters or does not meet the criteria.")
                continue
            return value
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)

def confirm_password(prompt="Enter password: ", min_length=1, max_length=63):
    while True:
        pwd1 = getpass.getpass(prompt)
        if pwd1.lower() == 'back':
            return 'back'
        if len(pwd1) < min_length or len(pwd1) > max_length:
            print(f"Password must be between {min_length} and {max_length} characters.")
            continue
        pwd2 = getpass.getpass("Confirm password: ")
        if pwd2.lower() == 'back':
            return 'back'
        if pwd1 != pwd2:
            print("Passwords do not match. Please try again.")
        else:
            return pwd1

def detect_sd_card():
    print("Detecting SD card devices...")
    devices = []
    # Use lsblk to list all block devices
    lsblk_output = subprocess.check_output(['lsblk', '-S', '-o', 'NAME,MODEL,TRAN,SIZE'], universal_newlines=True)
    lines = lsblk_output.strip().split('\n')
    device_lines = lines[1:]
    for line in device_lines:
        parts = re.split(r'\s+', line.strip())
        if len(parts) < 4:
            continue
        name, model, tran, size = parts
        device_path = f"/dev/{name}"
        # Assume that devices with 'usb' or 'mmc' transport are removable drives
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
        choice = input("Select the SD card device to configure: ")
        if choice.isdigit() and 1 <= int(choice) <= len(devices):
            return devices[int(choice)-1][0]
        else:
            print(f"Please enter a number between 1 and {len(devices)}.")

def mount_partitions(device):
    # Attempt to find the root partition (ext4)
    mount_point = '/mnt/orangepi_root'
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    partitions = [device + suffix for suffix in ['p1', '1']]
    partition_found = False
    for partition in partitions:
        if os.path.exists(partition):
            try:
                print(f"Trying to mount {partition} to {mount_point}...")
                subprocess.run(['mount', partition, mount_point], check=True)
                partition_found = True
                break
            except subprocess.CalledProcessError:
                continue
    if not partition_found:
        print("Could not find a valid partition to mount.")
        sys.exit(1)
    return mount_point

def unmount_partitions(mount_point):
    print(f"Unmounting {mount_point}...")
    subprocess.run(['umount', mount_point], check=True)

def main():
    print("Welcome to the Orange Pi Zero 2W Configurator")

    # Step 1: Detect and Mount SD Card
    device = detect_sd_card()
    mount_point = mount_partitions(device)

    try:
        # Step 2: Collect User Inputs
        inputs = {}
        step = 0
        steps = ['Configure WiFi']

        while step < len(steps):
            print(f"\n--- {steps[step]} ---")
            print("Type 'back' to return to the previous step.")

            if step == 0:
                ssid = prompt_input("Enter WiFi SSID: ", pattern=r'^[\x20-\x7E]{1,32}$')
                if ssid == 'back':
                    print("Cannot go back from the first step.")
                    continue
                wifi_pwd = confirm_password("Enter WiFi password: ", min_length=8, max_length=63)
                if wifi_pwd == 'back':
                    continue  # Stay on the same step to re-enter SSID
                inputs['ssid'] = ssid
                inputs['wifi_pwd'] = wifi_pwd
                step += 1

            else:
                step += 1

        # Step 3: Modify Configuration Files Directly

        # 3.1 Configure WiFi
        netplan_dir = os.path.join(mount_point, 'etc/netplan')
        os.makedirs(netplan_dir, exist_ok=True)
        netplan_conf = os.path.join(netplan_dir, '30-wifis-dhcp.yaml')
        with open(netplan_conf, 'w') as f:
            f.write(f"""network:
  version: 2
  renderer: networkd
  wifis:
    wlan0:
      dhcp4: true
      access-points:
        "{inputs['ssid']}":
          password: "{inputs['wifi_pwd']}"
""")

        # 3.2 Install blink_ip.sh script
        blink_script = os.path.join(mount_point, 'usr/local/bin/blink_ip.sh')
        os.makedirs(os.path.dirname(blink_script), exist_ok=True)
        with open(blink_script, 'w') as f:
            f.write("""#!/bin/bash

# Disable the default trigger for the green LED
original_trigger=$(cat /sys/class/leds/green_led/trigger)
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
    elif [ "$c" == "IV" ] || [ "$c" == "IX" ]; then
      blink_subtractive
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

# Restore the original trigger for the green LED
echo "$original_trigger" > /sys/class/leds/green_led/trigger
""")
        os.chmod(blink_script, 0o755)

        # 3.3 Create systemd service
        service_file = os.path.join(mount_point, 'etc/systemd/system/blinkip.service')
        with open(service_file, 'w') as f:
            f.write("""[Unit]
Description=Blink IP address on green LED
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/blink_ip.sh
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
""")
        # Enable the service by creating a symlink
        wants_dir = os.path.join(mount_point, 'etc/systemd/system/multi-user.target.wants')
        os.makedirs(wants_dir, exist_ok=True)
        service_symlink = os.path.join(wants_dir, 'blinkip.service')
        if not os.path.exists(service_symlink):
            os.symlink('/etc/systemd/system/blinkip.service', service_symlink)

    finally:
        # Cleanup
        unmount_partitions(mount_point)

    print("Configuration complete. You can now insert the SD card into your Orange Pi Zero 2W and boot it.")

if __name__ == '__main__':
    main()
