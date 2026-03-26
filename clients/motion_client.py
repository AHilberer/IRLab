from common.http_client import safe_get, DEFAULT_TIMEOUT

BASE_URL = "http://192.168.1.2:8001"

def build_motor_list_from_config():
    # Placeholder for function implementation
    pass

def mv(*kwargs):
    """Function to send a motor to a new position. Usage: mv(sx, 10.0)"""
    if len(kwargs)//2 != 0:
        raise ValueError("mv() requires exactly 2 arguments: motor name and position")
    else:
        for i in range(0, len(kwargs), 2):
            motor = kwargs[i]
            pos = kwargs[i+1]
            if not isinstance(motor, Motor) or not isinstance(pos, (int, float)):
                raise ValueError("First argument must be a Motor instance and position must be a number")
            # fire-and-forget move request
            safe_get(f"{BASE_URL}/mv/{motor}/{pos}", timeout=DEFAULT_TIMEOUT)

def umv(*kwargs):
    """Function to move a motor but shows continuously updated positions of motors. Usage: umv(sx, 10.0)"""
    if len(kwargs)//2 != 0:
        raise ValueError("umv() requires exactly 2 arguments: motor name and position")
    else:
        for i in range(0, len(kwargs), 2):
            motor = kwargs[i]
            pos = kwargs[i+1]
            if not isinstance(motor, Motor) or not isinstance(pos, (int, float)):
                raise ValueError("First argument must be a Motor instance and position must be a number")
            # make move with position updates

def wm(*kwargs):
    """Function to check the position of a motor. Usage: wm(sx) returns the position of motor sx."""
    for motor in kwargs:
        if not isinstance(motor, Motor):
            raise ValueError("Arguments must be Motor instances")
        r = safe_get(f"{BASE_URL}/read/{motor.name}", timeout=DEFAULT_TIMEOUT)
        print(f"{motor.name} position: {r.json()['position']}")



class Motor:
    def __init__(self,
                 name,
                 controler_type="PS90",
                 controler_channel=1,
                 velocity=1.0,
                 acceleration=1.0):
        self.name = name
        self.controler_type = controler_type
        self.controler_channel = controler_channel
        self.velocity = velocity
        self.acceleration = acceleration