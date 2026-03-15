"""
main.py
-------
HomeRing master script -- runs continuously on the Raspberry Pi.

How it works (step by step):
  1. The phone rings and the MT8870 chip picks up the caller ID tones
  2. This script reads the incoming phone number
  3. It sends the number to AWS IoT Core over the internet
  4. AWS looks up the number (blocklist, allowlist, unknown) and sends back a decision:
       "block"     -> immediately drop the call using the relay
       "allow"     -> do nothing, let the phone ring normally
       "challenge" -> play the "Press 5 to continue" message to the caller
  5. For the challenge:
       - If the caller presses 5, they pass and the call is allowed through
       - If they don't respond within 10 seconds, the call is blocked
  6. The script logs what happened and waits for the next call

To run this automatically when the Pi boots, add it to /etc/rc.local or use systemd.

Usage:
  python3 main.py

Dependencies:
  pip install RPi.GPIO AWSIoTPythonSDK pygame
"""

import time
import signal
import sys
import RPi.GPIO as GPIO

from caller_id  import read_phone_number
from relay      import setup as relay_setup, block_call, allow_call, cleanup as relay_cleanup
from aws_connect import AWSConnector
from audio      import run_challenge

# --- Configuration ---

# How long to wait between checking for new calls (seconds)
# The main loop polls continuously, but this small sleep prevents CPU overuse
LOOP_SLEEP = 0.1

# How long to hold the relay open (blocking the call) before resetting (seconds)
BLOCK_DURATION = 10

# GPIO pin connected to the ring detection circuit
# This pin goes HIGH when the phone is ringing
# If you don't have a ring detector, set this to None and the script will
# read caller ID tones continuously instead
RING_DETECT_PIN = 25


# --- Globals ---
aws = AWSConnector()
running = True   # Set to False by the shutdown handler to exit cleanly


def handle_shutdown(signum, frame):
    """
    Called automatically when the program is stopped (Ctrl+C or system shutdown).
    Cleans up GPIO and MQTT connections before exiting.
    """
    global running
    print("\n[Main] Shutdown signal received. Cleaning up...")
    running = False


def setup():
    """Initialize all hardware and connections at startup."""
    print("[Main] HomeRing starting up...")

    # Set up the relay (phone line control)
    relay_setup()

    # Set up ring detection pin (if wired)
    if RING_DETECT_PIN:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(RING_DETECT_PIN, GPIO.IN)

    # Connect to AWS IoT Core
    # This will fail if the Pi has no internet or certs are missing
    try:
        aws.connect()
    except Exception as e:
        print(f"[Main] WARNING: Could not connect to AWS: {e}")
        print("[Main] Running in offline mode -- all unknown calls will be allowed through.")

    print("[Main] Setup complete. Waiting for calls...\n")


def wait_for_ring():
    """
    Block until the phone starts ringing.
    If no ring detection pin is configured, returns immediately (always "ringing").
    """
    if not RING_DETECT_PIN:
        return   # No ring detector -- assume always ready

    print("[Main] Watching for ring signal on GPIO", RING_DETECT_PIN)
    while running:
        if GPIO.input(RING_DETECT_PIN) == GPIO.HIGH:
            print("[Main] Ring detected!")
            return
        time.sleep(0.05)


def handle_call():
    """
    Process a single incoming call from start to finish:
      1. Read the caller ID
      2. Ask AWS what to do
      3. Block, allow, or challenge based on the decision
    """
    print("[Main] ---- Incoming call ----")

    # Step 1: Read the caller's phone number from the MT8870 chip
    phone_number = read_phone_number()

    if not phone_number:
        print("[Main] Could not read caller ID. Allowing call through by default.")
        allow_call()
        return

    print(f"[Main] Caller number: {phone_number}")

    # Step 2: Send the number to AWS and wait for a decision
    try:
        decision = aws.send_and_wait(phone_number)
    except Exception as e:
        print(f"[Main] AWS error: {e}. Defaulting to 'allow'.")
        decision = "allow"

    print(f"[Main] Decision for {phone_number}: {decision}")

    # Step 3: Act on the decision
    if decision == "block":
        # The number is on the blocklist -- drop the call immediately
        print(f"[Main] BLOCKING call from {phone_number}.")
        block_call()
        time.sleep(BLOCK_DURATION)
        allow_call()
        print(f"[Main] Call from {phone_number} blocked and line restored.")

    elif decision == "challenge":
        # Unknown number -- give the caller a chance to prove they're human
        print(f"[Main] Challenging caller {phone_number}.")
        passed = run_challenge()

        if passed:
            print(f"[Main] {phone_number} passed the challenge. Allowing call.")
            allow_call()
        else:
            print(f"[Main] {phone_number} failed the challenge. Blocking call.")
            block_call()
            time.sleep(BLOCK_DURATION)
            allow_call()

    else:
        # Decision is "allow" (or anything unexpected -- default to safe/open)
        print(f"[Main] Allowing call from {phone_number}.")
        allow_call()

    print(f"[Main] Call handling complete.\n")


def main():
    """Main loop -- runs forever, processing one call at a time."""
    # Register the shutdown handler so Ctrl+C exits cleanly
    signal.signal(signal.SIGINT,  handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    setup()

    while running:
        try:
            # Wait for the phone to ring
            wait_for_ring()

            if running:
                # Handle the call (read ID, check with AWS, decide action)
                handle_call()

        except Exception as e:
            # Catch unexpected errors so the script doesn't crash between calls
            print(f"[Main] Unexpected error: {e}")
            allow_call()   # Safety: restore the phone line if something went wrong

        time.sleep(LOOP_SLEEP)

    # Cleanup when the loop exits
    relay_cleanup()
    aws.disconnect()
    GPIO.cleanup()
    print("[Main] HomeRing shut down cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
