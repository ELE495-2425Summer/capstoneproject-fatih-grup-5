import time
from gpiozero import Motor, PWMOutputDevice, DistanceSensor
import smbus2 as smbus
import tempfile
import requests
import soundfile as sf
import sounddevice as sd


# MPU6050 sabitleri
PWR_MGMT_1 = 0x6B
GYRO_ZOUT_H = 0x47
GYRO_SCALE = 131.0  # ±250°/s

def speak_text_with_elevenlabs(text):
    try:
        url = "https://api.elevenlabs.io/v1/text-to-speech/IuRRIAcbQK5AQk1XevPj"
        headers = {
            "xi-api-key": "your-api-key",
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.2}
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        audio_data = response.content
        temp_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        with open(temp_audio_path, "wb") as f:
            f.write(audio_data)

        data, samplerate = sf.read(temp_audio_path)
        sd.play(data, samplerate)
        sd.wait()
        os.remove(temp_audio_path)

    except Exception as e:
        print(f"TTS error: {e}")

class MPU6050:
    def __init__(self, i2c_bus=1, addr=0x68):
        self.addr = addr
        self.heading = 0.0
        self.offset = 0.0
        self.prev_time = time.time()
        self.stationary_threshold = 0.3

        self.bus = smbus.SMBus(i2c_bus)
        self.bus.write_byte_data(self.addr, PWR_MGMT_1, 0)
        time.sleep(0.1)

    def read_gyro_z(self):
        high = self.bus.read_byte_data(self.addr, GYRO_ZOUT_H)
        low = self.bus.read_byte_data(self.addr, GYRO_ZOUT_H + 1)
        value = (high << 8) | low
        if value >= 0x8000:
            value = -((65535 - value) + 1)
        return value

    def calibrate(self, samples=200):
        print("Calibrating... Do not move!")
        total = 0
        for i in range(samples):
            total += self.read_gyro_z() / GYRO_SCALE
            time.sleep(0.01)
            if (i + 1) % 50 == 0:
                print(f"Progress: {i + 1}/{samples}")
        self.offset = total / samples
        print(f"Calibration complete! Offset: {self.offset:.3f}°/s")

    def get_rotation_rate(self):
        raw = self.read_gyro_z()
        rate = (raw / GYRO_SCALE) - self.offset
        return 0.0 if abs(rate) < self.stationary_threshold else rate

    def update_heading(self):
        now = time.time()
        dt = now - self.prev_time
        if dt > 0:
            rate = self.get_rotation_rate()
            if abs(rate) > 0.1:
                self.heading += rate * dt
                while self.heading > 180:
                    self.heading -= 360
                while self.heading < -180:
                    self.heading += 360
            self.prev_time = now
        return self.heading

    def reset_heading(self):
        self.heading = 0.0
        self.prev_time = time.time()

    def get_heading(self):
        return self.heading

