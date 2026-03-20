# IRLab_shell.py
# startup with 'python IRLab_shell.py'

import IPython
from clients.motion_client import Motor
from clients.spectro_client import Spectrometer

print("----- Starting IRLab control shell -----")

sx = Motor("sx")
spec = Spectrometer()

def mv(motor, pos):
    motor.move(pos)

def ascan(motor, start, stop, npts):
    import numpy as np
    for x in np.linspace(start, stop, npts):
        mv(motor, x)

print("Checking connections...")

try:
    sx.status()
    print("Motor server running")
except:
    print("Motor server NOT reachable")

try:
    spec.status()
    print("Spectro server running")
except:
    print("Spectro server NOT reachable")

# lancer IPython avec ton namespace
IPython.start_ipython(argv=[], user_ns=globals())
