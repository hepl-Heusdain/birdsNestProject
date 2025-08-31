from flask import Flask, send_from_directory, render_template
from paho.mqtt import client as mqtt_client
from werkzeug.utils import secure_filename
from datetime import datetime
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import os, gc, configparser, uuid

imageChunks = {}
totalChunks = None
config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))

imageDir = config.get('Directories', 'imageDir')
thumbDir = config.get('Directories', 'thumbDir')
print(f"Image directory: {imageDir}, Thumbnail directory: {thumbDir}")
clientId = f"rpi-{hex(uuid.getnode())}"
broker = config.get('MQTT', 'broker')
port = config.getint('MQTT', 'port')
topic = config.get('MQTT', 'topic')
username = config.get('MQTT', 'username')
passwd = config.get('MQTT', 'passwd')
print(f"MQTT Broker: {broker}, Port: {port}, Topic: {topic}, Client ID: {clientId}")

def main():
    os.makedirs(imageDir, exist_ok=True)
    os.makedirs(thumbDir, exist_ok=True)
    MQTTsetup()
    app.run(host="0.0.0.0", port=8000, threaded=True)



def thumbnails():
    for fname in os.listdir(imageDir):
        if fname.endswith(".jpg"):
            img_path = os.path.join(imageDir, fname)
            thumb_path = os.path.join(thumbDir, fname)
            if not os.path.exists(thumb_path):
                try:
                    with Image.open(img_path) as img:
                        w, h = img.size
                        min_side = min(w, h)
                        left = (w - min_side) // 2
                        top = (h - min_side) // 2
                        right = left + min_side
                        bottom = top + min_side
                        img_cropped = img.crop((left, top, right, bottom))
                        img_cropped = img_cropped.resize((250, 250), Image.LANCZOS)
                        img_cropped.save(thumb_path, "JPEG", quality=70)
                        print(f"Thumbnail created: {thumb_path}")
                except UnidentifiedImageError:
                    print(f"Could not create thumbnail for {img_path}")

                   

app = Flask(__name__)
@app.route("/")
def index():
    thumbnails()
    files_with_time = []
    for f in os.listdir(imageDir):
        path = os.path.join(imageDir, f)
        if os.path.isfile(path):
            ctime = os.path.getctime(path)
            files_with_time.append({"name": f, "time": ctime})
    files_with_time.sort(key=lambda x: x["time"], reverse=True)
    return render_template("index.html", files=files_with_time)

@app.route("/images/<path:filename>")
def images(filename):
    filename = secure_filename(filename)
    return send_from_directory(imageDir, filename)

@app.route("/thumbs/<path:filename>")
def thumbs(filename):
    filename = secure_filename(filename)
    return send_from_directory(thumbDir, filename)



def MQTTsetup():
    client = mqtt_client.Client(clientId)
    client.username_pw_set(username, passwd)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker")
            client.subscribe(topic)
        else:
            print(f"Failed to connect, return code {rc}")
    
    def on_message(client, userdata, msg):
        global totalChunks
        try:
            index_b, total_b, chunkData = msg.payload.split(b'|', 2)
            index = int(index_b)
            if totalChunks is None:
                totalChunks = int(total_b)
        except Exception as e:
            print(f"Error processing chunk: {e}")
            return
        imageChunks[index] = chunkData
        print(f"Received chunk {index+1}/{totalChunks}")

        if len(imageChunks) == totalChunks:
            imageData = None
            try:
                imageData = BytesIO(b''.join(imageChunks[i] for i in range(totalChunks)))
                imageData.seek(0)
                with Image.open(imageData) as img:
                    img.verify()
                    if(img.format != "JPEG"):
                        raise ValueError(f"Rejected image, format {img.format}")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(imageDir, f"{timestamp}.jpg")
                imageData.seek(0)
                with open(filename, 'wb') as f:
                    f.write(imageData.getbuffer())
                print(f"Image saved as {filename}")

            except Exception as e:
                print(f"Error processing image: {e}")
                return
            finally:
                totalChunks = None
                if imageData is not None:
                    imageData.close()
                    imageData = None
                imageChunks.clear()
                gc.collect()

    client.on_message = on_message
    client.on_connect = on_connect
    client.connect(broker, port)
    client.loop_start()
    return client

if __name__ == "__main__":
    main()