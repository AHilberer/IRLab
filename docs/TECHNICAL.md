# IRLab: technical documentation

Complements the [README](../README.md) (architecture, installation, shell commands).

## Contents

- [Installation details](#installation-details)
- [Firewall](#firewall)
- [Starting the servers](#starting-the-servers)
- [Starting the shell](#starting-the-shell)
- [Optional: automatic start with Windows](#optional-automatic-start-with-windows)
- [Configuration](#configuration)
- [Environment variables](#environment-variables)
- [Shell commands: details](#shell-commands-details)
- [Server endpoints](#server-endpoints)
- [Logs](#logs)
- [Points to check on the hardware](#points-to-check-on-the-hardware)
- [Upgrading from the previous version](#upgrading-from-the-previous-version)
- [Tests](#tests)

## Installation details

- The FESTO chassis name (`cDAQ1`) is the one shown in NI MAX.
- The spectrometer server needs the Python packages `pyAndorSDK2` and
  `pyAndorSpectrograph`, installed with the Andor SDKs.
- **Offline installation**: the bench network has no Internet access. Installing from
  downloaded wheels is not scripted yet (planned: fixed versions in `requirements.txt`,
  `tools/download_wheels.ps1` and `tools/install_offline.ps1`). Meanwhile, keep a copy
  of a working `.venv`, and note its versions with `.\.venv\Scripts\python.exe -m pip freeze`.

## Firewall

On the server PCs, ports 8001 to 8003 must be open for incoming connections, only
from the bench subnet (PowerShell as administrator, replace `<subnet>`, e.g. `192.168.1.0`):

```powershell
New-NetFirewallRule -DisplayName "IRLab servers" -Direction Inbound -Protocol TCP -LocalPort 8001-8003 -RemoteAddress <subnet>/24 -Action Allow
```

## Starting the servers

On each server PC (see the table of the README):

```powershell
.\start_motion.ps1        # pc-moteurs
.\start_festo.ps1         # pc-moteurs
.\start_spectro.ps1       # pc-spectro
```

The scripts can be launched from any folder. They check that `.venv` exists, then run
`python -m uvicorn` with the Python of `.venv` (no activation needed), listening on all
network interfaces with the port of `config/servers.yaml` (`-Port <n>` overrides it).
If PowerShell refuses to run scripts:
`powershell -ExecutionPolicy Bypass -File .\start_motion.ps1`.
Stop a server with Ctrl+C in its window: moving axes are stopped and ports are closed.

The motion and FESTO servers load their config file at startup and open the hardware.
If the hardware is missing (COM port absent, NI driver missing...), the server still
starts in **degraded mode**: `GET /status` reports the errors, and
`POST /admin/reload_config` retries once the problem is fixed (from the `/docs` page of
the server, for example). The spectrometer server connects the camera when the shell
asks it (`POST /spectro/load_config`, sent at each shell start and by `reconnect()`).

Only one instance of each server may run: a second motion server reports that the COM
port is already in use.

## Starting the shell

```powershell
.\.venv\Scripts\python.exe IRLab_shell.py
```

The shell starts even if a server is not reachable (warning, then a summary of the
servers and objects loaded); start the missing server, then run `reconnect()`.

After starting the motion server, run `init_all()` once in the shell: it initializes
the axes (INIT powers the motors and activates their position control loop; the axes
do not move). Moves of non-initialized motors are refused. Automatic initialization at
server startup can be enabled with `initialize_on_startup: true` in `config/motors.yaml`.

## Optional: automatic start with Windows

Not set up by default. Two possibilities, for each server PC:

**Scheduled task**, started when the bench user logs on, so that the server window
stays visible (PowerShell as administrator, adapt the path and the script):

```powershell
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\IRLab\start_motion.ps1"'
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName 'IRLab motion server' -Action $action -Trigger $trigger
```

Remove it with `Unregister-ScheduledTask -TaskName 'IRLab motion server'`.

**Windows service with [NSSM](https://nssm.cc)** (runs without logged-on user; the
output is then only in the log files):

```powershell
nssm install IRLabMotion C:\IRLab\.venv\Scripts\python.exe "-m uvicorn servers.motion_server:app --host 0.0.0.0 --port 8001"
nssm set IRLabMotion AppDirectory C:\IRLab
nssm start IRLabMotion
```

## Configuration

- `config/servers.yaml`: server URLs (machine names) and ports.
- `config/motors.yaml`: PS90 controllers (serial port, timeouts), motors (axis, `unit`,
  `step_to_mm`, velocity, acceleration, `max_move_duration`, `position_tolerance_steps`),
  `initialize_on_startup`, `log_serial`. The fields are described at the top of the file.
- `config/festo.yaml`: NI-DAQ chassis and FESTO actuator channel mapping.
- `config/spectro.yaml`: Andor camera / Shamrock spectrograph device indices per named spectrometer.

The motion and FESTO servers read their configuration at startup: restart the server
after changing it (`POST /admin/reload_config` only retries what failed).

## Environment variables

| Variable | Used by | Meaning (default) |
|---|---|---|
| `MOTION_SERVER`, `SPECTRO_SERVER`, `FESTO_SERVER` | shell, clients, start scripts | server URLs (`config/servers.yaml`) |
| `IRLAB_MOTORS_CONFIG` | motion server | motor config file (`config/motors.yaml`) |
| `IRLAB_FESTO_CONFIG` | FESTO server | FESTO config file (`config/festo.yaml`) |
| `IRLAB_LOG_DIR` | servers | log directory (`logs/`) |
| `FESTO_CHASSIS` | FESTO server | chassis when not set in the config (`cDAQ1`) |
| `PS90_PORT` | motion server | serial port when not set in the config (none) |

## Shell commands: details

- **Units**: positions given to `mv` / `mvr` and returned by `m.position()` are always
  in the motor's `unit` (`config/motors.yaml`), so `mv(m, 2)` and `mv(m, 2.0)` are the
  same. `step_to_mm` is the size of one step in that unit. `wm()` returns
  `{'steps': ..., 'mm': ...}` per motor, for display.
- **Errors**: a failed move raises `MotionError`, with the target, the reached
  position and the axis state; the remaining motors of the `mv` are not moved.
  `mv(..., raise_on_error=False)` returns the errors in the results list instead.
  A move on a motor already moving raises `MotorBusyError`.
- **Timeouts**: `mv` / `mvr` wait for the motor's `max_move_duration` (120 s by default)
  plus 30 s; `timeout=<s>` or `timeout=None` (no limit) override it.
  `spec.acquire(exposure)` waits for the exposure plus 10 s.
- **Ctrl+C** in `mv`, `mvr`, `ascan`, `dscan` and `tweak` stops the motors involved.
  While a move request is running, Windows may only handle Ctrl+C at the end of the
  move: use `stop()` / `stop_all()` from another shell.
- **Scans**: after an error or Ctrl+C, the motor is left where it stopped (not returned
  to its initial position), and the point reached is printed.
- **Names**: a motor or actuator is not exposed by its name if that name would overwrite
  a shell command or is not a valid Python name (a warning is printed); it is always
  available as `motors['...']` / `actuators['...']`.
- **Not available yet**: acquisition and HDF5 saving during scans (`ascan` / `dscan`
  only move the motor), `sync_data()`, simultaneous moves in `mv` (motors move one
  after the other).

## Server endpoints

Actions that change the state of the bench use `POST` (a browser, a page refresh or a
link crawler cannot trigger them); reads use `GET`. All endpoints can be tried from
each server's `/docs` page.

### Motion server (port 8001)

- `GET /status` (JSON: version, config, controllers and their errors, motors)
- `GET /state`
- `GET /motors/list` (name, axis, controller, step_to_mm, unit, max_move_duration, state)
- `GET /motors/read/{motor}`
- `GET /motors/parameters/{motor}` (mode, velocity, acceleration, counters read from the PS90)
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

## Logs

Each server writes its log to the console and to `logs/<server>.log` (`motion_server.log`,
`spectro_server.log`, `festo_server.log`) at the repository root, or in `$IRLAB_LOG_DIR`.
Files are rotated every night (`<server>.log.YYYY-MM-DD`) and kept one year.

- Every action (POST request) is logged when it starts and when it ends: client IP,
  endpoint, parameters, result or error, duration. Reads (GET) are not logged.
- `log_serial: true` in `config/motors.yaml` also logs every command sent to the PS90
  and its response (verbose, for diagnosis only).

## Points to check on the hardware

The PS90 protocol details come from the PS 90+ user manual; the older PS90 of the
bench is assumed to behave the same. To be confirmed on the bench:

| Point | Where | What to check |
|---|---|---|
| Response terminator | `servers/motion_server.py:65` (`PS90_TERMINATOR`) | `CR` (PS90 setting `COMEND=0`; CR+LF also works, LF alone does not). Visible with `log_serial: true`. |
| Command processing time | `servers/motion_server.py:70` (`PS90_DEFAULT_COMMAND_DELAY`) | 0.05 s after each command without response (manual: 20 to 40 ms). |
| "OK" acknowledgements | `servers/motion_server.py:73` (`PS90_ACK`) | Terminal mode `TERM`: 0 is the safest; with 2 the "OK" are skipped. |
| Axis stop | `servers/motion_server.py:76` (`PS90_STOP_AXIS_CMD`) | `STOP<n>` decelerates and halts the axis. |
| General stop | `servers/motion_server.py:81` (`PS90_STOP_ALL_CMD`) | Not used: `stop_all` stops each registered axis (`MSTOP` mask format depends on `TERM`). |
| Motion states | `servers/motion_server.py:84` (`PS90_MOVING_STATES`) | `?ASTAT` letters meaning "moving" (T, S, V, P, F, W, X, Y, C, N). |
| INIT | `servers/motion_server.py:230` (`initialize_axis`) | INIT does not move the axis (manual: powers the motor, the reference run is `REF`). |
| Units | `config/motors.yaml` (`unit`, `step_to_mm`) | `faty`, `focdy`, `focuy` are in steps: check if they should be in mm or deg. |
| Serial port | `config/motors.yaml:31` | `COM25` is the PS90 port on the motion PC. |
| Shamrock import | `servers/spectro_server.py:22` | Import path / class name of the Shamrock SDK. |
| Camera index | `servers/spectro_server.py:63` | `camera_index` is not passed to the SDK: only one Andor camera is supported. |
| NI-DAQmx read-back | `servers/festo_server.py:84` | Reading the state of DO lines through a new task does not change the outputs. |

## Upgrading from the previous version

- Update all PCs at the same time: the actions are now `POST` requests, so an old shell
  cannot drive a new server (and conversely). Scripts calling the server URLs directly
  must be adapted (see [Server endpoints](#server-endpoints)).
- After starting the motion server, run `init_all()` (the shell no longer initializes the axes).
- `mv`, `mvr` raise `MotionError` on failure instead of returning the error in a list
  (`raise_on_error=False` gives the old behaviour).
- `Motor.controler_type` / `controler_channel` are renamed `controller_type` /
  `controller_channel` (the old names still work, with a deprecation warning).
- The serial port of the PS90 must be in `config/motors.yaml` (no default port anymore).

## Tests

Automatic tests, with a fake PS90 serial port (no hardware needed):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests
```

They complement, but do not replace, the tests on the bench listed in
[`TESTS_BANC.md`](../TESTS_BANC.md).
