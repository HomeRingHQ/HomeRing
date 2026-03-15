"""
aws_connect.py
--------------
Connects the Raspberry Pi to AWS IoT Core using MQTT.

How it works:
  MQTT is a lightweight messaging system used in IoT devices. Think of it like
  a walkie-talkie channel: the Pi "publishes" (sends) a phone number to AWS,
  and AWS "publishes" back a decision (block / allow / challenge) on a different
  channel. This script manages that two-way conversation.

  The Pi sends to:     homering/calls       (outgoing: "this number is calling")
  The Pi listens on:   homering/decisions   (incoming: "here's what to do")

Certificate files (required -- generated in AWS IoT Core console):
  certs/device.pem.crt   -- the Pi's identity certificate
  certs/private.pem.key  -- the Pi's private key (keep this secret!)
  certs/AmazonRootCA1.pem -- Amazon's root certificate (verifies AWS is really AWS)

Dependencies:
  pip install AWSIoTPythonSDK
"""

import json
import time
import threading
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

# --- AWS IoT Configuration ---
AWS_ENDPOINT   = "a1ihdxy8zxx9sa-ats.iot.us-east-1.amazonaws.com"
AWS_PORT       = 8883   # Standard MQTT over TLS port

# A unique name for this device -- AWS uses this to identify it
CLIENT_ID      = "HomeRing-Pi"

# MQTT topics
PUBLISH_TOPIC  = "homering/calls"       # We send phone numbers here
SUBSCRIBE_TOPIC = "homering/decisions"  # We receive block/allow decisions here

# Paths to the certificate files on the Pi
# Adjust these if your certs folder is somewhere else
CERT_PATH = "/home/pi/HomeRing/certs"
ROOT_CA   = f"{CERT_PATH}/AmazonRootCA1.pem"
CERT_FILE = f"{CERT_PATH}/device.pem.crt"
KEY_FILE  = f"{CERT_PATH}/private.pem.key"

# How long to wait for a decision from AWS before giving up (seconds)
DECISION_TIMEOUT = 10


class AWSConnector:
    """
    Handles the MQTT connection to AWS IoT Core.
    Create one instance of this at startup and reuse it for all calls.
    """

    def __init__(self):
        self._client = None
        self._last_decision = None       # Stores the most recent decision from AWS
        self._decision_event = threading.Event()  # Used to wait for a reply

    def connect(self):
        """
        Open the connection to AWS IoT Core.
        Call this once when the program starts.
        """
        print("[AWS] Connecting to AWS IoT Core...")

        # Create the MQTT client with our device ID
        self._client = AWSIoTMQTTClient(CLIENT_ID)
        self._client.configureEndpoint(AWS_ENDPOINT, AWS_PORT)

        # Point the client to our certificate files for secure authentication
        self._client.configureCredentials(ROOT_CA, KEY_FILE, CERT_FILE)

        # Connection settings -- these control retry behavior
        self._client.configureAutoReconnectBackoffTime(1, 32, 20)  # min, max, stable seconds
        self._client.configureOfflinePublishQueueing(-1)           # Queue messages if offline
        self._client.configureDrainingFrequency(2)                 # Drain queue at 2 Hz
        self._client.configureConnectDisconnectTimeout(10)         # 10 sec to connect
        self._client.configureMQTTOperationTimeout(5)              # 5 sec per operation

        self._client.connect()
        print("[AWS] Connected!")

        # Start listening for decisions from AWS right away
        self._client.subscribe(SUBSCRIBE_TOPIC, 1, self._on_decision_received)
        print(f"[AWS] Subscribed to '{SUBSCRIBE_TOPIC}'.")

    def _on_decision_received(self, client, userdata, message):
        """
        This function runs automatically whenever AWS sends a decision back.
        It parses the message and signals the waiting main thread.

        Expected message format (JSON):
          { "number": "8005551234", "decision": "block" }

        Possible decisions:
          "block"     -- hang up immediately
          "allow"     -- let the call ring through
          "challenge" -- play the Press 5 audio challenge
        """
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            decision = payload.get("decision", "allow").lower()
            number   = payload.get("number", "unknown")

            print(f"[AWS] Decision received for {number}: {decision}")

            self._last_decision = decision
            self._decision_event.set()   # Wake up anyone waiting in send_and_wait()

        except Exception as e:
            print(f"[AWS] Error parsing decision message: {e}")

    def send_number(self, phone_number):
        """
        Publish a phone number to AWS for lookup and decision.

        Arguments:
          phone_number -- string like "8005551234"
        """
        payload = json.dumps({
            "number": phone_number,
            "timestamp": time.time(),
            "device": CLIENT_ID
        })

        self._client.publish(PUBLISH_TOPIC, payload, 1)
        print(f"[AWS] Sent number {phone_number} to '{PUBLISH_TOPIC}'.")

    def send_and_wait(self, phone_number):
        """
        Send a phone number to AWS and wait for the decision to come back.

        Returns the decision string ("block", "allow", or "challenge").
        If no decision arrives within DECISION_TIMEOUT seconds, defaults to "allow"
        so we never accidentally block a legitimate call due to a connectivity issue.

        Arguments:
          phone_number -- string like "8005551234"
        """
        # Clear any leftover decision from a previous call
        self._last_decision = None
        self._decision_event.clear()

        # Send the number to AWS
        self.send_number(phone_number)

        # Wait up to DECISION_TIMEOUT seconds for a reply
        received = self._decision_event.wait(timeout=DECISION_TIMEOUT)

        if received:
            return self._last_decision
        else:
            print(f"[AWS] No decision received within {DECISION_TIMEOUT}s. Defaulting to 'allow'.")
            return "allow"

    def disconnect(self):
        """Close the MQTT connection cleanly."""
        if self._client:
            self._client.disconnect()
            print("[AWS] Disconnected from AWS IoT Core.")
