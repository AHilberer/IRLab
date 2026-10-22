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

Each server loads its config file at startup (motors / FESTO) and opens the hardware.
If the hardware is missing (COM port absent, NI driver missing...), the server still
starts in degraded mode: `GET /status` reports the errors, and `POST /admin/reload_config`
retries once the problem is fixed.

Start interactive shell:

```bash
python IRLab_shell.py
```

The shell starts even if a server is not reachable (warning, then a summary of the
servers and objects loaded); start the missing server and run `reconnect()`.

Motor axes are **not** initialized at server startup (`initialize_on_startup: false` in
`config/motors.yaml`), because INIT can move them. After starting the motion server, run
`init_all()` once in the shell, watching the bench. Moves of non-initialized motors are refused.

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
	- `IRLAB_MOTORS_CONFIG`: motor config file loaded by the motion server (default: `config/motors.yaml`)
	- `IRLAB_FESTO_CONFIG`: config file loaded by the FESTO server (default: `config/festo.yaml`)
	- `IRLAB_LOG_DIR`: directory of the server log files (default: `logs/`)

## Logs

Each server writes its log to the console and to `logs/<server>.log` (`motion_server.log`,
`spectro_server.log`, `festo_server.log`) at the repository root, or in `$IRLAB_LOG_DIR`.
Files are rotated every night (`<server>.log.YYYY-MM-DD`) and kept one year.

- Every action (POST request) is logged when it starts and when it ends: client IP,
  endpoint, parameters, result or error, duration. Reads (GET) are not logged.
- `log_serial: true` in `config/motors.yaml` also logs every command sent to the PS90
  and its response (verbose, for diagnosis only).

## Main Endpoints

Actions that change the state of the bench use `POST` (a browser, a page refresh or a
link crawler cannot trigger them); reads use `GET`. All endpoints can be tried from
each server's `/docs` page.

### Motion server (port 8001)

- `GET /status` (JSON: version, config, controllers and their errors, motors)
- `GET /state`
- `GET /motors/list` (name, axis, controller, step_to_mm, unit, max_move_duration, state)
- `GET /motors/read/{motor}`
- `GET /controllers/list`, `GET /ps90/status`
- `POST /motors/move_abs/{motor}` body `{"position": <steps>}`
- `POST /motors/move_rel/{motor}` body `{"delta": <steps>}`
- `POST /motors/stop/{motor}`, `POST /motors/stop_all`
- `POST /motors/init/{motor}`
- `POST /motors/free/{motor}`, `POST /motors/control/{motor}`
- `POST /admin/reload_config`
- `POST /ps90/connect`, `POST /ps90/close` (debug / recovery)

### Spectrometer server (port 8002)

- `GET /status` (JSON: version, spectrometers and their state)
- `GET /state`
- `GET /spectro/list`
- `POST /acquire` body `{"exposure": <s>, "name": <optional spectrometer name>}`
- `POST /spectro/load_config`
- `POST /spectro/connect`, `POST /spectro/close`

### FESTO server (port 8003)

- `GET /status` (JSON: version, config, controllers and their errors, actuators)
- `GET /state`
- `GET /festo/actuators/list`, `GET /festo/controllers/list`
- `GET /festo/actuators/state/{actuator}`
- `POST /festo/actuators/on/{actuator}`, `POST /festo/actuators/off/{actuator}`, `POST /festo/actuators/toggle/{actuator}`
- `POST /admin/reload_config`
- `POST /festo/connect`, `POST /festo/close` (debug / recovery)

## Shell Helpers

In `IRLab_shell.py`, these are available directly:

- `mv(...)` move one or more motors
- `mvr(...)` move one or more motors relatively
- `wm(...)` read motor positions
- `free(...)` release one or more motors
- `control(...)` re-acquire control of one or more motors
- `free_all_motors()` release all registered motors
- `init(...)` / `init_all()` initialize motors (needed once after the motion server starts; INIT can move axes)
- `stop(...)` / `stop_all()` stop motors immediately
- `reconnect()` retry the servers that were not reachable and create the missing motor / actuator objects
- `check_all()` print the state of the three servers
- `ascan(motor, start, stop, npts)` linear scan
- `dscan(motor, start_delta, stop_delta, npts)` relative linear scan
- `tweak(m1[, m2[, m3]])` interactive keyboard jog mode
- `spec.acquire(...)` acquire spectrum
- `on(a1, a2, ...)` activate one or more FESTO actuators
- `off(a1, a2, ...)` deactivate one or more FESTO actuators
- `toggle(a1, a2, ...)` toggle one or more FESTO actuators
- `state(a1, a2, ...)` read on/off state from server
