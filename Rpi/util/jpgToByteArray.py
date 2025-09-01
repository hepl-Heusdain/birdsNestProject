import os, random
header = b'%d|%d|%d|' % (0, 1, random.randint(0, 100))
with open(os.path.join(os.path.dirname(__file__), "testImage.jpg"), "rb") as img:
    with open(os.path.join(os.path.dirname(__file__), "testImage"), "wb") as imgFile:
        imgFile.write(header + bytearray(img.read()))