import esp32, ubinascii, camera, network, ujson, urandom, ntptime # type: ignore
from simple import MQTTClient
from time import sleep, ticks_ms, ticks_diff, localtime
from machine import Pin, unique_id, deepsleep, wake_reason, EXT0_WAKE, TIMER_WAKE # type: ignore

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
    wakeReason = wake_reason()
    if wakeReason == 0:
        try:
            connect_wifi(timeout=20, retries=5)
        except Exception as e:
            print(f"Error connecting to WiFi: {e}")
            return
        ntptime.settime()
        sendBatteryPercentage()
    elif wakeReason == EXT0_WAKE:
        captureSend()
        while(pirSensor.value() == 1):
            sleep(0.2)
        sleep(2)
    elif wakeReason == TIMER_WAKE:
        try:
            connect_wifi()
        except Exception as e:
            print(f"Error connecting to WiFi: {e}")
            return
        sendBatteryPercentage()

    print("Going to sleep")
    deepsleep(timeUntilMidnight())

def sendBatteryPercentage():
    try:
        client.connect()
        client.publish(topic, b'%d|%d|%d|%d' % (0, 0, urandom.randint(0, 100), 0))
        sleep(0.1)
        client.disconnect()
    except Exception as e:
        print(f"MQTT error: {e}")

def timeUntilMidnight():
    t = localtime()
    msUntilMidnight = ((23 - t[3]) * 3600 + (59 - t[4]) * 60 + (60 - t[5])) * 1000
    print(f"Milliseconds until midnight: {msUntilMidnight}")
    return msUntilMidnight

def connect_wifi(timeout=10000, retries=3):
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
#    camera.quality(5)
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
        battery = urandom.randint(0, 100)
        for i in range(numChunks):
            start = i * chunkSize
            end = start + chunkSize
            header = b'%d|%d|%d|' % (i, numChunks, battery)
            payload = header + img[start:end]
            client.publish(topic, payload)
            sleep(0.1)
    except Exception as e:
        print(f"MQTT error: {e}")
    client.disconnect()

main()