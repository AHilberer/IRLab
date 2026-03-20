from fastapi import FastAPI
import time

app = FastAPI()

# simulated state
position = {"sx": 0.0}

@app.get("/move/{motor}/{pos}")
def move(motor: str, pos: float):
    # replace with real OWIS driver code here
    print(f"Moving {motor} to {pos}")
    time.sleep(0.1)  # simulate motion
    position[motor] = pos
    return {"status": "ok"}

@app.get("/read/{motor}")
def read(motor: str):
    return {"position": position.get(motor, 0.0)}

@app.get("/status")
def status():
    return "This confirms connection to the motion server."


## launch with 'uvicorn servers.motion_server:app --host 0.0.0.0 --port 8001'