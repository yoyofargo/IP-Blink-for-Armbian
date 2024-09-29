#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import time
import re
import getpass
import crypt
import stat
import hashlib
import datetime

# Check for root privileges
if os.geteuid() != 0:
    print("This script must be run as root. Please run with sudo.")
    sys.exit(1)

def prompt_input(prompt, allow_empty=False):
    while True:
        try:
            value = input(prompt)
            if value.lower() == 'back':
                return 'back'
            if not value and not allow_empty:
                print("Input cannot be empty.")
                continue
            return value
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)

def confirm_password():
    while True:
        pwd1 = getpass.getpass("Enter password: ")
        if pwd1.lower() == 'back':
            return 'back'
        pwd2 = getpass.getpass("Confirm password: ")
        if pwd2.lower() == 'back':
            return 'back'
        if pwd1 != pwd2:
            print("Passwords do not match. Please try again.")
        else:
            return pwd1

def menu_select(options, prompt="Select an option:"):
    for idx, option in enumerate(options, 1):
        print(f"{idx}. {option}")
    while True:
        choice = input(prompt)
        if choice.lower() == 'back':
            return 'back'
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        else:
            print(f"Please enter a number between 1 and {len(options)} or 'back' to return.")

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

def generate_password_hash(password):
    # Use SHA-512 hashing algorithm
    salt = '$6$' + hashlib.sha256(os.urandom(16)).hexdigest()
    return crypt.crypt(password, salt)

def get_current_date_in_days():
    # Calculate the number of days since Jan 1, 1970
    epoch = datetime.date(1970, 1, 1)
    today = datetime.date.today()
    return (today - epoch).days

