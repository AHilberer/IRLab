from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import threading

from common.states import DeviceState
from common.version import get_version
from common.logging_setup import setup_logging, add_action_logging

logger = setup_logging('spectro_server')

try:
    from pyAndorSDK2 import atmcd, atmcd_codes, atmcd_errors
except Exception:
    atmcd = None
    atmcd_codes = None
    atmcd_errors = None

try:
    # NOTE: exact import path / class name to double-check against the
    # installed Andor Shamrock SDK's own examples if this doesn't match.
    from pyAndorSpectrograph.spectrograph import ATSpectrograph
except Exception:
    ATSpectrograph = None

try:
    import yaml
except Exception:
    yaml = None

app = FastAPI()
add_action_logging(app, logger)

# Serializes all raw Andor SDK2 hardware calls (connect/close/acquire):
# FastAPI's sync endpoints run on a thread pool, and SDK2 calls are not
# safe to interleave.
_sdk_lock = threading.Lock()

# Guards read/write access to the `spectrometers` registry and
# `default_spectrometer_name`, kept separate from _sdk_lock so a quick
# /state or /spectro/list poll never has to wait behind a long acquisition.
_registry_lock = threading.Lock()

# registry of named spectrometers (camera + optional spectrograph)
spectrometers = {}
default_spectrometer_name = None

DEFAULT_SPECTRO_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'config', 'spectro.yaml')


def _check(ret, action: str):
    """Raise a clear RuntimeError if an SDK2 call did not return DRV_SUCCESS."""
    if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
        raise RuntimeError(f'{action} failed: {atmcd_errors.Error_Codes(ret).name}')


class AndorCamera:
    """Wraps a single Andor SDK2 (pyAndorSDK2) camera, e.g. an iDus CCD."""

    def __init__(self, device_index: int = 0):
        if atmcd is None:
            raise RuntimeError('pyAndorSDK2 is required but not installed')
        self.device_index = device_index
        self.sdk = atmcd()
        self.xpixels = None
        self.ypixels = None
        self.exposure_time = None

    def connect(self):
        _check(self.sdk.Initialize(""), 'Initialize')
        _check(self.sdk.SetAcquisitionMode(atmcd_codes.Acquisition_Mode.SINGLE_SCAN), 'SetAcquisitionMode')
        _check(self.sdk.SetReadMode(atmcd_codes.Read_Mode.FULL_VERTICAL_BINNING), 'SetReadMode')
        _check(self.sdk.SetTriggerMode(atmcd_codes.Trigger_Mode.INTERNAL), 'SetTriggerMode')
        ret, self.xpixels, self.ypixels = self.sdk.GetDetector()
        _check(ret, 'GetDetector')
        self.set_exposure_time(0.1)

    def set_exposure_time(self, seconds: float):
        _check(self.sdk.SetExposureTime(seconds), 'SetExposureTime')
        self.exposure_time = seconds

    def acquire(self) -> list:
        """Run a single-scan acquisition and return the raw pixel intensities."""
        _check(self.sdk.PrepareAcquisition(), 'PrepareAcquisition')
        _check(self.sdk.StartAcquisition(), 'StartAcquisition')
        _check(self.sdk.WaitForAcquisition(), 'WaitForAcquisition')
        ret, arr, valid_first, valid_last = self.sdk.GetImages(1, 1, self.xpixels)
        _check(ret, 'GetImages')
        return list(arr)

    def close(self):
        try:
            self.sdk.AbortAcquisition()
        except Exception:
            pass
        self.sdk.ShutDown()


