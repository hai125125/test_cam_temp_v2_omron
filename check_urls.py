import urllib.request
urls=['https://raw.githubusercontent.com/adafruit/Adafruit_MLX90640/master/Adafruit_MLX90640.cpp','https://raw.githubusercontent.com/adafruit/Adafruit_MLX90640/master/utility/Adafruit_MLX90640.cpp']
for u in urls:
    try:
        req=urllib.request.Request(u, method='HEAD')
        with urllib.request.urlopen(req, timeout=10) as r:
            print('URL', u, 'SIZE', len(r.read()))
    except Exception as e:
        print('MISS', u, type(e).__name__, e)
