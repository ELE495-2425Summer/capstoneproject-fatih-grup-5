# TOBB ETÜ ELE495 - Capstone Project: Voice-Controlled Autonomous Mini Vehicle

## Table of Contents
- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Screenshots](#screenshots)
- [Acknowledgements](#acknowledgements)

## Introduction
This project aims to build a system that can understand Turkish natural language voice commands and translate them into basic movement instructions to control a mini autonomous vehicle. It integrates embedded systems, speech recognition, natural language processing, and motor control. The system captures voice input via a microphone, interprets the command using a language model, and executes the movement with sensor assistance. It also provides spoken feedback to the user in Turkish.

## Features

### Hardware
The following hardware components were used:
- [Raspberry Pi 4 Model B (4GB)](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/)
- [L298N Motor Driver](https://www.amazon.com/L298N-Controller-Stepper-Raspberry-Arduino/dp/B083NSB7CH)
- [HC-SR04 Ultrasonic Distance Sensor](https://www.sparkfun.com/products/15569)
- [MPU6050 Gyroscope and Accelerometer](https://www.sparkfun.com/products/11028)
- [USB Microphone](https://www.amazon.com/Plug-Play-Microphone-Compatible-Computer/dp/B08B1V3YQV)
- [Mini 3.5mm Speaker](https://www.amazon.com/s?k=mini+3.5mm+speaker)
- [Mini DC Motor Set with Wheels](https://www.robotistan.com/2li-dc-motor-ve-teker-seti)

### Operating System and Packages
- **OS**: Raspberry Pi OS (Bookworm)
- **Python Version**: 3.11+
- **Python Packages**:
  - `speechbrain`
  - `resemblyzer`
  - `speechrecognition`
  - `sounddevice`
  - `soundfile`
  - `Flask`
  - `openai`
  - `numpy`, `scipy`, `requests`

### Applications
- **Speaker Verification**: Authorize the user based on their voice profile
- **Natural Language Understanding**: Process commands via GPT-based LLM
- **Motor Control**: Execute commands such as forward, backward, left, and right
- **Obstacle Detection**: Use ultrasonic sensor to detect and avoid obstacles
- **Web Interface**: Flask-based interface to monitor system status and command history

### Services
- **LLM API**: Natural language processing via OpenAI GPT-4
- **Flask Server**: Local HTTP interface to monitor and control the system
- **Voice Listener**: Record and process audio commands
- **Motor Control Service**: Control motors via GPIO pins

## Installation

Steps to set up and run the project on Raspberry Pi:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system dependencies
sudo apt install python3-pip python3-dev libatlas-base-dev portaudio19-dev libasound-dev -y

# Clone the project repository
git clone https://github.com/username/project-name.git
cd project-name

# (Optional) Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
