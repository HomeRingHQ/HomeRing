"""
audio.py
--------
Plays an audio challenge message to the caller and listens for their response.

How it works:
  When a call is flagged as suspicious (but not definitively spam), HomeRing
  plays a short recorded message asking the caller to press 5 to continue.
  Real people can do this easily; robocallers almost never can.

  The message plays through the Pi's 3.5mm audio jack into the PAM8403 amplifier,
  which boosts the audio signal onto the phone line so the caller can hear it.

  After playing the message, the script then listens on the DTMF pins for up to
  RESPONSE_TIMEOUT seconds to see if the caller pressed 5.

  Returns:
    True  -- caller pressed 5 (likely human, allow the call)
    False -- no response or wrong digit (likely a robot, block the call)

Audio file:
  Place a file called challenge.wav in the same folder as this script.
  Record a message like: "This call is being screened. Please press 5 to continue."
  You can record this yourself using Audacity (free software) or any voice recorder.

Dependencies:
  sudo apt-get install python3-pygame
  pip install RPi.GPIO
"""

import time
import pygame
import os
import RPi.GPIO as GPIO

# --- Configuration ---

# Path to the audio file to play (must be a .wav or .mp3 file)
# Place challenge.wav in the same folder as this script
AUDIO_FILE = os.path.join(os.path.dirname(__file__), "challenge.wav")

# How many seconds to wait for the caller to press a digit after the message plays
RESPONSE_TIMEOUT = 10

# The digit the caller must press to prove they're human
MAGIC_DIGIT = '5'

# MT8870 DTMF pins -- same as in caller_id.py
# We reuse these to "listen" after playing the challenge
Q1_PIN  = 17
Q2_PIN  = 27
Q3_PIN  = 22
Q4_PIN  = 23
STD_PIN = 24

DTMF_MAP = {
    1:  '1', 2:  '2', 3:  '3', 4:  '4',
    5:  '5', 6:  '6', 7:  '7', 8:  '8',
    9:  '9', 10: '0', 11: '*', 12: '#',
}


def _setup_gpio():
    """Set up the DTMF input pins so we can listen for the caller's response."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in [Q1_PIN, Q2_PIN, Q3_PIN, Q4_PIN, STD_PIN]:
        GPIO.setup(pin, GPIO.IN)


def _read_digit_once():
    """
    Check if a digit has arrived on the DTMF pins right now.
    Returns the digit character if one is available, or None if not.
    """
    if GPIO.input(STD_PIN) == GPIO.HIGH:
        bit1 = GPIO.input(Q1_PIN)
        bit2 = GPIO.input(Q2_PIN)
        bit3 = GPIO.input(Q3_PIN)
        bit4 = GPIO.input(Q4_PIN)
        value = (bit4 << 3) | (bit3 << 2) | (bit2 << 1) | bit1
        return DTMF_MAP.get(value)
    return None


def play_challenge():
    """
    Play the challenge audio message over the phone line.
    Uses pygame to play the audio file through the Pi's audio jack.
    """
    if not os.path.exists(AUDIO_FILE):
        # If the audio file is missing, print a warning and skip playback.
        # This won't crash the program -- you'll just need to add the file later.
        print(f"[Audio] WARNING: Audio file not found at {AUDIO_FILE}")
        print("[Audio] Skipping playback. Please add challenge.wav to the device folder.")
        return

    print("[Audio] Playing challenge message to caller...")

    # Initialize pygame audio (only needs to happen once, but safe to repeat)
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

    # Load and play the file
    pygame.mixer.music.load(AUDIO_FILE)
    pygame.mixer.music.play()

    # Wait for the file to finish playing before we return
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)

    pygame.mixer.music.unload()
    print("[Audio] Challenge message finished playing.")


def wait_for_response():
    """
    After playing the challenge, listen for the caller to press a digit.

    Watches the DTMF pins for RESPONSE_TIMEOUT seconds.
    Returns True if the caller pressed the correct digit (5), False otherwise.
    """
    _setup_gpio()
    print(f"[Audio] Waiting up to {RESPONSE_TIMEOUT}s for caller to press {MAGIC_DIGIT}...")

    start = time.time()

    while time.time() - start < RESPONSE_TIMEOUT:
        digit = _read_digit_once()

        if digit:
            print(f"[Audio] Caller pressed: {digit}")

            if digit == MAGIC_DIGIT:
                print("[Audio] Correct digit! Caller is likely human.")
                return True
            else:
                print(f"[Audio] Wrong digit ({digit}). Treating as robot.")
                return False

            # Wait for STD pin to go LOW before checking again
            while GPIO.input(STD_PIN) == GPIO.HIGH:
                time.sleep(0.01)

        time.sleep(0.05)

    print("[Audio] No response received. Treating as robot.")
    return False


def run_challenge():
    """
    Convenience function: play the challenge message, then wait for a response.

    Returns:
      True  -- caller passed the challenge (allow the call)
      False -- caller failed or didn't respond (block the call)
    """
    play_challenge()
    return wait_for_response()
