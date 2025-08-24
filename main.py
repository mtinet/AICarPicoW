# main.py
# Combined code for AICar Pico W project

# ========== Imports ==========
from machine import Pin, PWM, ADC
import bluetooth
import struct
import time
import utime
from micropython import const

# ========== Configuration ==========
BT_NAME = "mtinet"  # Bluetooth name

# --- Pin Definitions ---
# Steering Motor (from stepMotorPicoW.py)
STEP_EN_PIN = 10
STEP_RST_PIN = 11
STEP_DIR_PIN = 12
STEP_PUL_PIN = 13

# Drive Motor (based on AICar.ino)
DRIVE_DIR_PIN = 14
DRIVE_PWM_PIN = 15

# Pedal and Switches (based on AICar.ino)
PEDAL_ADC_PIN = 26 # ADC0
PEDAL_F_PIN = 6  # Forward switch
PEDAL_B_PIN = 7  # Backward switch

# ========== Global Variables ==========
# --- Mode ---
# 1: Manual Control (default), 0: App Control
mode_state = 1

# --- Drive Motor ---
# Max speed percentage (50-100%) for App Control
max_speed_percentage = 100

# --- Steering Motor ---
rotate_pos = 10
rotate_mid = 10
rotate_left_limit = 0
rotate_right_limit = 20

# --- BLE Objects ---
ble = None
sp = None

# ========== BLE Code (from 1. bluetoothConnect.py) ==========
_ADV_TYPE_FLAGS            = const(0x01)
_ADV_TYPE_NAME             = const(0x09)
_ADV_TYPE_UUID16_COMPLETE  = const(0x3)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_APPEARANCE       = const(0x19)

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
            if len(b) == 2: _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 16: _append(_ADV_TYPE_UUID128_COMPLETE, b)
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))
    return payload

_IRQ_CENTRAL_CONNECT    = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE        = const(3)

_FLAG_READ              = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE             = const(0x0008)
_FLAG_NOTIFY            = const(0x0010)

