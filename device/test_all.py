"""
test_all.py
-----------
Hardware verification script for HomeRing.

Run this after wiring everything together to confirm each component works
before running the full main.py script.

Each test is independent -- you can run them one at a time by commenting out
the ones you don't want in the run_all_tests() function at the bottom.

Usage:
  python3 test_all.py

What gets tested:
  1. Relay     -- toggles the relay ON and OFF so you can hear it click
  2. Caller ID -- waits for you to dial a digit and shows what it received
  3. Audio     -- plays the challenge.wav file through the speaker
  4. AWS       -- connects to AWS IoT Core and sends a test message
  5. Full flow -- simulates a complete call with a fake number

IMPORTANT: Run this with the phone line DISCONNECTED from the relay during
initial testing to avoid accidentally affecting real calls.
"""

import time
import RPi.GPIO as GPIO

# ---- Colours for terminal output (makes pass/fail easier to read) ----
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def passed(msg): print(f"{GREEN}  [PASS] {msg}{RESET}")
def failed(msg): print(f"{RED}  [FAIL] {msg}{RESET}")
def info(msg):   print(f"{YELLOW}  [INFO] {msg}{RESET}")


# =============================================================================
# TEST 1: Relay
# =============================================================================

def test_relay():
    """
    Test the relay by turning it on and off.

    What to expect:
      You should hear TWO audible clicks from the relay module --
      one when it activates (ON) and one when it deactivates (OFF).
      If you have a multimeter, you can also measure continuity across
      the COM and NO terminals: they should connect when ON and open when OFF.
    """
    print("\n[Test 1] RELAY")
    print("  Turning relay ON (you should hear a click)...")

    try:
        import relay
        relay.setup()

        relay.block_call()
        time.sleep(1)   # Hold for 1 second so you can hear/measure it

        print("  Turning relay OFF (second click)...")
        relay.allow_call()
        time.sleep(0.5)

        passed("Relay toggled without errors.")
        print("  --> Did you hear two clicks? If yes, relay is wired correctly.")

    except Exception as e:
        failed(f"Relay test error: {e}")
    finally:
        GPIO.cleanup()


# =============================================================================
# TEST 2: Caller ID (MT8870)
# =============================================================================

def test_caller_id():
    """
    Test the MT8870 DTMF decoder.

    What to expect:
      The script will wait for you to send a DTMF tone.
      Use a phone or a DTMF tone generator app on your smartphone to dial
      a single digit into the phone line. The script should print that digit.

      If nothing happens, check:
        - MT8870 Q1-Q4 and STD pins are connected to the correct GPIO pins
        - MT8870 is powered (3.3V or 5V depending on your module)
        - The tone is actually reaching the MT8870 (check phone line connection)
    """
    print("\n[Test 2] CALLER ID (MT8870 DTMF decoder)")
    info("Waiting 10 seconds for a DTMF tone. Dial any digit on the phone line now...")

    try:
        import caller_id

        # We'll do a quick 10-second listen for a single digit
        caller_id.setup()
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        from caller_id import STD_PIN, DTMF_MAP, Q1_PIN, Q2_PIN, Q3_PIN, Q4_PIN

        start = time.time()
        digit_received = None

        while time.time() - start < 10:
            if GPIO.input(STD_PIN) == GPIO.HIGH:
                bit1 = GPIO.input(Q1_PIN)
                bit2 = GPIO.input(Q2_PIN)
                bit3 = GPIO.input(Q3_PIN)
                bit4 = GPIO.input(Q4_PIN)
                value = (bit4 << 3) | (bit3 << 2) | (bit2 << 1) | bit1
                digit_received = DTMF_MAP.get(value, f"unknown ({value})")
                break
            time.sleep(0.005)

        if digit_received:
            passed(f"Received digit: {digit_received}")
        else:
            failed("No DTMF tone received within 10 seconds.")
            print("  --> Check MT8870 wiring and that a tone source is connected.")

    except Exception as e:
        failed(f"Caller ID test error: {e}")
    finally:
        GPIO.cleanup()


# =============================================================================
# TEST 3: Audio Playback
# =============================================================================

