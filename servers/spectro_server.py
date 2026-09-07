from fastapi import FastAPI, HTTPException
import numpy as np
import time

from common.states import DeviceState

app = FastAPI()

# Overall spectrometer state (single device, no per-object registry like motion/festo).
state = DeviceState.OFF

@app.get("/acquire")
def acquire(exposure: float = 0.1):
    global state
    state = DeviceState.MOVING
    try:
        # replace with the real Andor SDK acquisition call
        time.sleep(exposure)

        # fake spectrum
        x = np.linspace(0, 1000, 100)
        y = np.sin(x / 100) + np.random.rand(100) * 0.1
    except Exception as e:
        state = DeviceState.FAULT
        raise HTTPException(status_code=500, detail=f'Acquisition failed: {e}')

    state = DeviceState.ON
    return {
        "wavelength": x.tolist(),
        "intensity": y.tolist()
    }

@app.get("/status")
def status():
    return "This confirms connection to the spectro server."


@app.get("/state")
def get_state():
    return {"state": state.value}


    # launch with uvicorn servers.spectro_server:app --host 0.0.0.0 --port 8002