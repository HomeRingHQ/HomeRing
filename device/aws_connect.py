import json
import time
import threading
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

AWS_ENDPOINT = "a1ihdxy8zxx9sa-ats.iot.us-east-1.amazonaws.com"
AWS_PORT = 8883
CLIENT_ID = "HomeRing-Pi"
PUBLISH_TOPIC = "homering/calls"
SUBSCRIBE_TOPIC = "homering/decisions"
CERT_PATH = "/home/pi/HomeRing/device/certs"
ROOT_CA = f"{CERT_PATH}/AmazonRootCA1.pem"
CERT_FILE = f"{CERT_PATH}/d04c49ca4d38b153fac0e62a3ab5f3d3e1389fe7166ebcb93c49c14a9de2d96c-certificate.pem.crt"
KEY_FILE = f"{CERT_PATH}/d04c49ca4d38b153fac0e62a3ab5f3d3e1389fe7166ebcb93c49c14a9de2d96c-private.pem.key"
DECISION_TIMEOUT = 10

class AWSConnector:
    def __init__(self):
        self._client = None
        self._last_decision = None
        self._decision_event = threading.Event()

    def connect(self):
        print("[AWS] Connecting to AWS IoT Core...")
        self._client = AWSIoTMQTTClient(CLIENT_ID)
        self._client.configureEndpoint(AWS_ENDPOINT, AWS_PORT)
        self._client.configureCredentials(ROOT_CA, KEY_FILE, CERT_FILE)
        self._client.configureAutoReconnectBackoffTime(1, 32, 20)
        self._client.configureOfflinePublishQueueing(-1)
        self._client.configureDrainingFrequency(2)
        self._client.configureConnectDisconnectTimeout(10)
        self._client.configureMQTTOperationTimeout(5)
        self._client.connect()
        print("[AWS] Connected!")
        self._client.subscribe(SUBSCRIBE_TOPIC, 1, self._on_decision_received)

    def _on_decision_received(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            decision = payload.get("decision", "allow").lower()
            self._last_decision = decision
            self._decision_event.set()
        except Exception as e:
            print(f"[AWS] Error: {e}")

    def send_and_wait(self, phone_number):
        self._last_decision = None
        self._decision_event.clear()
        payload = json.dumps({"phone_number": phone_number, "device_id": CLIENT_ID})
        self._client.publish(PUBLISH_TOPIC, payload, 1)
        print(f"[AWS] Sent {phone_number}")
        received = self._decision_event.wait(timeout=DECISION_TIMEOUT)
        if received:
            return self._last_decision
        else:
            return "allow"

    def disconnect(self):
        if self._client:
            self._client.disconnect()
