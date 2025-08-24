# ========== Imports ==========
from machine import Pin, PWM, ADC
from micropython import const
import bluetooth
import struct
import time
import utime

# ========== Bluetooth Constants and Setup ==========
BT_NAME = "mtinet"  # Bluetooth device name

# Advertising payloads are repeated packets of the following form:
#   1 byte data length (N + 1)
#   1 byte type (see constants below)
#   N bytes data
_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_APPEARANCE = const(0x19)

# Helper function to encode advertising payloads.
def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
    payload = bytearray()
    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value
    _append(_ADV_TYPE_FLAGS, struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)))
    if name:
        _append(_ADV_TYPE_NAME, name)
    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))
    return payload

# BLE UART Service constants
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_READ | _FLAG_NOTIFY,)
_UART_RX = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE,)
_UART_SERVICE = (_UART_UUID, (_UART_TX, _UART_RX),)

# BLE Peripheral Class
class BLESimplePeripheral:
    def __init__(self, ble, name=BT_NAME):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._handle_tx, self._handle_rx),) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._connections = set()
        self._write_callback = None
        self._payload = advertising_payload(name=name, services=[_UART_UUID])
        self._advertise()

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn, _, _ = data
            print("New connection", conn)
            self._connections.add(conn)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn, _, _ = data
            print("Disconnected", conn)
            self._connections.remove(conn)
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            value = self._ble.gatts_read(value_handle)
            if value_handle == self._handle_rx and self._write_callback:
                self._write_callback(value)

    def send(self, data):
        for conn_handle in self._connections:
            self._ble.gatts_notify(conn_handle, self._handle_tx, data)

    def is_connected(self):
        return len(self._connections) > 0

    def _advertise(self, interval_us=500000):
        print("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    def on_write(self, callback):
        self._write_callback = callback

# ========== Hardware Pin Setup ==========
# DC Motor Pins
motor_dir = Pin(21, Pin.OUT)
motor_sd1 = Pin(20, Pin.OUT)
motor_sd2 = Pin(19, Pin.OUT)
motor_pwm = PWM(Pin(18))
motor_pwm.freq(1000)

# Accelerator (ADC)
accel = ADC(Pin(28))

# Forward/Reverse Switch
fwd_rev_switch = Pin(1, Pin.IN, Pin.PULL_UP)

# Initial motor driver state
motor_sd1.value(1)
motor_sd2.value(1)

# Stepper Motor Pins
step_en = Pin(10, Pin.OUT)
step_rst = Pin(11, Pin.OUT)
step_dir = Pin(12, Pin.OUT)
step_pul = Pin(13, Pin.OUT)

# Stepper Motor Init
step_en.value(0)
step_rst.value(0)
utime.sleep_ms(10)

# ========== Global State and Constants ==========
control_mode = 'manual'  # 'manual' or 'app'
app_command = 'stop'     # App mode command: 'stop', 'forward', 'backward'
app_motor_direction = 'forward' # Actual direction of the motor in app mode
current_speed = 63000    # Initial speed is stopped

STOP_SPEED = 63000
# MAX_SPEED is now dynamic, see below
RAMP_STEP = 1500 # Speed change per loop iteration for acceleration

# DC Motor Speed Control
# Levels correspond to 40%, 60%, 80%, 100% of max speed
# Lower value = higher speed
DC_MOTOR_SPEED_LEVELS = [41800, 31200, 20600, 10000]
dc_motor_speed_level_index = 3 # Start at 100% (index 3)
MAX_SPEED = DC_MOTOR_SPEED_LEVELS[dc_motor_speed_level_index]


# Stepper Motor State
rotate_pos = 10
rotate_mid = 10
rotate_left_limit = 0
rotate_right_limit = 20
STEPS_PER_REV = 400

# ========== Motor Control Function ==========
def drive_motor(speed_val, direction='forward'):
    motor_dir.value(1 if direction == 'forward' else 0)
    motor_pwm.duty_u16(speed_val)

# ========== Stepper Motor Control Function ==========
def step_rotate(direction='left', degrees=13):
    global rotate_pos

    # 1 step = 0.036 degrees (with 1:50 gear), 여기에 실제 회전 각도 보정을 위해 ×2
    steps = int(degrees / 0.036 * 2)

    if direction == 'left':
        if rotate_pos <= rotate_left_limit:
            rotate_pos = rotate_left_limit
            print("Steering at left limit.")
            return
        step_dir.value(1) # Swapped to fix reversed direction
        rotate_pos -= 1
    elif direction == 'right':
        if rotate_pos >= rotate_right_limit:
            rotate_pos = rotate_right_limit
            print("Steering at right limit.")
            return
        step_dir.value(0) # Swapped to fix reversed direction
        rotate_pos += 1

    step_en.value(1)  # Enable

    for _ in range(steps):
        step_pul.value(1)
        utime.sleep_us(500)
        step_pul.value(0)
        utime.sleep_us(500)

    step_en.value(0)
    print("rotate_pos:", rotate_pos, "degrees rotated:", degrees)

# ========== Bluetooth RX Callback for Mode and Command Switching ==========
def on_rx(data):
    global control_mode, app_command, current_speed, dc_motor_speed_level_index, MAX_SPEED
    command = data.decode().strip()
    print(f"Received command: '{command}'")

    # Mode switching commands
    if command == 'i':
        if control_mode != 'app':
            control_mode = 'app'
            app_command = 'stop'
            current_speed = STOP_SPEED
            drive_motor(current_speed) # Stop motor on mode change
            print("Switching to App Control Mode.")
            sp.send(b"Switched to App Mode")
    elif command == 'm':
        if control_mode != 'manual':
            control_mode = 'manual'
            drive_motor(STOP_SPEED) # Stop motor before switching
            print("Switching to Manual Mode.")
            sp.send(b"Switched to Manual Mode")
    
    # App mode motor commands
    elif control_mode == 'app':
        if command == 'w':
            app_command = 'forward'
            print("App command: FORWARD")
        elif command == 'x':
            app_command = 'backward'
            print("App command: BACKWARD")
        elif command == 's':
            app_command = 'stop'
            print("App command: STOP")
        elif command == 'a':
            print("App command: Steer Left")
            step_rotate(direction='left', degrees=13)
        elif command == 'd':
            print("App command: Steer Right")
            step_rotate(direction='right', degrees=13)
        elif command == 'o': # Decrease max speed
            if dc_motor_speed_level_index > 0:
                dc_motor_speed_level_index -= 1
                MAX_SPEED = DC_MOTOR_SPEED_LEVELS[dc_motor_speed_level_index]
                level_percent = ((dc_motor_speed_level_index * 2) + 4) * 10
                print(f"Max speed decreased to {level_percent}%")
                sp.send(f"Max speed: {level_percent}%".encode())
        elif command == 'p': # Increase max speed
            if dc_motor_speed_level_index < len(DC_MOTOR_SPEED_LEVELS) - 1:
                dc_motor_speed_level_index += 1
                MAX_SPEED = DC_MOTOR_SPEED_LEVELS[dc_motor_speed_level_index]
                level_percent = ((dc_motor_speed_level_index * 2) + 4) * 10
                print(f"Max speed increased to {level_percent}%")
                sp.send(f"Max speed: {level_percent}%".encode()) 

# ========== Initialization ==========
ble = bluetooth.BLE()
sp = BLESimplePeripheral(ble, name=BT_NAME)
sp.on_write(on_rx)

print("BLE UART service started. Waiting for connection...")

# ========== Main Loop ==========
while True:
    if control_mode == 'manual':
        accel_val = accel.read_u16()

        # --- Accelerator Mapping ---
        in_min = 18500
        in_max = 65500
        
        # Clamp input value
        if accel_val < in_min:
            accel_val = in_min
        elif accel_val > in_max:
            accel_val = in_max

        # Linear inverse mapping
        speed = STOP_SPEED - ((accel_val - in_min) * (STOP_SPEED - MAX_SPEED)) // (in_max - in_min)

        # Read forward/reverse switch
        fwd_rev = fwd_rev_switch.value()
        direction = 'forward' if fwd_rev == 1 else 'backward'

        drive_motor(speed, direction)
        
        direction_str = 'forward' if fwd_rev == 1 else 'backward'
        print(f"Mode: Manual | Accel: {accel_val}, Speed: {speed}, Direction: {direction_str}")

    elif control_mode == 'app':
        # Determine if a direction reversal is commanded
        is_reversing = (app_command == 'forward' and app_motor_direction == 'backward') or                        (app_command == 'backward' and app_motor_direction == 'forward')

        # If a direction change is commanded while the motor is moving, stop first.
        if is_reversing and current_speed < STOP_SPEED:
            # Ramp up speed value to decelerate to a stop
            current_speed = min(STOP_SPEED, current_speed + RAMP_STEP)
            
            # Once stopped, update the motor's direction to the new target
            if current_speed >= STOP_SPEED:
                app_motor_direction = 'forward' if app_command == 'forward' else 'backward'
        else:
            # No direction change, or we are already stopped. Proceed with command.
            if app_command == 'forward':
                app_motor_direction = 'forward'
                if current_speed > MAX_SPEED:
                    current_speed = max(MAX_SPEED, current_speed - RAMP_STEP)
            
            elif app_command == 'backward':
                app_motor_direction = 'backward'
                if current_speed > MAX_SPEED:
                    current_speed = max(MAX_SPEED, current_speed - RAMP_STEP)

            elif app_command == 'stop':
                current_speed = STOP_SPEED

        drive_motor(current_speed, app_motor_direction)
        print(f"Mode: App | Cmd: {app_command} | Speed: {current_speed} | Dir: {app_motor_direction}")

    utime.sleep(0.1)