class ShamrockSpectrograph:
    """Wraps an Andor Shamrock spectrograph (e.g. a 303i) via pyAndorSpectrograph."""

    def __init__(self, device_index: int = 0):
        if ATSpectrograph is None:
            raise RuntimeError('pyAndorSpectrograph is required but not installed')
        self.device_index = device_index
        self.sdk = ATSpectrograph()

    def connect(self):
        ret = self.sdk.Initialize("")
        if ret != self.sdk.ATSPECTROGRAPH_SUCCESS:
            raise RuntimeError(f'Shamrock Initialize failed (code {ret})')

    def get_calibration(self, num_pixels: int) -> list:
        """Return the live wavelength axis for `num_pixels`, reflecting the
        spectrograph's current grating and center wavelength."""
        ret, calibration = self.sdk.GetCalibration(self.device_index, num_pixels)
        if ret != self.sdk.ATSPECTROGRAPH_SUCCESS:
            raise RuntimeError(f'Shamrock GetCalibration failed (code {ret})')
        return list(calibration)

    def close(self):
        try:
            self.sdk.Close()
        except Exception:
            pass


class Spectrometer:
    """A named spectrometer: one Andor camera plus an optional Shamrock spectrograph."""

    def __init__(self, name: str, camera_index: int = 0, spectrograph_index: int = None):
        self.name = name
        self.camera = AndorCamera(device_index=camera_index)
        self.spectrograph = ShamrockSpectrograph(device_index=spectrograph_index) if spectrograph_index is not None else None
        self.state = DeviceState.OFF

    def connect(self):
        with _sdk_lock:
            try:
                self.camera.connect()
                if self.spectrograph is not None:
                    self.spectrograph.connect()
            except Exception:
                self.state = DeviceState.FAULT
                # Don't leak a partially-opened camera handle (e.g. the camera
                # connected fine but the spectrograph then failed) -- a caller
                # that discards this Spectrometer and retries /spectro/connect
                # would otherwise re-Initialize() the same device while the
                # first handle is still open.
                try:
                    self.camera.close()
                except Exception:
                    pass
                if self.spectrograph is not None:
                    try:
                        self.spectrograph.close()
                    except Exception:
                        pass
                raise
        self.state = DeviceState.ON

    def close(self):
        with _sdk_lock:
            self.camera.close()
            if self.spectrograph is not None:
                self.spectrograph.close()
        self.state = DeviceState.OFF

    def acquire(self, exposure: float = 0.1):
        self.state = DeviceState.MOVING
        try:
            with _sdk_lock:
                self.camera.set_exposure_time(exposure)
                intensity = self.camera.acquire()
                if self.spectrograph is not None:
                    wavelength = self.spectrograph.get_calibration(self.camera.xpixels)
                else:
                    wavelength = list(range(len(intensity)))
        except Exception:
            self.state = DeviceState.FAULT
            # Best-effort: un-wedge the camera so the *next* request isn't
            # blocked behind this failed one (see /spectro/close for a full reset).
            try:
                self.camera.sdk.AbortAcquisition()
            except Exception:
                pass
            raise
        self.state = DeviceState.ON
        return wavelength, intensity


def _to_list(values) -> list:
    """Plain Python list of numbers, JSON-serializable: the SDKs may return numpy
    arrays, whose elements (numpy.int32...) FastAPI cannot encode."""
    return values.tolist() if hasattr(values, 'tolist') else [v for v in values]


def get_spectrometer(name: str = None) -> Spectrometer:
    """Return a registered spectrometer by name. If name is None, use the default."""
    with _registry_lock:
        if name is None:
            if default_spectrometer_name is None:
                raise RuntimeError('No spectrometer connected. Call /spectro/connect first.')
            name = default_spectrometer_name
        if name not in spectrometers:
            raise RuntimeError(f'Spectrometer "{name}" not connected. Call /spectro/connect?name={name} first.')
        return spectrometers[name]


@app.post('/spectro/connect')
def spectro_connect(name: str = 'main', camera_index: int = 0, spectrograph_index: int = None):
    """Connect a camera (and optional spectrograph) and register it under `name`.

    Example: /spectro/connect?name=main&camera_index=0&spectrograph_index=0
    """
    global default_spectrometer_name
    with _registry_lock:
        if name in spectrometers:
            return {'status': 'already_connected', 'name': name}
    try:
        spec = Spectrometer(name=name, camera_index=camera_index, spectrograph_index=spectrograph_index)
        spec.connect()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to connect spectrometer: {e}')
    with _registry_lock:
        spectrometers[name] = spec
        if default_spectrometer_name is None:
            default_spectrometer_name = name
    return {'status': 'connected', 'name': name, 'camera_index': camera_index, 'spectrograph_index': spectrograph_index}


