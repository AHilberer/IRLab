# IRLab

Control framework for an optical spectroscopy bench: FastAPI servers drive the
hardware, and an IPython shell offers SPEC-like commands (`mv`, `wm`, `ascan`,
`tweak`, `on`, `off`...) from any PC of the bench.

Current version: **1.3** (shown under the shell banner and in each server's console,
see [`docs/TECHNICAL.md`](docs/TECHNICAL.md#version)).

Technical details (configuration, endpoints, logs, points to check on the hardware...)
are in [`docs/TECHNICAL.md`](docs/TECHNICAL.md); the tests to run on the bench are in
[`TESTS_BANC.md`](TESTS_BANC.md).

## Framework architecture

- **One server per hardware**, running on the PC the hardware is connected to:
  - `servers/motion_server.py`: motors, through an OWIS PS90 controller (serial port);
  - `servers/spectro_server.py`: spectrometer (Andor camera + Shamrock spectrograph);
  - `servers/festo_server.py`: FESTO pneumatic actuators, through an NI cDAQ chassis (NI-DAQmx).
- **The servers are the single source of truth.** Each one loads its configuration
  (`config/*.yaml`) at startup, owns its hardware, serializes the accesses to it, and
  keeps a log of every action (`logs/`). If the hardware is missing, it still starts
  in degraded mode and reports the errors.
- **Clients talk to the servers over HTTP/JSON** (`clients/`): reads are `GET`,
  actions that change the bench are `POST`. Any number of shells, on any PC, can
  use the servers at the same time.
- **The shell** (`IRLab_shell.py`) creates its motor and actuator objects from the
  servers' lists and exposes the commands below. Scans and jog mode are in
  `scripts/base_scripts.py`; personal routines go in `scripts/user_scripts.py`.

## Bench architecture

The 5 bench PCs run Windows 10/11 and are connected by a switch on a local network
**isolated from the Internet**. Machine names are resolved by the Windows `hosts`
file of each PC; `config/servers.yaml` uses these names, never IP addresses.

| Server | Runs on PC | Port | Start script |
|---|---|---|---|
| Motion (OWIS PS90) | `pc-moteurs` (PC with the PS90 serial cable) | 8001 | `start_motion.ps1` |
| FESTO (NI-DAQmx) | `pc-moteurs` (PC with the NI cDAQ chassis) | 8003 | `start_festo.ps1` |
| Spectrometer (Andor) | `pc-spectro` (PC with the Andor camera) | 8002 | `start_spectro.ps1` |

Since v1.1 the spectrometer server is disabled (`disabled_servers` in `config/servers.yaml`):
its code is kept, but it is not tested on the bench yet and the shell does not contact it.

`pc-moteurs` and `pc-spectro` are example names: replace them here and in
`config/servers.yaml` with the real names of the bench PCs. The shell runs on any PC.

## Installation

The bench network has no Internet access: IRLab is installed from files kept on a USB
key (or a network share), the same on all PCs: the Python 3.13 installer
(`python-3.13.17-amd64.exe`) and the `wheels` folder of Python packages
(see [`docs/TECHNICAL.md`](docs/TECHNICAL.md#offline-installation) to make them).

On each PC (PowerShell; IRLab does not use Anaconda):

1. Install Python 3.13, the same way on all PCs (PowerShell **as administrator**; installs
   the `py` launcher, does not change the PATH):
   ```powershell
   .\python-3.13.17-amd64.exe /passive InstallAllUsers=1 PrependPath=0 Include_launcher=1 InstallLauncherAllUsers=1 Include_test=0
   ```
2. In the repository folder, create the `.venv` from the `wheels` folder (an existing
   `.venv` must be renamed first: `Rename-Item .venv .venv_old`):
   ```powershell
   .\tools\install_offline.ps1 -Wheels E:\wheels
   ```

Drivers needed besides the Python packages:

- **FESTO PC**: the NI-DAQmx driver from National Instruments (the `nidaqmx` package
  alone is not enough);
- **spectrometer PC**: the Andor SDK2 and Shamrock SDK;
- **motion PC**: the USB-serial driver of the PS90, if any (COM port in `config/motors.yaml`).

On the server PCs, ports 8001 to 8003 must be open in the firewall
(see [`docs/TECHNICAL.md`](docs/TECHNICAL.md#firewall)).

**Starting**: on each server PC, run its start script (`.\start_motion.ps1`...), then
start the shell from any PC and initialize the motors once:

```powershell
.\start_shell.ps1      # same as .\.venv\Scripts\python.exe IRLab_shell.py
```
```python
init_all()      # once after the motion server starts: powers the motors
```

## Shell commands

Motors (positions always in the motor's `unit` from `config/motors.yaml`: mm, deg, steps...):

| Command | Action |
|---|---|
| `mv(m1, pos1[, m2, pos2...])` | absolute move; raises `MotionError` on failure; Ctrl+C stops the motors |
| `mvr(m1, delta1[, ...])` | relative move |
| `wm(m1, ...)`, `m.position()` | read positions |
| `stop(m1, ...)`, `stop_all()` | stop motors immediately (also from another shell) |
| `init(m1, ...)`, `init_all()` | initialize motors, once after the motion server starts |
| `free(...)`, `control(...)` | release / re-acquire axes (e.g. to move an axis by hand) |
| `free_all_motors()`, `control_all_motors()` | same, for all motors |
| `ascan(m, start, stop, npts)` | absolute scan, back to the initial position at the end |
| `dscan(m, start_delta, stop_delta, npts)` | scan relative to the current position |
| `tweak(m1[, m2[, m3]])` | keyboard jog mode (arrows, a/z, +/- for the step, q to quit) |

FESTO actuators and spectrometer:

| Command | Action |
|---|---|
| `on(a1, ...)`, `off(a1, ...)`, `toggle(a1, ...)` | actuate / retract / toggle actuators |
| `state(a1, ...)` | read the actuators' on/off state |
| `spec.acquire(exposure=...)` | acquire a spectrum |

Servers:

| Command | Action |
|---|---|
| `reconnect()` | retry the servers that were not reachable, create the missing objects |
| `check_all()` | print the state of the three servers |

Motors and actuators are available by their name (`sx`, `festo_1`...) and as
`motors['...']` / `actuators['...']`.
