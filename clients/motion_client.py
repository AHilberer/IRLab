import requests

BASE_URL = "http://192.168.1.2:8001"

class Motor:
    def __init__(self, name):
        self.name = name

    def move(self, pos):
        requests.get(f"{BASE_URL}/move/{self.name}/{pos}")

    def read(self):
        r = requests.get(f"{BASE_URL}/read/{self.name}")
        return r.json()["position"]

    def status(self):
        r = requests.get(f"{BASE_URL}/status")
        return r.text