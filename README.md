# IP-Blink-for-Armbian
An easy-to-use Python script that automates the setup of a freshly flashed Armbian image on an SD card for the Orange Pi Zero 2W before first boot. It configures user credentials, WiFi, locale, and displays the device's IP address by blinking the onboard LED using Roman numeral blink codes every time the system boots.

This is probably stupid if you already have admin access to the network or if your SBC supports armbian_first_run.txt in the boot folder. Might work on other SBCs but I haven't tested.

## Features

- Automates the Armbian first-run setup (root password, user creation).
- Configures WiFi for headless setup.
- Sets timezone and locale preferences.
- Blinks the last two octets of the assigned IP address using the onboard LED in Roman numerals.

## Prerequisites

- A Linux host machine with Python 3 installed. (Windows machines can use Virtualbox with Extensions installed. I use BookwormPup64 in a VM and it works for me, and may work on mac idk)
- An SD card with a FRESHLY flashed Armbian image for the Orange Pi Zero 2W. I use Rufus. Balena Etcher is fine too.
- The SD card plugged into host machine, not the Orange Pi.

## Usage

1. Download the python file on the linux host machine.
2. Navigate to and run the configurator script with administrative privileges.
   `sudo python3 configurator.py`
3. Follow the on-screen prompts to enter your desired settings:
   - Root password and user credentials.
   - WiFi SSID and password.
   - Timezone and locale.

After completing the setup, insert the SD card into your Orange Pi Zero 2W and power it on. The device will be configured with the options you entered.
Be Patient. First boot can take upwards of 3 minutes sometimes because of systemd-networkd-wait-online.service/start

## Understanding the LED Blink Codes

The onboard LED blinks out the last two octets of the device’s IP address using Roman numerals. If the subnet is 0, it doesn't get blinked. Each digit in an octet is blinked separately. 

### Blink Representation:

- Short blink (I): Represents 1.
- Medium blink (V): Represents 5.
- Long blink (X): Represents 10 or 0 (zero is represented by a long blink).

### Examples:

If the IP address assigned is `192.168.0.105`, the LED will blink:

- **I** (short blink) for 1.
- **X** (long blink) for 0.
- **V** (medium blink) for 5.

If the IP address assigned is `192.168.149.106`, the LED will blink:

- **I** (short blink) for 1.
- **IV** (short blink, medium blink) for 4.
- **IX** (short blink, long blink) for 9.
- (Short Pause)
- **I** (short blink) for 1.
- **X** (long blink) for 0.
- **VI** (medium blink, short blink) for 6.

The blinks are separated by short pauses, and each digit is separated by a longer pause.

### Special Case:

- If no IP address is assigned, the LED will blink `X` (long blink) three times, representing "000".

## Notes

- The IP address will be blinked ten times upon boot.
- After ten repetitions, the LED will return to its default behavior.

## Acknowledgements

This project was inspired by Matthias Wandel’s LED blink script for Raspberry Pi devices. His concept of using Roman numerals to display the IP address via LED was adapted and extended for the Orange Pi Zero 2W.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