def test_audio():
    """
    Test audio playback through the PAM8403 amplifier.

    What to expect:
      The challenge.wav file should play through your speaker.
      If you hear nothing, check:
        - Pi audio output is set to the 3.5mm jack (run: sudo raspi-config -> Audio)
        - Speaker/amplifier is powered and volume is up
        - challenge.wav exists in the same folder as this script

      If challenge.wav doesn't exist yet, this test will warn you but not crash.
    """
    print("\n[Test 3] AUDIO PLAYBACK")

    try:
        import os
        audio_file = os.path.join(os.path.dirname(__file__), "challenge.wav")

        if not os.path.exists(audio_file):
            failed(f"challenge.wav not found at: {audio_file}")
            print("  --> Create this file and re-run the test.")
            return

        info("Playing challenge.wav now...")

        import pygame
        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.unload()
        passed("Audio file played without errors.")
        print("  --> Did you hear the audio? If yes, speaker is wired correctly.")

    except Exception as e:
        failed(f"Audio test error: {e}")


# =============================================================================
# TEST 4: AWS IoT Core Connection
# =============================================================================

def test_aws():
    """
    Test the connection to AWS IoT Core.

    What to expect:
      The script will connect to AWS and publish a test message to homering/calls.
      Check your AWS IoT Core console -> Test -> MQTT test client to see if
      the message arrives.

      If the connection fails, check:
        - Pi has an active internet connection (ping google.com)
        - Certificate files exist in the certs/ folder
        - The AWS endpoint in aws_connect.py matches your account's endpoint
        - The IoT policy attached to the certificate allows publish/subscribe
    """
    print("\n[Test 4] AWS IoT CORE CONNECTION")

    try:
        from aws_connect import AWSConnector

        info("Connecting to AWS IoT Core...")
        connector = AWSConnector()
        connector.connect()
        passed("Connected to AWS IoT Core.")

        info("Publishing test message to homering/calls...")
        connector.send_number("0000000000")   # Fake number for testing
        passed("Test message published.")

        info("Waiting 5 seconds for a decision to come back (optional)...")
        import threading
        event = threading.Event()
        event.wait(timeout=5)

        connector.disconnect()
        passed("Disconnected cleanly.")
        print("  --> Check AWS IoT console to confirm message was received.")

    except Exception as e:
        failed(f"AWS test error: {e}")
        print("  --> Check certs folder, internet connection, and AWS endpoint.")


# =============================================================================
# TEST 5: Full Call Simulation
# =============================================================================

def test_full_flow():
    """
    Simulate a complete call using a fake phone number.

    This test does NOT use the actual phone line or MT8870 -- it injects
    a fake number directly to test the AWS + relay logic end to end.

    What to expect:
      A fake number "5551234567" is sent to AWS.
      Whatever decision comes back (or the default "allow") is acted upon.
      The relay will click if the decision is "block" or "challenge" fails.
    """
    print("\n[Test 5] FULL FLOW SIMULATION (fake number: 5551234567)")

    try:
        import relay
        from aws_connect import AWSConnector

        relay.setup()

        connector = AWSConnector()
        info("Connecting to AWS...")

        try:
            connector.connect()
            info("Sending fake number to AWS and waiting for decision...")
            decision = connector.send_and_wait("5551234567")
        except Exception as e:
            info(f"AWS unavailable ({e}). Using default decision: allow")
            decision = "allow"

        print(f"  Decision received: {decision}")

        if decision == "block":
            info("Simulating block: relay ON for 3 seconds...")
            relay.block_call()
            time.sleep(3)
            relay.allow_call()
            passed("Block simulation complete.")

        elif decision == "challenge":
            info("Simulating challenge flow...")
            from audio import run_challenge
            result = run_challenge()
            print(f"  Challenge result: {'passed' if result else 'failed'}")
            passed("Challenge simulation complete.")

        else:
            info("Decision is 'allow' -- no relay action needed.")
            passed("Allow simulation complete.")

        try:
            connector.disconnect()
        except Exception:
            pass

    except Exception as e:
        failed(f"Full flow simulation error: {e}")
    finally:
        GPIO.cleanup()


# =============================================================================
# Run all tests
# =============================================================================

def run_all_tests():
    """
    Run every hardware test in sequence.
    Comment out any tests you want to skip.
    """
    print("=" * 60)
    print("  HomeRing Hardware Test Suite")
    print("  Run after assembly to verify all wiring is correct.")
    print("=" * 60)

    test_relay()       # Test 1: Relay click
    test_caller_id()   # Test 2: MT8870 DTMF reading
    test_audio()       # Test 3: Audio playback
    test_aws()         # Test 4: AWS IoT connection
    test_full_flow()   # Test 5: End-to-end simulation

    print("\n" + "=" * 60)
    print("  All tests complete.")
    print("  Fix any [FAIL] items above before running main.py.")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
