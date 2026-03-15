"""
audio.py
--------
Plays an audio challenge message to the caller and listens for their response.

How it works:
  When a call is flagged as suspicious (but not definitively spam), HomeRing
  plays a short recorded message asking the caller to press 5 to continue.
  Real people can do this easily; robocallers almost never can.

  The message is played through the MAX98357A I2S digital amplifier, which
  receives audio from the Raspberry Pi over the I2S bus (a digital protocol
  that carries audio data cleanly without the noise of an analog signal).
  The amplifier converts the digital audio to an amplified analog signal
  and drives it onto the phone line so the caller can hear it.

  After playing the message, the script listens on the DTMF pins for up to
  RESPONSE_TIMEOUT seconds to see if the caller pressed 5.

  Returns:
    True  -- caller pressed 5 (likely human, allow the call)
    False -- no response or wrong digit (likely a robot, block the call)

Hardware setup (MAX98357A I2S amplifier -> Raspberry Pi 4):
  MAX98357A Pin  ->  Raspberry Pi GPIO (BCM numbering)
  -------------------------------------------------
  BCLK           ->  GPIO 18  (I2S bit clock)
  LRCLK          ->  GPIO 19  (I2S left/right word clock)
  DIN            ->  GPIO 21  (I2S data in)
  GND            ->  GND
  VIN            ->  5V

  These I2S pins are driven directly by the Raspberry Pi's hardware I2S
  controller -- you do NOT need to configure them in this script. Instead,
  enable the I2S driver once in /boot/config.txt by adding:

      dtoverlay=hifiberry-dac

  After a reboot, the MAX98357A will appear as an ALSA sound card and
  this script can send audio to it via the SDL/ALSA audio stack.

  To verify the card is recognised before running this script:
      aplay -l                        # should list a card like "sndrpihifiberry"
      aplay -D hw:0,0 challenge.wav   # quick playback test outside Python

Audio file:
  Place a file called challenge.wav in the same folder as this script.
  Record a message like: "This call is being screened. Please press 5 to continue."
  You can record this yourself using Audacity (free software) or any voice recorder.
  A mono, 44100 Hz, 16-bit WAV file works best with the settings below.

Dependencies:
  sudo apt-get install python3-pygame
  pip install RPi.GPIO
"""

import os
import time
import pygame
import RPi.GPIO as GPIO

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Path to the challenge audio file.
# It must live in the same folder as this script.
AUDIO_FILE = os.path.join(os.path.dirname(__file__), "challenge.wav")

# How many seconds to wait for the caller to press a digit after the message plays.
RESPONSE_TIMEOUT = 10

# The digit the caller must press to prove they're human.
MAGIC_DIGIT = '5'

# ALSA device name for the MAX98357A I2S amplifier.
# After enabling the hifiberry-dac overlay, the card usually appears as
# hw:0,0 (first card, first device). If you have other sound cards installed
# you may need to change this index -- run "aplay -l" to check.
I2S_ALSA_DEVICE = "hw:0,0"

# MT8870 DTMF decoder pins (BCM numbering).
# These are the same pins used by caller_id.py -- we reuse them here to
# read whichever digit the caller presses after hearing the challenge.
Q1_PIN  = 17   # Bit 0 (LSB) of the decoded DTMF digit
Q2_PIN  = 27   # Bit 1
Q3_PIN  = 22   # Bit 2
Q4_PIN  = 23   # Bit 3 (MSB)
STD_PIN = 24   # Strobe / Data Valid -- goes HIGH when a new digit is ready

