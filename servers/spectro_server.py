from fastapi import FastAPI
import numpy as np
import time

app = FastAPI()

@app.get("/acquire")
def acquire(exposure: float = 0.1):
    # replace with the real Andor SDK acquisition call
    time.sleep(exposure)

    # fake spectrum
    x = np.linspace(0, 1000, 100)
    y = np.sin(x / 100) + np.random.rand(100) * 0.1

    return {
        "wavelength": x.tolist(),
        "intensity": y.tolist()
    }

@app.get("/status")
def status():
    return "This confirms connection to the spectro server."


    # launch with uvicorn servers.spectro_server:app --host 0.0.0.0 --port 8002