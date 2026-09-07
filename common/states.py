from enum import Enum


class DeviceState(str, Enum):
    """Shared device-state convention used by all device servers.

    Every hardware-backed object (motor, actuator, spectrometer, ...) tracks
    its status using one of these values, and each server exposes its
    current state via a `GET /state` endpoint so the shell / clients can
    poll hardware health without triggering a hardware call:

      OFF    - not connected / not yet initialized
      ON     - connected and idle, ready to accept commands
      MOVING - a command (move, acquisition, actuation) is in progress
      FAULT  - the last connection or command attempt raised an exception

    Subclassing `str` means the enum serializes directly to its value in
    JSON responses (e.g. {"state": "on"}) without extra conversion.
    """
    ON = "on"
    MOVING = "moving"
    FAULT = "fault"
    OFF = "off"
