from machine import Pin, PWM, ADC
import utime

# 스텝모터 핀 설정
step_en = Pin(10, Pin.OUT)
step_rst = Pin(11, Pin.OUT)
step_dir = Pin(12, Pin.OUT)
step_pul = Pin(13, Pin.OUT)

# DC모터 핀 설정
motor_dir = Pin(21, Pin.OUT)  # CW/CCW
motor_sd1 = Pin(20, Pin.OUT)
motor_sd2 = Pin(19, Pin.OUT)
motor_pwm = PWM(Pin(18))
motor_pwm.freq(1000)

# 엑셀 (ADC)
accel = ADC(Pin(28))

# 전후진 스위치
fwd_rev_switch = Pin(2, Pin.IN, Pin.PULL_UP)

# 초기 설정
step_en.value(0)
step_rst.value(0)
utime.sleep_ms(10)
step_rst.value(1)

motor_sd1.value(1)
motor_sd2.value(1)

# 스텝모터 회전 함수
def step_rotate(direction='left', steps=100, speed_us=500):
    step_en.value(1)
    step_dir.value(0 if direction == 'left' else 1)
    for _ in range(steps):
        step_pul.value(1)
        utime.sleep_us(speed_us)
        step_pul.value(0)
        utime.sleep_us(speed_us)
    step_en.value(0)

# DC모터 제어 함수 (최대값 250 기준)
def drive_motor(pwm_val, direction='forward'):
    motor_dir.value(1 if direction == 'forward' else 0)  # HIGH: forward, LOW: backward
    motor_pwm.duty_u16(int(pwm_val * 65535 / 250))       # 250 기준 정규화

# 메인 루프
while True:
    accel_val = accel.read_u16()

    # 엑셀 맵핑 (18000 ~ 65535 → 250 ~ 0)
    if accel_val < 18000:
        speed = 0
        motor_sd1.value(0)  # 셧다운
        motor_sd2.value(0)
    else:
        scale = 65535 - 18000
        speed = (65535 - accel_val) * 250 // scale
        speed = min(max(speed, 0), 250)

        motor_sd1.value(1)  # 셧다운 해제
        motor_sd2.value(1)

    # 전후진 스위치 판독
    fwd_rev = fwd_rev_switch.value()
    direction = 'forward' if fwd_rev == 1 else 'backward'

    # 모터 회전
    drive_motor(speed, direction)

    # 출력 상태 확인 (스위치 입력 기준)
    direction_str = 'forward' if fwd_rev == 1 else 'backward'

    print("Accel:", accel_val,
          "Speed:", speed,
          "Direction (switch GPIO2):", direction_str)

    utime.sleep(0.1)