# Maps the 4-bit binary value from Q1-Q4 to the corresponding digit character.
# This encoding is defined by the MT8870 datasheet.
DTMF_MAP = {
    1:  '1', 2:  '2', 3:  '3', 4:  '4',
    5:  '5', 6:  '6', 7:  '7', 8:  '8',
    9:  '9', 10: '0', 11: '*', 12: '#',
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_gpio():
    """Configure the DTMF input pins so we can read the caller's keypress."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # All five MT8870 output pins are inputs from the Pi's perspective.
    for pin in [Q1_PIN, Q2_PIN, Q3_PIN, Q4_PIN, STD_PIN]:
        GPIO.setup(pin, GPIO.IN)


def _read_digit_once():
    """
    Sample the DTMF pins once and return the digit that is currently present,
    or None if no valid digit is available right now.

    The MT8870 raises STD_PIN HIGH for as long as a tone is being decoded.
    While it is HIGH, Q1-Q4 hold the 4-bit value of the detected digit.
    """
    if GPIO.input(STD_PIN) == GPIO.HIGH:
        # Read the four data bits and combine them into a single integer.
        bit1 = GPIO.input(Q1_PIN)
        bit2 = GPIO.input(Q2_PIN)
        bit3 = GPIO.input(Q3_PIN)
        bit4 = GPIO.input(Q4_PIN)
        value = (bit4 << 3) | (bit3 << 2) | (bit2 << 1) | bit1
        return DTMF_MAP.get(value)
    return None


def _init_i2s_audio():
    """
    Point pygame's audio output at the MAX98357A I2S card via ALSA,
    then initialise the pygame mixer.

    SDL (the library underneath pygame) respects two environment variables
    to control which audio backend and device it uses:
      SDL_AUDIODRIVER=alsa  -- use ALSA instead of PulseAudio / auto-detect
      AUDIODEV=hw:0,0       -- the specific ALSA device to open

    We set these before calling pygame.mixer.init() so that all subsequent
    audio goes through the I2S amplifier rather than any other output.
    """
    os.environ["SDL_AUDIODRIVER"] = "alsa"
    os.environ["AUDIODEV"] = I2S_ALSA_DEVICE

    # frequency=44100  -- standard CD-quality sample rate
    # size=-16         -- 16-bit signed samples (most WAV files use this)
    # channels=1       -- mono; the MAX98357A is a mono amplifier
    # buffer=512       -- small buffer keeps latency low on the Pi
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
    print(f"[Audio] I2S audio initialised on ALSA device: {I2S_ALSA_DEVICE}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def play_challenge():
    """
    Play the challenge audio file through the MAX98357A I2S amplifier.

    The function blocks until the entire file has finished playing so that
    wait_for_response() is only called after the caller has heard the message.
    """
    if not os.path.exists(AUDIO_FILE):
        # A missing file is non-fatal -- the rest of call screening can still
        # proceed, but the caller won't hear any message.
        print(f"[Audio] WARNING: Audio file not found at {AUDIO_FILE}")
        print("[Audio] Skipping playback. Please add challenge.wav to the device folder.")
        return

    print("[Audio] Playing challenge message to caller over I2S...")

    # Set up pygame to output through the I2S amplifier.
    _init_i2s_audio()

    # Load the WAV file into the mixer and start playback.
    pygame.mixer.music.load(AUDIO_FILE)
    pygame.mixer.music.play()

    # Poll until the file is done -- this keeps the function synchronous so
    # the caller has heard the full message before we start watching for
    # their keypress.
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)

    pygame.mixer.music.unload()
    print("[Audio] Challenge message finished playing.")


def wait_for_response():
    """
    Listen on the DTMF pins for up to RESPONSE_TIMEOUT seconds.

    Returns True if the caller presses the correct digit (5), False if they
    press the wrong digit or don't respond before the timeout expires.
    """
    _setup_gpio()
    print(f"[Audio] Waiting up to {RESPONSE_TIMEOUT}s for caller to press {MAGIC_DIGIT}...")

    deadline = time.time() + RESPONSE_TIMEOUT

    while time.time() < deadline:
        digit = _read_digit_once()

        if digit:
            print(f"[Audio] Caller pressed: {digit}")

            if digit == MAGIC_DIGIT:
                print("[Audio] Correct digit -- caller is likely human.")
                return True
            else:
                print(f"[Audio] Wrong digit ({digit}) -- treating as robot.")
                return False

            # Wait for the STD strobe to go LOW before sampling again so we
            # don't read the same keypress multiple times.
            while GPIO.input(STD_PIN) == GPIO.HIGH:
                time.sleep(0.01)

        # Short sleep to avoid hammering the CPU between samples.
        time.sleep(0.05)

    print("[Audio] No response received -- treating as robot.")
    return False


def run_challenge():
    """
    Convenience function: play the challenge, then wait for the caller's response.

    Returns:
      True  -- caller passed the challenge (allow the call through)
      False -- caller failed or didn't respond (block the call)
    """
    play_challenge()
    return wait_for_response()