def main():
    print("Welcome to the Orange Pi Zero 2W Configurator")

    # Step 1: Detect and Mount SD Card
    device = detect_sd_card()
    mount_point = mount_partitions(device)

    try:
        # Step 2: Collect User Inputs
        inputs = {}
        step = 0
        steps = ['Set Root Password', 'Create User', 'Set Timezone', 'Set Locale', 'Configure WiFi']

        while step < len(steps):
            print(f"\n--- {steps[step]} ---")
            print("Type 'back' to return to the previous step.")

            if step == 0:
                root_pwd = confirm_password()
                if root_pwd == 'back':
                    print("Cannot go back from the first step.")
                    continue  # Stay on the first step
                inputs['root_pwd'] = root_pwd
                step += 1

            elif step == 1:
                username = prompt_input("Enter username: ")
                if username == 'back':
                    step -= 1
                    if step < 0:
                        step = 0
                    continue
                user_pwd = confirm_password()
                if user_pwd == 'back':
                    continue  # Stay on the same step to re-enter username
                inputs['username'] = username
                inputs['user_pwd'] = user_pwd
                step += 1

            elif step == 2:
                timezones = ['UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Other']
                print("Available Timezones:")
                tz_idx = menu_select(timezones)
                if tz_idx == 'back':
                    step -=1
                    if step < 0:
                        step = 0
                    continue
                if timezones[tz_idx] == 'Other':
                    custom_tz = prompt_input("Enter your timezone (e.g., Europe/London): ")
                    if custom_tz == 'back':
                        continue  # Stay on the same step
                    inputs['timezone'] = custom_tz
                else:
                    inputs['timezone'] = timezones[tz_idx]
                step += 1

            elif step == 3:
                locales = ['en_US.UTF-8', 'en_GB.UTF-8', 'de_DE.UTF-8', 'Other']
                print("Available Locales:")
                loc_idx = menu_select(locales)
                if loc_idx == 'back':
                    step -=1
                    if step < 0:
                        step = 0
                    continue
                if locales[loc_idx] == 'Other':
                    custom_locale = prompt_input("Enter your locale (e.g., en_AU.UTF-8): ")
                    if custom_locale == 'back':
                        continue  # Stay on the same step
                    inputs['locale'] = custom_locale
                else:
                    inputs['locale'] = locales[loc_idx]
                step += 1

            elif step == 4:
                ssid = prompt_input("Enter WiFi SSID: ")
                if ssid == 'back':
                    step -=1
                    if step < 0:
                        step = 0
                    continue
                wifi_pwd = confirm_password()
                if wifi_pwd == 'back':
                    continue  # Stay on the same step to re-enter SSID
                inputs['ssid'] = ssid
                inputs['wifi_pwd'] = wifi_pwd
                step += 1

            else:
                step += 1

        # Step 3: Modify Configuration Files Directly

        # 3.1 Set Root Password
        shadow_file = os.path.join(mount_point, 'etc/shadow')
        with open(shadow_file, 'r') as f:
            shadow_lines = f.readlines()
        new_shadow_lines = []
        root_hash = generate_password_hash(inputs['root_pwd'])
        last_change = str(get_current_date_in_days())
        for line in shadow_lines:
            if line.startswith('root:'):
                parts = line.strip().split(':')
                parts[1] = root_hash
                parts[2] = last_change  # Set last password change to current date
                new_line = ':'.join(parts) + '\n'
                new_shadow_lines.append(new_line)
            else:
                new_shadow_lines.append(line)
        with open(shadow_file, 'w') as f:
            f.writelines(new_shadow_lines)

        # 3.2 Create User
        uid = 1000  # Starting UID for regular users
        passwd_file = os.path.join(mount_point, 'etc/passwd')
        with open(passwd_file, 'r') as f:
            passwd_lines = f.readlines()
        existing_uids = []
        for line in passwd_lines:
            parts = line.strip().split(':')
            existing_uids.append(int(parts[2]))
            if parts[0] == inputs['username']:
                print(f"User {inputs['username']} already exists.")
                sys.exit(1)
        while uid in existing_uids:
            uid += 1
        gid = uid  # Use the same number for GID
        home_dir = f"/home/{inputs['username']}"
        shell = '/bin/bash'
        new_passwd_entry = f"{inputs['username']}:x:{uid}:{gid}:{inputs['username']}:{home_dir}:{shell}\n"
        with open(passwd_file, 'a') as f:
            f.write(new_passwd_entry)

        # 3.3 Set User Password
        user_hash = generate_password_hash(inputs['user_pwd'])
        with open(shadow_file, 'a') as f:
            f.write(f"{inputs['username']}:{user_hash}:{last_change}:0:99999:7:::\n")

        # 3.4 Update /etc/group
        group_file = os.path.join(mount_point, 'etc/group')
        with open(group_file, 'r') as f:
            group_lines = f.readlines()
        existing_gids = []
        group_dict = {}
        for line in group_lines:
            parts = line.strip().split(':')
            group_name, passwd, gid_str, members = parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ''
            existing_gids.append(int(gid_str))
            group_dict[group_name] = parts
        while gid in existing_gids:
            gid += 1
        # Update existing groups
        for group_name in ['sudo', 'adm', 'tty']:
            if group_name in group_dict:
                members = group_dict[group_name][3] if len(group_dict[group_name]) > 3 else ''
                if inputs['username'] not in members.split(','):
                    members = ','.join(filter(None, [members, inputs['username']]))
                    group_dict[group_name][3] = members
            else:
                # Create group if it doesn't exist
                group_dict[group_name] = [group_name, 'x', str(gid), inputs['username']]
                gid +=1
        # Add new user group
        group_dict[inputs['username']] = [inputs['username'], 'x', str(gid), '']
        # Rewrite the group file
        with open(group_file, 'w') as f:
            for group_info in group_dict.values():
                f.write(':'.join(group_info) + '\n')

        # 3.5 Update /etc/gshadow
        gshadow_file = os.path.join(mount_point, 'etc/gshadow')
        with open(gshadow_file, 'r') as f:
            gshadow_lines = f.readlines()
        gshadow_dict = {}
        for line in gshadow_lines:
            parts = line.strip().split(':')
            gshadow_dict[parts[0]] = parts
        for group_name in ['sudo', 'adm', 'tty']:
            if group_name in gshadow_dict:
                members = gshadow_dict[group_name][3]
                if inputs['username'] not in members.split(','):
                    members = ','.join(filter(None, [members, inputs['username']]))
                    gshadow_dict[group_name][3] = members
            else:
                gshadow_dict[group_name] = [group_name, '!', '', inputs['username']]
        # Add new user group to gshadow
        gshadow_dict[inputs['username']] = [inputs['username'], '!', '', '']
        # Rewrite the gshadow file
        with open(gshadow_file, 'w') as f:
            for gshadow_info in gshadow_dict.values():
                f.write(':'.join(gshadow_info) + '\n')

        # 3.6 Create Home Directory
        user_home = os.path.join(mount_point, 'home', inputs['username'])
        os.makedirs(user_home, exist_ok=True)
        os.chown(user_home, uid, gid)
        os.chmod(user_home, 0o755)

        # 3.7 Disable First Run Script
        fr_file = os.path.join(mount_point, 'root/.not_logged_in_yet')
        if os.path.exists(fr_file):
            os.remove(fr_file)
        fr_script = os.path.join(mount_point, 'etc/profile.d/armbian-check-first-login.sh')
        if os.path.exists(fr_script):
            os.remove(fr_script)

        # 3.8 Set Timezone
        timezone_file = os.path.join(mount_point, 'etc/timezone')
        with open(timezone_file, 'w') as f:
            f.write(inputs['timezone'] + '\n')

        # Create symlink for localtime
        localtime_path = os.path.join(mount_point, 'etc/localtime')
        zoneinfo_path = os.path.join('usr/share/zoneinfo', inputs['timezone'])
        full_zoneinfo_path = os.path.join(mount_point, zoneinfo_path)
        if os.path.exists(full_zoneinfo_path):
            if os.path.exists(localtime_path):
                os.remove(localtime_path)
            os.symlink(zoneinfo_path, localtime_path)
        else:
            print(f"Warning: Timezone file {zoneinfo_path} does not exist. Timezone may not be set correctly.")

        # 3.9 Set Locale
        locale_gen_path = os.path.join(mount_point, 'etc/locale.gen')
        with open(locale_gen_path, 'r') as f:
            lines = f.readlines()
        locale_found = False
        with open(locale_gen_path, 'w') as f:
            for line in lines:
                if inputs['locale'] in line:
                    f.write(inputs['locale'] + ' UTF-8\n')
                    locale_found = True
                else:
                    f.write(line)
            if not locale_found:
                f.write(inputs['locale'] + ' UTF-8\n')
        # Write /etc/default/locale
        default_locale_path = os.path.join(mount_point, 'etc/default/locale')
        with open(default_locale_path, 'w') as f:
            f.write(f'LANG="{inputs["locale"]}"\n')

        # 3.10 Configure WiFi
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

        # 3.11 Install blink_ip.sh script
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
echo "heartbeat" > /sys/class/leds/green_led/trigger # Wouldn't let me use $original_trigger as it is set somewhere else
""")  
        os.chmod(blink_script, 0o755)

        # 3.12 Create systemd service
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

        # Ensure correct permissions for /etc/shadow and /etc/passwd
        os.chmod(os.path.join(mount_point, 'etc/passwd'), 0o644)
        os.chown(os.path.join(mount_point, 'etc/passwd'), 0, 0)
        os.chmod(os.path.join(mount_point, 'etc/shadow'), 0o640)
        os.chown(os.path.join(mount_point, 'etc/shadow'), 0, 42)  # Group 'shadow' typically has GID 42

    finally:
        # Cleanup
        unmount_partitions(mount_point)

    print("Configuration complete. You can now insert the SD card into your Orange Pi Zero 2W and boot it.")

if __name__ == '__main__':
    main()
