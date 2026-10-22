"""Minimal fake of a PS90 on a serial port, for tests only.

It understands the few commands used by servers/motion_server.py and records
a protocol violation whenever a command is written while the response to the
previous one has not been read yet (which is what happens when two threads
interleave on the real port).
"""
import threading
import time


class FakePS90Serial:
    def __init__(self, port=None, baudrate=9600, n_axes=9, move_polls=10, timeout=1, stop_polls=0,
                 moving_char='T', late_ack=False, **kwargs):
        self.port = port
        self.timeout = timeout
        self.disconnected = False      # simulate an unplugged cable: no response at all
        self.overrides = {}            # cmd -> raw response, to simulate bad answers
        self.blocked = {}              # axis index -> (reached position, status char), e.g. limit switch
        self.n_axes = n_axes
        self.move_polls = move_polls   # number of ?ASTAT polls an axis stays in 'T'
        self.stop_polls = stop_polls   # polls an axis stays in 'T' after STOP (deceleration)
        self.moving_char = moving_char # ?ASTAT state while positioning ('T' trapezoidal, 'S' S-curve)
        self.late_ack = late_ack       # TERM=2: "OK" after each command, arriving late
        self._ack_due = False
        self.positions = [0] * n_axes
        self.setpoints = [0] * n_axes
        self.status = ['R'] * n_axes
        self._remaining_polls = [0] * n_axes
        self._pending = None           # response not read yet
        self._internal = threading.Lock()
        self.collisions = 0
        self.commands = []

    # --- pyserial API used by PS90 ---
    def reset_input_buffer(self):
        with self._internal:
            self._pending = None

    def write(self, data):
        cmd = data.decode().strip()
        with self._internal:
            if self._pending is not None:
                self.collisions += 1
            self.commands.append(cmd)
            if self.late_ack and cmd.startswith('?') and self._ack_due:
                prefix = 'OK\r'
            else:
                prefix = ''
            self._ack_due = self.late_ack and not cmd.startswith('?')
            if self.disconnected:
                response = None
            elif cmd in self.overrides:
                response = self.overrides[cmd]
            else:
                response = self._handle(cmd)
            self._pending = (prefix + response) if (prefix and response is not None) else response
        # widen the race window so unprotected interleavings show up reliably
        time.sleep(0.001)
        return len(data)

    def read_all(self):
        with self._internal:
            r, self._pending = self._pending, None
        return ((r + '\r') if r else '').encode()

    def read_until(self, expected=b'\n'):
        # a real port would block up to `timeout` before returning what it got
        with self._internal:
            data = ((self._pending + '\r') if self._pending else '').encode()
            i = data.find(expected)
            if i < 0 or i + len(expected) == len(data):
                self._pending = None
                return data
            rest = data[i + len(expected):].decode()
            self._pending = rest[:-1] if rest.endswith('\r') else rest
            return data[:i + len(expected)]

    def close(self):
        pass

    # --- tiny PS90 model ---
    def _handle(self, cmd):
        if cmd == '?ASTAT':
            for i in range(self.n_axes):
                if self.status[i] == self.moving_char:
                    self._remaining_polls[i] -= 1
                    if self._remaining_polls[i] <= 0:
                        self.status[i] = 'R'
                        self.positions[i] = self.setpoints[i]
                        if i in self.blocked:
                            self.positions[i], self.status[i] = self.blocked[i]
            return ''.join(self.status)
        if cmd.startswith('?CNT'):
            return str(self.positions[int(cmd[4:]) - 1])
        if cmd.startswith('PSET'):
            axis, value = cmd[4:].split('=')
            self.setpoints[int(axis) - 1] = int(value)
            return None
        if cmd.startswith('PGO'):
            axis = int(cmd[3:]) - 1
            self.status[axis] = self.moving_char
            self._remaining_polls[axis] = self.move_polls
            return None
        if cmd.startswith('STOP'):
            axis = int(cmd[4:]) - 1
            if self.status[axis] == self.moving_char:
                self.setpoints[axis] = (self.positions[axis] + self.setpoints[axis]) // 2
                if self.stop_polls:
                    self._remaining_polls[axis] = self.stop_polls
                else:
                    self.status[axis] = 'R'
                    self.positions[axis] = self.setpoints[axis]
            return None
        if cmd.startswith('?'):
            return '0'
        return None
