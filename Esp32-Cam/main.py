import esp32, ubinascii, camera, network, ujson # type: ignore
from simple import MQTTClient
from time import sleep, ticks_ms, ticks_diff
from machine import Pin, unique_id, deepsleep, wake_reason, PIN_WAKE # type: ignore

config = ujson.load(open('config.json'))

clientId = ubinascii.hexlify(unique_id())
broker = config['MQTT']['broker']
port = config['MQTT']['port']
topic = config['MQTT']['topic']
username = config['MQTT']['username']
passwd = config['MQTT']['passwd']

SSID = config['WLAN']['SSID']
PWD  = config['WLAN']['wlanPasswd']
WLAN = network.WLAN(network.STA_IF)

pirSensor = Pin(2, mode=Pin.IN)
LED = Pin(4, mode=Pin.OUT)

client = MQTTClient(clientId, broker, port=port, user=username, password=passwd)
esp32.wake_on_ext0(pin=pirSensor, level=esp32.WAKEUP_ANY_HIGH)

def main():
    if wake_reason() == PIN_WAKE:
        captureSend()
        while(pirSensor.value() == 1):
            sleep(0.2)
        sleep(2)
    print("Going to sleep")
    deepsleep()

def connect_wifi(timeout=10000, retries=2):
    attempt = 0
    while attempt < retries:
        if not WLAN.active():
            WLAN.active(True)
        try:
            scan = WLAN.scan()
            found = False
            for net in scan:
                if net[0].decode('utf-8') == SSID:
                    print(f"Found SSID {SSID}, RSSI {net[3]}")
                    found = True
                    break
            if not found:
                print(f"SSID {SSID} not found")
                raise Exception(f"SSID {SSID} not found in scan results")
            if not WLAN.isconnected():
                print(f"Connecting to WiFi, attempt {attempt + 1}...")
                WLAN.connect(SSID, PWD)
                start = ticks_ms()
                while not WLAN.isconnected():
                    if ticks_diff(ticks_ms(), start) > timeout:
                        print(f"attempt {attempt + 1} failed")
                        raise Exception(f"Connection attempt {attempt + 1} timed out")
                    sleep(0.2)
                if WLAN.isconnected():
                    print(f"Connected: {WLAN.ifconfig()}")
                    return True
        except Exception as e:
            print(f"Error connecting to WiFi: {e}")
        attempt += 1
        print(f"Attempting to reconnect to WiFi...")
    raise Exception(f"Failed to connect to WiFi after {retries} attempts, aborting ...")

# framesizes : 320x240 (QVGA), 640x480 (VGA), 800x600 (SVGA), 1600x1200 (UXGA)
def captureSend():
    LED.value(1)
    camera.init(0, format=camera.JPEG, fb_location=camera.PSRAM)
    camera.framesize(camera.FRAME_SVGA)
    camera.quality(4)
    img = camera.capture()
    LED.value(0)
    camera.deinit()

    chunkSize = 20000
    numChunks = len(img) // chunkSize + (1 if len(img) % chunkSize else 0)

    try:
        connect_wifi()
    except Exception as e:
        print(f"Error connecting to WiFi: {e}")
        return

    try:
        client.connect()
        for i in range(numChunks):
            start = i * chunkSize
            end = start + chunkSize
            header = b'%d|%d|' % (i, numChunks)
            payload = header + img[start:end]
            client.publish(topic, payload)
            sleep(0.1)
    except Exception as e:
        print(f"MQTT error: {e}")
    client.disconnect()

main()