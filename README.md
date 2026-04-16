# IRLab

Control framework for an optical spectroscopy bench.

## What Is Included

- Motion server (FastAPI, PS90-based): `servers/motion_server.py`
- Spectrometer server (FastAPI, simulated): `servers/spectro_server.py`
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
```

Start interactive shell:

```bash
python IRLab_shell.py
```

## Configuration

- `config/servers.yaml`: default server URLs
- `config/motors.yaml`: controllers, motors, and optional motion parameters
- Environment overrides:
	- `MOTION_SERVER`
	- `SPECTRO_SERVER`

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
