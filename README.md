# Natural Language Controlled Autonomous Mini Vehicle

## Table of Contents
- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Screenshots](#screenshots)
- [Acknowledgements](#acknowledgements)

## Introduction

This capstone project (ELE495) presents an autonomous mini vehicle that can understand and execute Turkish natural language voice commands. The system integrates cutting-edge AI technologies with robotics to create an intelligent vehicle capable of interpreting conversational commands and translating them into precise movements. By combining Speech-to-Text, Large Language Models, and Text-to-Speech technologies with sensor-based navigation, the project demonstrates a multidisciplinary approach to human-robot interaction.

The vehicle processes voice commands through a sophisticated pipeline: capturing audio, converting speech to text, understanding intent using AI, executing movements safely with sensor feedback, and providing voice confirmations—all in real-time.

## Features

### Hardware Components
- **[Raspberry Pi 5 4GB](https://www.raspberrypi.com/products/raspberry-pi-5/)** - Main control unit running Python
- **Torima K9 Wireless Microphone** - Turkish voice command detection
- **[JBL GO Bluetooth Speaker](https://www.jbl.com/portable-speakers/)** - Voice feedback system
- **[HC-SR04 Ultrasonic Sensor](https://www.sparkfun.com/products/15569)** - Obstacle detection and distance measurement
- **[MPU6050 6-Axis Gyro & Accelerometer](https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/)** - Orientation sensing with PID-controlled turning
- **[L298N Motor Driver](https://www.sparkfun.com/datasheets/Robotics/L298_H_Bridge.pdf)** - Bidirectional motor control
- **DC Motors and Chassis** - Vehicle mobility system
- **[UPS HAT with 2x 18650 Batteries](https://www.waveshare.com/wiki/UPS_HAT)** - Uninterrupted power supply

### Software & Services
- **Operating System**: Raspberry Pi OS
- **Programming Language**: Python
- **Web Framework**: Flask for real-time monitoring interface
- **AI/ML Services**:
  - [OpenAI GPT-3.5 Turbo](https://platform.openai.com/docs/models/gpt-3-5) - Natural language understanding and JSON command generation
  - [Google Speech-to-Text](https://cloud.google.com/speech-to-text) - Voice to text conversion
  - [ElevenLabs Text-to-Speech](https://elevenlabs.io/) - Turkish voice synthesis for feedback
- **Control Algorithms**: PID control for stable navigation

### Key Capabilities
- Natural language understanding in Turkish
- Real-time voice command processing
- Autonomous navigation with obstacle avoidance
- Voice feedback for executed actions
- Web-based monitoring dashboard
- Multi-threaded operation for concurrent processing

## Installation

### Prerequisites
- Raspberry Pi 5 with Raspberry Pi OS installed
- Python 3.8 or higher
- Active internet connection for cloud services
- API keys for:
  - OpenAI GPT-3.5
  - Google Speech-to-Text
  - ElevenLabs TTS

### Hardware Setup
1. Connect the MPU6050 sensor to the I2C pins on Raspberry Pi
2. Wire the HC-SR04 ultrasonic sensor to GPIO pins
3. Connect the L298N motor driver to the motors and Raspberry Pi
4. Set up the UPS HAT with batteries for power
5. Pair the Bluetooth speaker and configure the wireless microphone

### Software Installation
```bash
# Clone the repository
git clone https://github.com/username/autonomous-mini-vehicle.git
cd autonomous-mini-vehicle

# Install required Python packages
pip install -r requirements.txt

# Install system dependencies
sudo apt-get update
sudo apt-get install python3-flask python3-pip portaudio19-dev

# Configure API keys
cp .env.example .env
# Edit .env file with your API keys
