# IRLab

Control framework for an optical spectroscopy bench.

## What Is Included

- Motion server (FastAPI, PS90-based): `servers/motion_server.py`
- Spectrometer server (FastAPI, simulated): `servers/spectro_server.py`
- FESTO pneumatic server (FastAPI, NI-DAQmx-based): `servers/festo_server.py`
- Python clients: `clients/`
- Interactive shell: `IRLab_shell.py`

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run servers:

```bash
uvicorn servers.motion_server:app --host 0.0.0.0 --port 8001
uvicorn servers.spectro_server:app --host 0.0.0.0 --port 8002
uvicorn servers.festo_server:app --host 0.0.0.0 --port 8003
```

Start interactive shell:

```bash
python IRLab_shell.py
```

## Configuration

- `config/servers.yaml`: default server URLs
- `config/motors.yaml`: controllers, motors, and optional motion parameters
- `config/festo.yaml`: NI-DAQ chassis and FESTO actuator channel mapping
- Environment overrides:
	- `MOTION_SERVER`
	- `SPECTRO_SERVER`
	- `FESTO_SERVER`
	- `FESTO_CHASSIS` (default: `cDAQ1`)

## Main Motion Endpoints

- `GET /ps90/connect`
- `GET /ps90/close`
- `GET /ps90/load_config`
- `GET /motors/list`
- `GET /motors/init/{motor}`
- `GET /motors/read/{motor}`
- `GET /motors/move_abs/{motor}/{position}`
- `GET /motors/move_rel/{motor}/{delta}`
- `GET /motors/free/{motor}`
- `GET /motors/control/{motor}`

## Main Spectrometer Endpoints

- `GET /acquire?exposure=0.1`
- `GET /status`

## Main FESTO Endpoints

- `GET /festo/connect`
- `GET /festo/close`
- `GET /festo/load_config`
- `GET /festo/controllers/list`
- `GET /festo/actuators/list`
- `GET /festo/actuators/register`
- `GET /festo/actuators/on/{actuator}`
- `GET /festo/actuators/off/{actuator}`
- `GET /festo/actuators/toggle/{actuator}`
- `GET /festo/actuators/state/{actuator}`

## Shell Helpers

In `IRLab_shell.py`, these are available directly:

- `mv(...)` move one or more motors
- `mvr(...)` move one or more motors relatively
- `wm(...)` read motor positions
- `free(...)` release one or more motors
- `control(...)` re-acquire control of one or more motors
- `free_all_motors()` release all registered motors
- `ascan(motor, start, stop, npts)` linear scan
- `dscan(motor, start_delta, stop_delta, npts)` relative linear scan
- `tweak(m1[, m2[, m3]])` interactive keyboard jog mode
- `spec.acquire(...)` acquire spectrum
- `on(a1, a2, ...)` activate one or more FESTO actuators
- `off(a1, a2, ...)` deactivate one or more FESTO actuators
- `toggle(a1, a2, ...)` toggle one or more FESTO actuators
- `state(a1, a2, ...)` read on/off state from server