@app.post('/spectro/close')
def spectro_close(name: str = None):
    """Close a named spectrometer (or the default). Use this together with
    /spectro/connect to recover a wedged connection without restarting the server."""
    global default_spectrometer_name
    with _registry_lock:
        if name is None:
            if default_spectrometer_name is None:
                return {'status': 'not_connected'}
            name = default_spectrometer_name
        if name not in spectrometers:
            return {'status': 'not_connected'}
        spec = spectrometers[name]
    try:
        spec.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error closing spectrometer: {e}')
    with _registry_lock:
        del spectrometers[name]
        if default_spectrometer_name == name:
            default_spectrometer_name = next(iter(spectrometers.keys()), None)
    return {'status': 'closed', 'name': name}


def _load_spectro_config_from_dict(cfg: dict):
    global default_spectrometer_name
    created = []
    for entry in cfg.get('spectrometers', []):
        name = entry.get('name')
        with _registry_lock:
            already_registered = not name or name in spectrometers
        if already_registered:
            continue
        camera_index = int(entry.get('camera_index', 0))
        spectrograph_index = entry.get('spectrograph_index')
        if spectrograph_index is not None:
            spectrograph_index = int(spectrograph_index)
        spec = Spectrometer(name=name, camera_index=camera_index, spectrograph_index=spectrograph_index)
        spec.connect()
        with _registry_lock:
            spectrometers[name] = spec
            if default_spectrometer_name is None:
                default_spectrometer_name = name
        created.append(name)
    return created


@app.post('/spectro/load_config')
def spectro_load_config(path: str = None):
    """Load spectrometer definitions from config/spectro.yaml and connect them."""
    if yaml is None:
        raise HTTPException(status_code=500, detail='pyyaml is not installed in this environment')
    if path is None:
        path = os.path.normpath(DEFAULT_SPECTRO_CONFIG)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f'Config file not found: {path}')
    try:
        with open(path, 'r') as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to read config: {e}')
    try:
        created = _load_spectro_config_from_dict(cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'status': 'loaded', 'created': created}


@app.get('/spectro/list')
def spectro_list():
    """List registered spectrometers and their state."""
    with _registry_lock:
        return {'spectrometers': [{'name': n, 'state': s.state.value} for n, s in spectrometers.items()]}


class AcquireRequest(BaseModel):
    exposure: float = 0.1    # s
    name: str = None         # spectrometer name; None = default one


@app.post("/acquire")
def acquire(req: AcquireRequest):
    """Acquire a spectrum (body: {"exposure": s, "name": optional spectrometer name})."""
    exposure, name = req.exposure, req.name
    try:
        spec = get_spectrometer(name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        wavelength, intensity = spec.acquire(exposure)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Acquisition failed: {e}. If this persists, try /spectro/close then /spectro/connect.',
        )
    return {
        "wavelength": _to_list(wavelength),
        "intensity": _to_list(intensity),
    }


@app.get("/status")
def status():
    """Server status: version and registered spectrometers with their state."""
    with _registry_lock:
        specs = [{"name": n, "state": sp.state.value} for n, sp in spectrometers.items()]
    return {
        "server": "spectro_server",
        "version": get_version(),
        "status": "ok" if specs else "no spectrometer connected",
        "spectrometers": specs,
    }


@app.get("/state")
def get_state():
    """Server-wide state: FAULT if any spectrometer is in FAULT, MOVING if any is
    acquiring, else ON (or OFF if none registered)."""
    with _registry_lock:
        states = [s.state for s in spectrometers.values()]
    if DeviceState.FAULT in states:
        overall = DeviceState.FAULT
    elif DeviceState.MOVING in states:
        overall = DeviceState.MOVING
    elif states:
        overall = DeviceState.ON
    else:
        overall = DeviceState.OFF
    return {"state": overall.value}


## launch with uvicorn servers.spectro_server:app --host 0.0.0.0 --port 8002