_UART_UUID   = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX     = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_READ | _FLAG_NOTIFY)
_UART_RX     = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
_UART_SERVICE = (_UART_UUID, (_UART_TX, _UART_RX),)

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
        global mode_state
        if event == _IRQ_CENTRAL_CONNECT:
            conn, _, _ = data
            print("New connection", conn)
            self._connections.add(conn)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn, _, _ = data
            print("Disconnected", conn)
            self._connections.remove(conn)
            # Stop motor and revert to manual mode on disconnect for safety
            drive_stop()
            mode_state = 1
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            _, value_handle = data
            if value_handle == self._handle_rx and self._write_callback:
                self._write_callback(self._ble.gatts_read(value_handle))

    def send(self, data):
        for h in self._connections:
            self._ble.gatts_notify(h, self._handle_tx, data)

    def is_connected(self):
        return bool(self._connections)

    def _advertise(self, interval_us=500000):
        print("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    def on_write(self, callback):
        self._write_callback = callback

# ========== Hardware Initialization ==========
# --- Steering Motor ---
step_en = Pin(STEP_EN_PIN, Pin.OUT)
step_rst = Pin(STEP_RST_PIN, Pin.OUT)
step_dir = Pin(STEP_DIR_PIN, Pin.OUT)
step_pul = Pin(STEP_PUL_PIN, Pin.OUT)
step_en.value(0)
step_rst.value(0)
utime.sleep_ms(10)
step_rst.value(1)

# --- Drive Motor ---
drive_dir = Pin(DRIVE_DIR_PIN, Pin.OUT)
drive_pwm = PWM(Pin(DRIVE_PWM_PIN))
drive_pwm.freq(1000)

# --- Pedal & Switches ---
pedal_adc = ADC(Pin(PEDAL_ADC_PIN))
pedal_f = Pin(PEDAL_F_PIN, Pin.IN, Pin.PULL_UP)
pedal_b = Pin(PEDAL_B_PIN, Pin.IN, Pin.PULL_UP)

# ========== Motor Control Functions ==========

def execute_step(steps, direction):
    step_dir.value(direction)
    step_en.value(1)
    for _ in range(steps):
        step_pul.value(1)
        utime.sleep_us(500)
        step_pul.value(0)
        utime.sleep_us(500)
    step_en.value(0)

def steer_left():
    global rotate_pos
    if rotate_pos > rotate_left_limit:
        execute_step(120, 0) # 120 steps, direction 0 for left
        rotate_pos -= 1
        print(f"Steer left, pos: {rotate_pos}")

def steer_right():
    global rotate_pos
    if rotate_pos < rotate_right_limit:
        execute_step(120, 1) # 120 steps, direction 1 for right
        rotate_pos += 1
        print(f"Steer right, pos: {rotate_pos}")

def steer_center():
    global rotate_pos
    print("Centering steering...")
    while rotate_pos != rotate_mid:
        if rotate_pos > rotate_mid:
            execute_step(120, 0) # Turn left
            rotate_pos -= 1
        else:
            execute_step(120, 1) # Turn right
            rotate_pos += 1
        print(f"Centering... pos: {rotate_pos}")
    print("Steering centered.")

def drive_stop():
    drive_pwm.duty_u16(0)
    print("Drive stop")

def accelerate(target_duty):
    current_duty = drive_pwm.duty_u16()
    step = 2000  # Acceleration increment
    if current_duty < target_duty:
        for duty in range(current_duty, target_duty, step):
            drive_pwm.duty_u16(duty)
            utime.sleep_ms(10)
    drive_pwm.duty_u16(target_duty)

def drive_forward():
    print("Drive forward")
    steer_center()
    drive_dir.value(0)
    target_duty = int(65535 * (max_speed_percentage / 100.0))
    accelerate(target_duty)

def drive_backward():
    print("Drive backward")
    drive_dir.value(1)
    target_duty = int(65535 * (max_speed_percentage / 100.0))
    accelerate(target_duty)

# ========== Main Logic ==========

def on_rx(data):
    global mode_state, max_speed_percentage
    cmd = data.decode().strip().lower()
    print(f"Received command: '{cmd}'")

    if 'm' in cmd:
        mode_state = 1
        drive_stop()
        print("Mode -> Manual Control")
        sp.send(b"Mode: Manual")
        return
    elif 'i' in cmd:
        mode_state = 0
        drive_stop()
        print("Mode -> App Control")
        sp.send(b"Mode: App")
        return

    if mode_state == 0:  # Process commands only in App Control Mode
        if 'w' in cmd:
            drive_forward()
        elif 'x' in cmd:
            drive_backward()
        elif 's' in cmd:
            drive_stop()
        elif 'a' in cmd:
            steer_left()
        elif 'd' in cmd:
            steer_right()
        elif 'o' in cmd:
            max_speed_percentage = max(50, max_speed_percentage - 10)
            print(f"Speed decreased to {max_speed_percentage}%")
            sp.send(f"Speed: {max_speed_percentage}%".encode())
        elif 'p' in cmd:
            max_speed_percentage = min(100, max_speed_percentage + 10)
            print(f"Speed increased to {max_speed_percentage}%")
            sp.send(f"Speed: {max_speed_percentage}%".encode())

def manual_control():
    # NOTE: The pedal ADC values are estimates. You will need to calibrate
    # them by printing the pedal_adc.read_u16() value and adjusting.
    min_pedal_adc = 15000  # Value when pedal is not pressed
    max_pedal_adc = 55000  # Value when pedal is fully pressed

    # Read switches (PULL_UP means 0 is pressed)
    is_forward_pressed = pedal_f.value() == 0
    is_backward_pressed = pedal_b.value() == 0

    # Read pedal ADC (0-65535)
    pedal_val = pedal_adc.read_u16()

    duty = 0
    if pedal_val > min_pedal_adc:
        # Map pedal value to PWM duty cycle (0-65535)
        duty = int((pedal_val - min_pedal_adc) * 65535 / (max_pedal_adc - min_pedal_adc))
    
    duty = max(0, min(65535, duty)) # Constrain value

    if is_forward_pressed and not is_backward_pressed:
        drive_dir.value(0) # Forward
        drive_pwm.duty_u16(duty)
    elif is_backward_pressed and not is_forward_pressed:
        drive_dir.value(1) # Backward
        drive_pwm.duty_u16(duty)
    else:
        # Stop if both or neither switch is pressed
        drive_stop()

# ========== Program Start ==========
def main():
    global ble, sp
    
    ble = bluetooth.BLE()
    sp = BLESimplePeripheral(ble)
    sp.on_write(on_rx)

    print("AICar Pico W Ready.")
    print("Initial mode: Manual Control")

    while True:
        if mode_state == 1:
            manual_control()
        # In App Control mode (mode_state == 0), actions are event-driven by on_rx.
        # The main loop doesn't need to do anything for app mode.
        
        time.sleep_ms(20) # Main loop delay

if __name__ == "__main__":
    main()
