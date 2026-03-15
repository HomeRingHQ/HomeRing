"""
caller_id.py
------------
Reads incoming phone numbers from the MT8870 DTMF decoder chip.

How it works:
  When a call comes in, the phone company sends the caller's number as a series
  of audio tones called DTMF. The MT8870 chip listens to those tones on the phone
  line and converts each digit into a 4-bit binary signal on its output pins.
  This script watches those pins, decodes each digit, and builds the full number.

Wiring:
  MT8870 Pin  ->  Raspberry Pi GPIO
  Q1          ->  GPIO 17   (least significant bit)
  Q2          ->  GPIO 27
  Q3          ->  GPIO 22
  Q4          ->  GPIO 23   (most significant bit)
  STD         ->  GPIO 24   (goes HIGH for a moment when a valid digit arrives)
"""

import RPi.GPIO as GPIO
import time

# --- Pin Definitions ---
# These are the four data pins that carry the digit as a binary number
Q1_PIN = 17   # bit 1 (value 1)
Q2_PIN = 27   # bit 2 (value 2)
Q3_PIN = 22   # bit 3 (value 4)
Q4_PIN = 23   # bit 4 (value 8)

# STD = "Strobe / Data Valid" -- pulses HIGH when the chip has a new digit ready
STD_PIN = 24

# How long to wait for a full phone number before giving up (in seconds)
READ_TIMEOUT = 10

# How many digits to collect before considering the number complete
# Most US numbers are 10 digits (area code + 7-digit number)
MAX_DIGITS = 10

# The MT8870 maps its 4-bit output to digits like this:
DTMF_MAP = {
    1:  '1',
    2:  '2',
    3:  '3',
    4:  '4',
    5:  '5',
    6:  '6',
    7:  '7',
    8:  '8',
    9:  '9',
    10: '0',
    11: '*',
    12: '#',
}


def setup():
    """Set up the GPIO pins so we can read from the MT8870."""
    GPIO.setmode(GPIO.BCM)   # Use Broadcom pin numbering (the GPIO numbers printed on pinout diagrams)
    GPIO.setwarnings(False)

    # Set all MT8870 output pins as inputs on the Pi side
    for pin in [Q1_PIN, Q2_PIN, Q3_PIN, Q4_PIN, STD_PIN]:
        GPIO.setup(pin, GPIO.IN)

    print("[CallerID] GPIO pins initialized.")


def _read_digit():
    """
    Read the current 4-bit value from the MT8870 data pins and return the digit.
    Returns None if the value doesn't map to a known digit.
    """
    # Read each bit -- GPIO.HIGH means the pin is at 3.3V (logic 1)
    bit1 = GPIO.input(Q1_PIN)  # value 1
    bit2 = GPIO.input(Q2_PIN)  # value 2
    bit3 = GPIO.input(Q3_PIN)  # value 4
    bit4 = GPIO.input(Q4_PIN)  # value 8

    # Combine the bits into a single number (binary to decimal)
    value = (bit4 << 3) | (bit3 << 2) | (bit2 << 1) | bit1

    return DTMF_MAP.get(value)  # Look up the digit; returns None if unknown


def read_phone_number():
    """
    Wait for and collect a full incoming phone number.

    This function blocks (waits) until it has collected MAX_DIGITS digits
    or the READ_TIMEOUT is reached, then returns whatever it has gathered.

    Returns the phone number as a string like "8005551234",
    or an empty string if nothing was received in time.
    """
    setup()
    digits = []
    start_time = time.time()

    print("[CallerID] Waiting for incoming caller ID tones...")

    while len(digits) < MAX_DIGITS:
        # Check if we've been waiting too long
        if time.time() - start_time > READ_TIMEOUT:
            print("[CallerID] Timeout reached.")
            break

        # Wait for the STD pin to go HIGH -- that means a new digit is ready
        if GPIO.input(STD_PIN) == GPIO.HIGH:
            digit = _read_digit()

            if digit and digit not in ('*', '#'):  # Skip non-numeric symbols
                digits.append(digit)
                print(f"[CallerID] Got digit: {digit}  (so far: {''.join(digits)})")

            # Wait for STD to go LOW again before watching for the next digit
            # This prevents reading the same digit multiple times
            while GPIO.input(STD_PIN) == GPIO.HIGH:
                time.sleep(0.01)

        time.sleep(0.005)  # Small pause to avoid hammering the CPU

    phone_number = ''.join(digits)
    print(f"[CallerID] Full number received: {phone_number}")
    return phone_number


def cleanup():
    """Release GPIO pins when we're done."""
    GPIO.cleanup()
    print("[CallerID] GPIO cleaned up.")
