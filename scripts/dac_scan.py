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

        


if __name__ == "__main__":
    data = dac_scan()
    print("Scan complete")



