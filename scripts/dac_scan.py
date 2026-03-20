import numpy as np
import time

from clients.motion_client import Motor
from clients.spectro_client import Spectrometer

import h5py

def save_hdf5(data, filename="scan.h5"):
    with h5py.File(filename, "w") as f:
        for i, point in enumerate(data):
            grp = f.create_group(f"point_{i}")
            grp["x"] = point["x"]
            grp["wavelength"] = point["spectrum"]["wavelength"]
            grp["intensity"] = point["spectrum"]["intensity"]

        
sx = Motor("sx")
spec = Spectrometer()

def dac_scan():
    results = []

    for x in np.linspace(0, 10, 20):
        print(f"Moving to {x}")
        sx.move(x)

        time.sleep(0.2)  # attendre stabilisation

        spectrum = spec.acquire(0.1)

        results.append({
            "x": x,
            "spectrum": spectrum
        })

    return results


if __name__ == "__main__":
    data = dac_scan()
    print("Scan complete")