class Robot:
    def __init__(self, gyro_sensor, left_fwd=13, left_bwd=19, right_fwd=22, right_bwd=27, left_pwm=26, right_pwm=18):
        self.gyro = gyro_sensor
        self.sensor = DistanceSensor(echo=24, trigger=23, max_distance=1.0)

        self.left_motor = Motor(forward=left_fwd, backward=left_bwd)
        self.right_motor = Motor(forward=right_fwd, backward=right_bwd)
        self.left_speed = PWMOutputDevice(left_pwm)
        self.right_speed = PWMOutputDevice(right_pwm)
        self.halt()

    # ------------------ Temel Motor Kontrolü ------------------ #

    def halt(self):
        self.left_motor.stop()
        self.right_motor.stop()
        self.left_speed.value = 0
        self.right_speed.value = 0

    def drive(self, left_forward, right_forward, speed=1.0):
        speed = max(0.0, min(1.0, speed))
        self.left_motor.forward() if left_forward else self.left_motor.backward()
        self.right_motor.forward() if right_forward else self.right_motor.backward()
        self.left_speed.value = speed
        self.right_speed.value = speed

    # ------------------ İleri Gitme ------------------ #

    def move_forward(self, duration_sec, speed=1.0, kp=0.02, ki=0.005, kd=0.08):
        start_time = time.time()
        self.gyro.reset_heading()

        integral = 0.0
        previous_error = 0.0
        previous_time = time.time()
        max_integral = 1.0 / ki if ki > 0 else float('inf')
        deadband = 0

        while time.time() - start_time < duration_sec:
            distance_cm = self.sensor.distance * 100
            if distance_cm < 40:
                print(f"🚧 Engel algılandı! Mesafe: {distance_cm:.1f} cm")
                self.halt()
                speak_text_with_elevenlabs("Engel algılandı. Duruyorum.")
                return False

            current_time = time.time()
            dt = current_time - previous_time
            if dt < 1e-6:
                time.sleep(0.01)
                continue

            current_heading = self.gyro.update_heading()
            error = current_heading if abs(current_heading) > deadband else 0.0

            integral += error * dt
            integral = max(-max_integral, min(max_integral, integral))
            derivative = (error - previous_error) / dt if dt > 0 else 0.0
            correction = kp * error + ki * integral + kd * derivative
            correction = max(-0.5, min(0.5, correction))

            left_power = max(0.0, min(1.0, speed + correction))
            right_power = max(0.0, min(1.0, speed - correction))

            self.left_motor.forward()
            self.right_motor.forward()
            self.left_speed.value = left_power
            self.right_speed.value = right_power

            print(f"🧭 Heading: {current_heading:.2f}° | Error: {error:.2f}° | "
                  f"P: {kp*error:.3f} I: {ki*integral:.3f} D: {kd*derivative:.3f} | "
                  f"Correction: {correction:.3f} | L: {left_power:.2f}, R: {right_power:.2f}")

            previous_error = error
            previous_time = current_time
            time.sleep(0.02)

        self.halt()
        return True

    # ------------------ Engel Algılanana Kadar İleri Git ------------------ #

    def move_until_obstacle(self, speed=1.0, kp=0.02, ki=0.005, kd=0.08, stop_distance_cm=40):
        self.gyro.reset_heading()

        integral = 0.0
        previous_error = 0.0
        previous_time = time.time()
        max_integral = 1.0 / ki if ki > 0 else float('inf')
        deadband = 0

        while True:
            distance_cm = self.sensor.distance * 100
            if distance_cm < stop_distance_cm:
                print(f"🚧 Engel algılandı! Mesafe: {distance_cm:.1f} cm")
                self.halt()
                speak_text_with_elevenlabs("Engel algılandı. Duruyorum.")
                return

            current_time = time.time()
            dt = current_time - previous_time
            if dt < 1e-6:
                time.sleep(0.01)
                continue

            current_heading = self.gyro.update_heading()
            error = current_heading if abs(current_heading) > deadband else 0.0

            integral += error * dt
            integral = max(-max_integral, min(max_integral, integral))
            derivative = (error - previous_error) / dt if dt > 0 else 0.0
            correction = kp * error + ki * integral + kd * derivative
            correction = max(-0.5, min(0.5, correction))

            left_power = max(0.0, min(1.0, speed + correction))
            right_power = max(0.0, min(1.0, speed - correction))

            self.left_motor.forward()
            self.right_motor.forward()
            self.left_speed.value = left_power
            self.right_speed.value = right_power

            print(f"🧭 Heading: {current_heading:.2f}° | Error: {error:.2f}° | "
                  f"P: {kp*error:.3f} I: {ki*integral:.3f} D: {kd*derivative:.3f} | "
                  f"Correction: {correction:.3f} | L: {left_power:.2f}, R: {right_power:.2f}")

            previous_error = error
            previous_time = current_time
            time.sleep(0.02)

    # ------------------ Dönüşler ------------------ #

    def _execute_pid_turn(self, angle_deg, direction, kp=1.2, ki=0.0, kd=0.15, max_power=0.5, recalculate_offset=False):
        if recalculate_offset:
            self.halt()
            self.gyro.calibrate()
        self.gyro.reset_heading()

        previous_error = abs(angle_deg)
        cumulative_error = 0.0
        previous_time = time.time()
        left_fwd, right_fwd = (True, False) if direction == "right" else (False, True)

        timeout = 10.0
        start_time = time.time()

        while True:
            now = time.time()
            dt = max(0.001, now - previous_time)
            previous_time = now

            current_angle = abs(self.gyro.update_heading())
            error = abs(angle_deg) - current_angle
            cumulative_error += error * dt
            derivative = (error - previous_error) / dt
            previous_error = error

            control = kp * error + ki * cumulative_error + kd * derivative
            speed = max(0.15, min(max_power, abs(control) * 0.1))
            self.drive(left_fwd, right_fwd, speed)

            print(f"🔄 Target: {angle_deg:.1f}° | Now: {current_angle:.1f}° | Error: {error:.1f}° | Speed: {speed:.2f}")

            if error <= 1.0:
                print("✅ Dönüş tamamlandı.")
                break
            if now - start_time > timeout:
                print("⏱️ Zaman aşımı.")
                break

            time.sleep(0.01)

        self.halt()

    def turn_right(self, degrees, **kwargs):
        self._execute_pid_turn(degrees, direction="right", **kwargs)

    def turn_left(self, degrees, **kwargs):
        self._execute_pid_turn(degrees, direction="left", **kwargs)
    
    def turn_back(self, **kwargs):
        self._execute_pid_turn(180, direction="right", **kwargs)

    
    def move_back(self, duration_sec, speed=1.0, kp=0.015, ki=0.005, kd=0.08):
        self._execute_pid_turn(180, direction="right", kp=1.0, ki=0.0, kd=0.0)
        self.move_forward(duration_sec, speed=speed, kp=kp, ki=ki, kd=kd)

    def shutdown(self):
        self.halt()
