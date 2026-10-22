# IRLab

Control framework for an optical spectroscopy bench.

## What Is Included

- Motion server (FastAPI, PS90-based): `servers/motion_server.py`
- Spectrometer server (FastAPI, Andor SDK2 + Shamrock-based): `servers/spectro_server.py`
- FESTO pneumatic server (FastAPI, NI-DAQmx-based): `servers/festo_server.py`
- Python clients: `clients/`
- Interactive shell: `IRLab_shell.py`

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run servers, each on its own PC (see [Network](#network)), from the repository root:

```powershell
.\start_motion.ps1
.\start_spectro.ps1
.\start_festo.ps1
```

Each script listens on all network interfaces (`--host 0.0.0.0`) and reads its
port from `config/servers.yaml`; `-Port <n>` overrides it. Equivalent manual command:

```bash
uvicorn servers.motion_server:app --host 0.0.0.0 --port 8001
```

Start interactive shell:

```bash
python IRLab_shell.py
```

## Network

The bench PCs are on an isolated local network; machine names are resolved by
the Windows `hosts` file of each PC (`C:\Windows\System32\drivers\etc\hosts`).
`config/servers.yaml` uses these names, never IP addresses.

| Server | Script | Runs on PC | Port | URL in `config/servers.yaml` |
|---|---|---|---|---|
| Motion (OWIS PS90) | `start_motion.ps1` | `pc-moteurs` (PC with the PS90 serial cable) | 8001 | `http://pc-moteurs:8001` |
| Spectrometer (Andor) | `start_spectro.ps1` | `pc-spectro` (PC with the Andor camera) | 8002 | `http://pc-spectro:8002` |
| FESTO (NI-DAQmx) | `start_festo.ps1` | `pc-moteurs` (PC with the NI cDAQ chassis) | 8003 | `http://pc-moteurs:8003` |

`pc-moteurs` and `pc-spectro` are example names: replace them in this table and
in `config/servers.yaml` with the real names of the bench PCs.

## Configuration

- `config/servers.yaml`: server URLs (machine names) and ports
- `config/motors.yaml`: controllers, motors, and optional motion parameters
- `config/festo.yaml`: NI-DAQ chassis and FESTO actuator channel mapping
- `config/spectro.yaml`: Andor camera / Shamrock spectrograph device indices per named spectrometer
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

- `GET /spectro/connect`
- `GET /spectro/close`
- `GET /spectro/load_config`
- `GET /spectro/list`
- `GET /acquire?exposure=0.1`
- `GET /status`
- `GET /state`

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
