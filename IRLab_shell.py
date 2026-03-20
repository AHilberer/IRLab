# IRLab_shell.py
# startup with 'python IRLab_shell.py'

import IPython
from clients.motion_client import Motor
from clients.spectro_client import Spectrometer

print("""
 █████ ███████████   █████                 █████    
▒▒███ ▒▒███▒▒▒▒▒███ ▒▒███                 ▒▒███     
 ▒███  ▒███    ▒███  ▒███         ██████   ▒███████ 
 ▒███  ▒██████████   ▒███        ▒▒▒▒▒███  ▒███▒▒███
 ▒███  ▒███▒▒▒▒▒███  ▒███         ███████  ▒███ ▒███
 ▒███  ▒███    ▒███  ▒███      █ ███▒▒███  ▒███ ▒███
 █████ █████   █████ ███████████▒▒████████ ████████ 
▒▒▒▒▒ ▒▒▒▒▒   ▒▒▒▒▒ ▒▒▒▒▒▒▒▒▒▒▒  ▒▒▒▒▒▒▒▒ ▒▒▒▒▒▒▒▒  
                                                    
                                                    
 """)

sx = Motor("sx")
spec = Spectrometer()

def mv(motor, pos):
    motor.move(pos)

def ascan(motor, start, stop, npts):
    import numpy as np
    for x in np.linspace(start, stop, npts):
        mv(motor, x)
print("-----------------------------------------------------")
print("Checking connections...")
print("-----------------------------------------------------")

# prefer a short timeout at startup so the shell doesn't block
STARTUP_TIMEOUT = 2

m_status = sx.status(timeout=STARTUP_TIMEOUT)
if m_status is None:
    print("Motor server NOT reachable")
else:
    print(f"Motor server running: {m_status}")

s_status = spec.status(timeout=STARTUP_TIMEOUT)
if s_status is None:
    print("Spectro server NOT reachable")
else:
    print(f"Spectro server running: {s_status}")


print("-----------------------------------------------------")
print("Starting custom shell interface")
print("-----------------------------------------------------")

IPython.start_ipython(argv=[], user_ns=globals(), display_banner=False)
