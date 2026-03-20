import requests

BASE_URL = "http://192.168.1.2:8002"

class Spectrometer:
    def acquire(self, exposure=0.1):
        r = requests.get(f"{BASE_URL}/acquire", params={"exposure": exposure})
        return r.json()

    def status(self):
        r = requests.get(f"{BASE_URL}/status")
        return r.text