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

- `servers.yaml`: default server URLs
- `motors.yaml`: controllers, motors, and optional motion parameters
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

## Main Spectrometer Endpoints

- `GET /acquire?exposure=0.1`
- `GET /status`

## Shell Helpers

In `IRLab_shell.py`, these are available directly:

- `mv(...)` move one or more motors
- `wm(...)` read motor positions
- `ascan(motor, start, stop, npts)` linear scan
- `spec.acquire(...)` acquire spectrum
