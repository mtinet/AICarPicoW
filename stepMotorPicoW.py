from machine import Pin
import utime

# 핀 설정
step_en = Pin(10, Pin.OUT)   # Enable
step_rst = Pin(11, Pin.OUT)  # Reset
step_dir = Pin(12, Pin.OUT)  # Direction
step_pul = Pin(13, Pin.OUT)  # Step

# 회전 위치 추적 변수
rotate_pos = 10
rotate_mid = 10
rotate_left_limit = 0
rotate_right_limit = 20

# 스텝 수 설정
STEPS_PER_REV = 400  # 점퍼 off-on-off (200pulse/rev) 기준, 2회전

# 초기화: 전원 투입 시
step_en.value(0)       # EN: LOW로 초기화 (비활성)
step_rst.value(0)      # RST: LOW로 초기화
utime.sleep_ms(10)

# 회전 함수
def step_rotate(direction='left', degrees=30):
    global rotate_pos

    # 1 step = 0.036 degrees (with 1:50 gear), 여기에 실제 회전 각도 보정을 위해 ×2
    steps = int(degrees / 0.036 * 2)

    if direction == 'left':
        if rotate_pos <= rotate_left_limit:
            rotate_pos = rotate_left_limit
            return
        step_dir.value(0)
        rotate_pos -= 1
    elif direction == 'right':
        if rotate_pos >= rotate_right_limit:
            rotate_pos = rotate_right_limit
            return
        step_dir.value(1)
        rotate_pos += 1

    step_en.value(1)  # Enable

    for _ in range(steps):
        step_pul.value(1)
        utime.sleep_us(500)
        step_pul.value(0)
        utime.sleep_us(500)

    step_en.value(0)
    print("rotate_pos:", rotate_pos, "degrees rotated:", degrees)



# 테스트 루프: 왼쪽 1회, 오른쪽 1회 반복
while True:
    print("LEFT")
    step_rotate('left')
    utime.sleep(1)

    print("RIGHT")
    step_rotate('right')
    utime.sleep(1)
