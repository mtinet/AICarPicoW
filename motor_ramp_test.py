from machine import Pin, PWM
import utime

# DC모터 핀 설정 (accelPicoW.py 참고)
motor_dir = Pin(21, Pin.OUT)
motor_sd1 = Pin(20, Pin.OUT)
motor_sd2 = Pin(19, Pin.OUT)
motor_pwm = PWM(Pin(18))
motor_pwm.freq(1000)

# 모터 드라이버 활성화
motor_sd1.value(1)
motor_sd2.value(1)

# 모터 방향 설정 (예: 전진)
motor_dir.value(1)

print("모터 속도 자동 증감 테스트를 시작합니다. 중지하려면 Ctrl+C를 누르세요.")

try:
    # 3번 반복
    for i in range(3):
        print(f"--- Cycle {i + 1} of 3 ---")

        # 최저속도(0)에서 최고속도(65535)까지 점진적으로 증가
        print("Ramping speed down (65500 to 10)...")
        for speed in range(63000, 10000, -256):
            motor_pwm.duty_u16(speed)
            print(f"Speed: {speed:<5}", end='\r')
            utime.sleep_ms(20)
        motor_pwm.duty_u16(10000)
        print("Speed: 10000") # 이전 출력 덮어쓰기
        utime.sleep(3)

        # 최고속도에서 최저속도로 점진적으로 감소
        print("Ramping speed up (10 to 65500)...")
        for speed in range(10000, 63000, 256):
            motor_pwm.duty_u16(speed)
            print(f"Speed: {speed:<5}", end='\r')
            utime.sleep_ms(20)
        motor_pwm.duty_u16(63000)
        print("Speed: 63000               ") # 이전 출력 덮어쓰기
        utime.sleep(3)



    print("\nTest complete. 3 cycles finished.")

except KeyboardInterrupt:
    print("\nTest interrupted by user.")

finally:
    # 프로그램 종료 시 모터를 안전하게 정지
    print("Turning off motor.")
    motor_pwm.duty_u16(0)
    motor_pwm.deinit()
