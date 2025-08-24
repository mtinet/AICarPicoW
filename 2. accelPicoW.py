from machine import Pin, PWM, ADC
import utime

# DC모터 핀 설정
motor_dir = Pin(21, Pin.OUT)  # CW/CCW
motor_sd1 = Pin(20, Pin.OUT)
motor_sd2 = Pin(19, Pin.OUT)
motor_pwm = PWM(Pin(18))
motor_pwm.freq(1000)

# 엑셀 (ADC)
accel = ADC(Pin(28))

# 전후진 스위치
fwd_rev_switch = Pin(1, Pin.IN, Pin.PULL_UP)

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

# DC모터 제어 함수
def drive_motor(speed_val, direction='forward'):
    # speed_val 값을 PWM 값으로 직접 사용
    motor_dir.value(1 if direction == 'forward' else 0)  # HIGH: forward, LOW: backward
    motor_pwm.duty_u16(speed_val)

# 메인 루프
while True:
    accel_val = accel.read_u16()

    # --- 사용자 정의 엑셀 매핑 ---
    # 입력 (accel_val): 18500 ~ 65500
    # 출력 (speed): 10000 (최고 속도) ~ 63000 (정지)
    in_min = 18500
    in_max = 65500
    out_max_speed = 10000
    out_min_speed = 63000

    # 입력 값을 유효 범위(in_min ~ in_max) 내로 고정(clamp)
    if accel_val < in_min:
        accel_val = in_min
    elif accel_val > in_max:
        accel_val = in_max

    # 역방향 선형 매핑
    # 이제 accel_val은 항상 유효 범위 안에 있으므로 직접 공식 적용
    speed = out_min_speed - ((accel_val - in_min) * (out_min_speed - out_max_speed)) // (in_max - in_min)

    # 모터 드라이버는 항상 활성화 상태를 유지합니다. (셧다운 기능 비활성화)

    # 전후진 스위치 판독
    fwd_rev = fwd_rev_switch.value()
    direction = 'forward' if fwd_rev == 1 else 'backward'

    # 모터 회전 (변환된 speed 값 사용)
    drive_motor(speed, direction)

    # 출력 상태 확인 (스위치 입력 기준)
    direction_str = 'forward' if fwd_rev == 1 else 'backward' 

    print("Accel:", accel_val,
          "Speed:", speed,
          "Direction (switch GPIO2):", direction_str)

    utime.sleep(0.1)
