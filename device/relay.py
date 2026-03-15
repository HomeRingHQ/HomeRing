"""
relay.py
--------
Controls the 5V relay module that physically opens and closes the phone line.

How it works:
  A relay is like an electrically-controlled switch. When we tell GPIO pin 18
  to go HIGH, it energizes a small electromagnet inside the relay, which flips
  a metal switch that disconnects the phone line -- blocking the call.
  When we set the pin LOW, the magnet turns off and the switch snaps back,
  reconnecting the phone line -- allowing the call through.

Wiring:
  Relay Module Pin  ->  Raspberry Pi
  IN (signal)       ->  GPIO 18
  VCC               ->  5V pin
  GND               ->  Ground pin

  Phone line wires connect to the relay's COM and NO (Normally Open) terminals:
    - COM = one wire of the phone line
    - NO  = other wire of the phone line
    When the relay is OFF (not blocking), COM and NO are disconnected.
    When the relay is ON  (blocking),     COM and NO are connected, shorting the line.

  NOTE: Exact wiring depends on whether your relay module is active-HIGH or active-LOW.
  Most common modules are active-HIGH (HIGH = relay ON). Adjust RELAY_ON below if needed.
"""

import RPi.GPIO as GPIO
import time

# --- Pin Definition ---
RELAY_PIN = 18

# Set this to GPIO.HIGH if your relay activates on HIGH (most common)
# Set this to GPIO.LOW  if your relay activates on LOW  (some modules)
RELAY_ON  = GPIO.HIGH
RELAY_OFF = GPIO.LOW


def setup():
    """Initialize the relay GPIO pin."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RELAY_PIN, GPIO.OUT)

    # Make sure the relay starts in the OFF (not blocking) state
    GPIO.output(RELAY_PIN, RELAY_OFF)
    print("[Relay] GPIO pin initialized. Relay is OFF (line open).")


def block_call():
    """
    Activate the relay to disconnect the phone line, blocking the call.
    This cuts the line so the caller hears nothing (or a busy signal).
    """
    GPIO.output(RELAY_PIN, RELAY_ON)
    print("[Relay] Relay ON -- phone line BLOCKED.")


def allow_call():
    """
    Deactivate the relay, reconnecting the phone line so the call can ring through.
    """
    GPIO.output(RELAY_PIN, RELAY_OFF)
    print("[Relay] Relay OFF -- phone line OPEN (call allowed).")


def pulse_block(duration_seconds=5):
    """
    Block the line for a set number of seconds, then allow it again.
    Useful for dropping a spam call after a brief delay.

    Arguments:
      duration_seconds -- how long to keep the line blocked (default: 5 seconds)
    """
    block_call()
    print(f"[Relay] Holding block for {duration_seconds} second(s)...")
    time.sleep(duration_seconds)
    allow_call()


def is_blocking():
    """
    Returns True if the relay is currently active (call is being blocked).
    """
    return GPIO.input(RELAY_PIN) == RELAY_ON


def cleanup():
    """Release the relay pin and make sure it's left in the OFF state."""
    allow_call()   # Safety: always restore line before releasing GPIO
    GPIO.cleanup()
    print("[Relay] GPIO cleaned up.")
