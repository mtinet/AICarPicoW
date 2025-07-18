BT_NAME = "mtinet"  # 블루투스 출력 이름 (영문 8글자 이내)

from micropython import const
import bluetooth
import struct
import time

# ========== BLE Advertising 관련 코드 ==========
_ADV_TYPE_FLAGS            = const(0x01)
_ADV_TYPE_NAME             = const(0x09)
_ADV_TYPE_UUID16_COMPLETE  = const(0x3)
_ADV_TYPE_UUID32_COMPLETE  = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE      = const(0x2)
_ADV_TYPE_UUID32_MORE      = const(0x4)
_ADV_TYPE_UUID128_MORE     = const(0x6)
_ADV_TYPE_APPEARANCE       = const(0x19)

def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
    payload = bytearray()
    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value

    _append(_ADV_TYPE_FLAGS,
            struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)))
    if name:
        _append(_ADV_TYPE_NAME, name)
    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))
    return payload

# ========== BLE Simple Peripheral 관련 코드 ==========
_IRQ_CENTRAL_CONNECT    = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE        = const(3)

_FLAG_READ              = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE             = const(0x0008)
_FLAG_NOTIFY            = const(0x0010)

_UART_UUID   = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX     = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"),
                _FLAG_READ | _FLAG_NOTIFY)
_UART_RX     = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
                _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
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
            _, value_handle = data
            value = self._ble.gatts_read(value_handle)
            if value_handle == self._handle_rx and self._write_callback:
                self._write_callback(value)

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

# ========== 수신 콜백 테스트 ==========
def on_rx(data):
    print("Received:", data)
    # 받은 데이터를 웹페이지로 다시 전송(에코)
    sp.send(b"피코에서 보냄: " + data)

# ========== 메인 ==========
ble = bluetooth.BLE()
sp  = BLESimplePeripheral(ble)
sp.on_write(on_rx)

print("BLE UART 서비스 시작됨. 연결을 기다리는 중...")

# 예시: MicroPython에서 웹페이지로 직접 문자열을 보내고 싶을 때
# sp.send(b"MicroPython에서 웹으로 전송하는 메시지!")

while True:
    time.sleep(1)
