from flask import Flask, render_template_string, redirect, url_for, request, jsonify, flash
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import speech_recognition as sr
import tempfile
import threading
import datetime
import os
import json
from openai import OpenAI
import requests
import soundfile as sf
from speechbrain.inference.speaker import SpeakerRecognition
from werkzeug.utils import secure_filename

from pidandgyro import Robot, MPU6050
from INA219 import INA219

app = Flask(__name__)

recording = []
fs = 16000
is_recording = False
command_history = []
llm_output = []

# Gerçek zamanlı eylem takibi 
current_action = "😴 Bekliyor - Yeni komut bekleniyor"
action_history = []

gyro = MPU6050()
robot = Robot(gyro)

# Battery monitor initialization
try:
    battery_monitor = INA219(addr=0x42)  
    battery_available = True
    print("✅ Battery monitor initialized")
except Exception as e:
    battery_monitor = None
    battery_available = False
    print(f"❌ Battery monitor failed to initialize: {e}")

# Konuşmacı tanıma modeli (SpeechBrain)
recognizer_model = SpeakerRecognition.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")

# Yetkili kullanıcılar ve dosyaları - JSON dosyasından yükle
USERS_FILE = 'authorized_users.json'
VOICES_DIR = 'authorized_voices'

# Klasör oluşturma
os.makedirs(VOICES_DIR, exist_ok=True)

def load_authorized_users():
    """JSON dosyasından yetkili kullanıcıları yükle"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Kullanıcı dosyası yüklenirken hata: {e}")
    
    # Varsayılan kullanıcılar(ekip üyeleri)
    default_users = {
        "ata": [f"{VOICES_DIR}/ata.wav"],
        "arda": [f"{VOICES_DIR}/arda.wav"],
        "can": [f"{VOICES_DIR}/can.wav"],
        "atakan": [f"{VOICES_DIR}/atakan.wav"]
    }
    save_authorized_users(default_users)
    return default_users

def save_authorized_users(users_dict):
    """Yetkili kullanıcıları JSON dosyasına kaydet"""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_dict, f, indent=2, ensure_ascii=False)
        print("✅ Kullanıcı listesi kaydedildi")
    except Exception as e:
        print(f"Kullanıcı dosyası kaydedilirken hata: {e}")

# Kullanıcıları yükleme
authorized_files = load_authorized_users()
threshold = 0.40

print("Yüklenen yetkili kullanıcılar:", list(authorized_files.keys()))

def update_current_action(action_text):
    """Şu anki eylemi güncelle ve geçmişe ekle"""
    global current_action, action_history
    current_action = action_text
    
    # geçmişe ekle
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    action_history.insert(0, {"action": action_text, "time": timestamp})
    
    # Son 20 eylemi tut
    if len(action_history) > 20:
        action_history = action_history[:20]
    
    print(f"🤖 Şu anda: {action_text}")

def get_battery_info():
    """anlık batarya  durumu"""
    if not battery_available or battery_monitor is None:
        return {
            'voltage': 0.0,
            'current': 0.0,
            'power': 0.0,
            'percentage': 0,
            'status': 'Unknown'
        }
    
    try:
        bus_voltage = battery_monitor.getBusVoltage_V()
        current = battery_monitor.getCurrent_mA()
        power = battery_monitor.getPower_W()
        
        # Yüzde hesabı
        # 2S LiPo batarya (6V-8.4V aralığı)
        min_voltage = 6.0  # Minimum güvenli voltaj
        max_voltage = 8.4  # Maximum voltaj (tam şarjlı)
        
        percentage = ((bus_voltage - min_voltage) / (max_voltage - min_voltage)) * 100
        percentage = max(0, min(100, percentage))  # 0-100 arası sınırla
        
        # Durum kararı
        if percentage > 75:
            status = 'Excellent'
        elif percentage > 50:
            status = 'Good'
        elif percentage > 25:
            status = 'Low'
        elif percentage > 10:
            status = 'Critical'
        else:
            status = 'Empty'
        
        return {
            'voltage': round(bus_voltage, 2),
            'current': round(current, 1),
            'power': round(power, 2),
            'percentage': round(percentage, 1),
            'status': status
        }
    except Exception as e:
        print(f"Battery reading error: {e}")
        return {
            'voltage': 0.0,
            'current': 0.0,
            'power': 0.0,
            'percentage': 0,
            'status': 'Error'
        }

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

client = OpenAI(api_key="your-api-key")

template = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DOĞAL DİL İLE KONTROL EDİLEBİLEN OTONOM MİNİ ARAÇ</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #ffffff;
            min-height: 100vh;
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            padding: 30px 0;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            background: linear-gradient(45deg, #ffffff, #e0e7ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .subtitle {
            font-size: 1.1rem;
            opacity: 0.9;
            margin-top: 10px;
        }

        .controls {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 40px;
            flex-wrap: wrap;
        }

        .control-button {
            background: linear-gradient(45deg, #ff6b6b, #ee5a52);
            border: none;
            padding: 15px 30px;
            border-radius: 50px;
            color: white;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }

        .control-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 12px 35px rgba(0, 0, 0, 0.3);
        }

        .control-button.stop {
            background: linear-gradient(45deg, #6c757d, #5a6268);
        }

        .control-button.stop:hover {
            background: linear-gradient(45deg, #5a6268, #495057);
        }

        .control-button.user-management {
            background: linear-gradient(45deg, #28a745, #20c997);
        }

        .control-button.user-management:hover {
            background: linear-gradient(45deg, #20c997, #17a2b8);
        }

        .content-section {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            color: #2c3e50;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.3);
        }

        .section-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: #2c3e50;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .section-title::before {
            content: '';
            width: 4px;
            height: 25px;
            background: linear-gradient(45deg, #3498db, #2980b9);
            border-radius: 2px;
        }

        /* Gerçek zamanlı eylem stilleri */
        .current-action {
            background: linear-gradient(135deg, #e8f5e8, #d4edda);
            border: 3px solid #28a745;
            padding: 25px;
            border-radius: 15px;
            font-size: 1.4rem;
            font-weight: 700;
            line-height: 1.6;
            color: #155724;
            min-height: 80px;
            display: flex;
            align-items: center;
            text-align: center;
            justify-content: center;
            animation: pulse-action 3s infinite;
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.3);
        }

        @keyframes pulse-action {
            0% { 
                background: linear-gradient(135deg, #e8f5e8, #d4edda);
                transform: scale(1);
            }
            50% { 
                background: linear-gradient(135deg, #d4edda, #c3e6cb);
                transform: scale(1.02);
            }
            100% { 
                background: linear-gradient(135deg, #e8f5e8, #d4edda);
                transform: scale(1);
            }
        }

        .action-history {
            max-height: 350px;
            overflow-y: auto;
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            border: 2px solid #e9ecef;
        }

        .action-item {
            background: #ffffff;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 10px;
            border-left: 4px solid #6c757d;
            font-size: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s ease;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        }

        .action-item:hover {
            transform: translateX(5px);
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
        }

        .action-item:first-child {
            border-left-color: #28a745;
            background: #f8fff8;
        }

        .action-time {
            color: #6c757d;
            font-size: 0.85rem;
            font-weight: 600;
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 12px;
        }

        .section-subtitle {
            margin-top: 25px;
            margin-bottom: 15px;
            color: #2c3e50;
            font-size: 1.2rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .command-list {
            list-style: none;
            counter-reset: command-counter;
        }

        .command-item {
            counter-increment: command-counter;
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #28a745;
            position: relative;
            transition: all 0.3s ease;
        }

        .command-item:hover {
            transform: translateX(5px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }

        .command-item::before {
            content: counter(command-counter);
            position: absolute;
            left: -2px;
            top: -2px;
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            width: 25px;
            height: 25px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: bold;
        }

        .command-content {
            background: white;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            line-height: 1.4;
            color: #2c3e50;
            border: 1px solid #e9ecef;
            white-space: pre-wrap;
            word-break: break-all;
            margin-left: 15px;
        }

        .status-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(40, 167, 69, 0.9);
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px);
        }

        .status-indicator.recording {
            background: rgba(220, 53, 69, 0.9);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }

        .empty-state {
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 30px;
        }

        /* Battery Styles */
        .battery-info {
            display: flex;
            align-items: center;
            gap: 30px;
            flex-wrap: wrap;
        }

        .battery-visual {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .battery-container {
            position: relative;
            width: 80px;
            height: 40px;
            border: 3px solid #2c3e50;
            border-radius: 8px;
            background: #f8f9fa;
            display: flex;
            align-items: center;
        }

        .battery-level {
            height: 100%;
            border-radius: 4px;
            transition: all 0.5s ease;
            background: linear-gradient(90deg, #28a745, #20c997);
        }

        .battery-level.low {
            background: linear-gradient(90deg, #ffc107, #fd7e14);
        }

        .battery-level.critical {
            background: linear-gradient(90deg, #dc3545, #c82333);
        }

        .battery-tip {
            position: absolute;
            right: -8px;
            top: 50%;
            transform: translateY(-50%);
            width: 5px;
            height: 20px;
            background: #2c3e50;
            border-radius: 0 3px 3px 0;
        }

        .battery-percentage {
            font-size: 2rem;
            font-weight: 700;
            color: #2c3e50;
            min-width: 80px;
        }

        .battery-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 15px;
            flex: 1;
        }

        .battery-stat {
            display: flex;
            flex-direction: column;
            gap: 5px;
            padding: 10px;
            background: #e9ecef;
            border-radius: 8px;
        }

        .stat-label {
            font-size: 0.9rem;
            color: #6c757d;
            font-weight: 500;
        }

        .stat-value {
            font-size: 1.1rem;
            font-weight: 600;
            color: #2c3e50;
        }

        .battery-status.excellent {
            color: #28a745;
        }

        .battery-status.good {
            color: #20c997;
        }

        .battery-status.low {
            color: #ffc107;
        }

        .battery-status.critical {
            color: #dc3545;
        }

        @media (max-width: 768px) {
            .container {
                padding: 15px;
            }
            
            .header h1 {
                font-size: 1.8rem;
            }
            
            .controls {
                flex-direction: column;
                align-items: center;
            }
            
            .control-button {
                width: 200px;
                justify-content: center;
            }

            .battery-info {
                flex-direction: column;
                gap: 20px;
            }

            .battery-details {
                grid-template-columns: repeat(2, 1fr);
            }

            .current-action {
                font-size: 1.2rem;
                padding: 20px;
            }

            .action-history {
                max-height: 250px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>DOĞAL DİL İLE KONTROL EDİLEBİLEN OTONOM MİNİ ARAÇ</h1>
            <div class="subtitle">Sesli komutlarla akıllı araç kontrolü</div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="controls">
            <form action="/start" method="get">
                <button type="submit" class="control-button">
                    🔴 Kaydı Başlat
                </button>
            </form>
            <form action="/stop" method="get">
                <button type="submit" class="control-button stop">
                    ⏹️ Kaydı Durdur
                </button>
            </form>
            <a href="/users" class="control-button user-management">
                👥 Kullanıcı Yönetimi
            </a>
        </div>

        <div class="content-section">
            <h2 class="section-title">🔋 Batarya Durumu</h2>
            <div class="battery-info">
                <div class="battery-visual">
                    <div class="battery-container">
                        <div class="battery-level" id="batteryLevel"></div>
                        <div class="battery-tip"></div>
                    </div>
                    <div class="battery-percentage" id="batteryPercentage">{{ battery.percentage }}%</div>
                </div>
                <div class="battery-details">
                    <div class="battery-stat">
                        <span class="stat-label">Gerilim:</span>
                        <span class="stat-value" id="batteryVoltage">{{ battery.voltage }}V</span>
                    </div>
                    <div class="battery-stat">
                        <span class="stat-label">Akım:</span>
                        <span class="stat-value" id="batteryCurrent">{{ battery.current }}mA</span>
                    </div>
                    <div class="battery-stat">
                        <span class="stat-label">Güç:</span>
                        <span class="stat-value" id="batteryPower">{{ battery.power }}W</span>
                    </div>
                    <div class="battery-stat">
                        <span class="stat-label">Durum:</span>
                        <span class="stat-value battery-status" id="batteryStatus">{{ battery.status }}</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="content-section">
            <h2 class="section-title">🤖 Robot Durumu</h2>
            <div class="current-action" id="currentAction">{{ current_action }}</div>
            
            <h3 class="section-subtitle">📝 Son Eylemler</h3>
            <div class="action-history" id="actionHistory">
                {% if action_history %}
                    {% for action in action_history %}
                        <div class="action-item">
                            <span>{{ action.action }}</span>
                            <span class="action-time">{{ action.time }}</span>
                        </div>
                    {% endfor %}
                {% else %}
                    <div class="empty-state">Henüz eylem geçmişi yok...</div>
                {% endif %}
            </div>
        </div>

        <div class="content-section">
            <h2 class="section-title">🧠 LLM JSON Komut Geçmişi</h2>
            {% if llm_commands %}
                <ol class="command-list">
                {% for cmd in llm_commands %}
                    <li class="command-item">
                        <pre class="command-content">{{ cmd }}</pre>
                    </li>
                {% endfor %}
                </ol>
            {% else %}
                <div class="empty-state">
                    Henüz komut geçmişi bulunmuyor...
                </div>
            {% endif %}
        </div>
    </div>

    <div class="status-indicator" id="statusIndicator">
        Sistem Hazır
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const startButton = document.querySelector('form[action="/start"] button');
            const stopButton = document.querySelector('form[action="/stop"] button');
            const statusIndicator = document.getElementById('statusIndicator');

            startButton.addEventListener('click', function() {
                statusIndicator.textContent = 'Kayıt Başlatılıyor...';
                statusIndicator.classList.add('recording');
            });

            stopButton.addEventListener('click', function() {
                statusIndicator.textContent = 'Kayıt Durduruluyor...';
                statusIndicator.classList.remove('recording');
            });

            // Battery level animation and updates
            function updateBatteryDisplay(percentage, status) {
                const batteryLevel = document.getElementById('batteryLevel');
                const batteryPercentage = document.getElementById('batteryPercentage');
                const batteryStatus = document.getElementById('batteryStatus');
                
                if (batteryLevel && batteryPercentage) {
                    batteryLevel.style.width = percentage + '%';
                    batteryPercentage.textContent = percentage + '%';
                    
                    // Update battery level color based on percentage
                    batteryLevel.classList.remove('low', 'critical');
                    if (percentage <= 10) {
                        batteryLevel.classList.add('critical');
                    } else if (percentage <= 25) {
                        batteryLevel.classList.add('low');
                    }
                }
                
                if (batteryStatus) {
                    batteryStatus.className = 'stat-value battery-status ' + status.toLowerCase();
                }
            }

            // Auto-refresh battery status every 10 seconds
            function refreshBatteryStatus() {
                fetch('/battery')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('batteryVoltage').textContent = data.voltage + 'V';
                        document.getElementById('batteryCurrent').textContent = data.current + 'mA';
                        document.getElementById('batteryPower').textContent = data.power + 'W';
                        updateBatteryDisplay(data.percentage, data.status);
                    })
                    .catch(error => console.log('Battery update failed:', error));
            }

            // *** YENİ: Gerçek zamanlı eylem güncelleme ***
            function updateCurrentAction() {
                fetch('/current_action')
                    .then(response => response.json())
                    .then(data => {
                        // Şu anki eylemi güncelle
                        document.getElementById('currentAction').textContent = data.current_action;
                        
                        // Eylem geçmişini güncelle
                        const historyDiv = document.getElementById('actionHistory');
                        historyDiv.innerHTML = '';
                        
                        if (data.action_history.length > 0) {
                            data.action_history.forEach((item, index) => {
                                const actionDiv = document.createElement('div');
                                actionDiv.className = 'action-item';
                                if (index === 0) actionDiv.style.borderLeftColor = '#28a745';
                                
                                actionDiv.innerHTML = `
                                    <span>${item.action}</span>
                                    <span class="action-time">${item.time}</span>
                                `;
                                historyDiv.appendChild(actionDiv);
                            });
                        } else {
                            historyDiv.innerHTML = '<div class="empty-state">Henüz eylem geçmişi yok...</div>';
                        }
                    })
                    .catch(error => console.log('Action update failed:', error));
            }

            // Initial battery display setup
            const initialPercentage = parseFloat(document.getElementById('batteryPercentage').textContent);
            const initialStatus = document.getElementById('batteryStatus').textContent;
            updateBatteryDisplay(initialPercentage, initialStatus);

            // Set up auto-refresh intervals
            setInterval(refreshBatteryStatus, 10000);  // Batarya 10 saniyede bir
            setInterval(updateCurrentAction, 2000);    // Eylemler 2 saniyede bir

            // İlk yüklemeler
            updateCurrentAction();
        });
    </script>
</body>
</html>
"""

user_management_template = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kullanıcı Yönetimi - Robot Kontrol</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #ffffff;
            min-height: 100vh;
            line-height: 1.6;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            padding: 30px 0;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .header h1 {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 10px;
            color: #ffffff;
        }

        .back-button {
            background: linear-gradient(45deg, #6c757d, #5a6268);
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 30px;
            transition: all 0.3s ease;
        }

        .back-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(108, 117, 125, 0.3);
        }

        .content-section {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            color: #2c3e50;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        }

        .section-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 20px;
            color: #2c3e50;
        }

        .user-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .user-card {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            border: 2px solid #e9ecef;
            transition: all 0.3s ease;
        }

        .user-card:hover {
            border-color: #3498db;
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
        }

        .user-name {
            font-size: 1.3rem;
            font-weight: 700;
            color: #2c3e50;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .user-files {
            font-size: 0.95rem;
            color: #6c757d;
            margin-bottom: 15px;
            background: #e9ecef;
            padding: 8px 12px;
            border-radius: 6px;
        }

        .delete-user-btn {
            background: linear-gradient(45deg, #dc3545, #c82333);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
        }

        .delete-user-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(220, 53, 69, 0.4);
        }

        .add-user-form {
            background: linear-gradient(135deg, #e3f2fd, #f3e5f5);
            border-radius: 15px;
            padding: 30px;
            border: 2px dashed #3498db;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #2c3e50;
            font-size: 1.1rem;
        }

        .form-input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: #ffffff;
        }

        .form-input:focus {
            outline: none;
            border-color: #3498db;
            box-shadow: 0 0 10px rgba(52, 152, 219, 0.2);
        }

        .file-input {
            padding: 8px;
        }

        .add-user-btn {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 30px;
            font-size: 1.1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
        }

        .add-user-btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(40, 167, 69, 0.4);
        }

        .flash-messages {
            margin-bottom: 25px;
        }

        .flash-message {
            padding: 15px 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            font-weight: 600;
            font-size: 1rem;
        }

        .flash-success {
            background: #d4edda;
            color: #155724;
            border: 2px solid #c3e6cb;
        }

        .flash-error {
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #f5c6cb;
        }

        .empty-state {
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 40px;
            font-size: 1.1rem;
        }

        @media (max-width: 768px) {
            .container {
                padding: 15px;
            }
            
            .header h1 {
                font-size: 1.8rem;
            }
            
            .user-list {
                grid-template-columns: 1fr;
            }
            
            .add-user-form {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👥 Kullanıcı Yönetimi</h1>
        </div>

        <a href="/" class="back-button">
            ← Ana Sayfaya Dön
        </a>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <div class="content-section">
            <h2 class="section-title">🔊 Mevcut Yetkili Kullanıcılar</h2>
            {% if users %}
                <div class="user-list">
                    {% for username, files in users.items() %}
                        <div class="user-card">
                            <div class="user-name">
                                👤 {{ username.title() }}
                            </div>
                            <div class="user-files">
                                📁 Ses dosyası: {{ files[0].split('/')[-1] }}
                            </div>
                            <form action="/delete_user/{{ username }}" method="post" 
                                  onsubmit="return confirm('{{ username }} kullanıcısını silmek istediğinizden emin misiniz?')">
                                <button type="submit" class="delete-user-btn">
                                    🗑️ Kullanıcıyı Sil
                                </button>
                            </form>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <div class="empty-state">
                    Henüz yetkili kullanıcı bulunmuyor...
                </div>
            {% endif %}
        </div>

        <div class="content-section">
            <h2 class="section-title">➕ Yeni Kullanıcı Ekle</h2>
            <form action="/add_user" method="post" enctype="multipart/form-data" class="add-user-form">
                <div class="form-group">
                    <label for="username" class="form-label">👤 Kullanıcı Adı:</label>
                    <input type="text" id="username" name="username" class="form-input" 
                           placeholder="Örn: ahmet" required>
                </div>
                <div class="form-group">
                    <label for="voice_file" class="form-label">🎤 Ses Dosyası (WAV, 5 saniye):</label>
                    <input type="file" id="voice_file" name="voice_file" class="form-input file-input" 
                           accept=".wav" required>
                </div>
                <button type="submit" class="add-user-btn">
                    ✨ Kullanıcı Ekle
                </button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    battery_info = get_battery_info()
    return render_template_string(template,
                                  current_action=current_action,
                                  action_history=action_history,
                                  llm_commands=llm_output,
                                  battery=battery_info)

@app.route("/users")
def user_management():
    """Kullanıcı yönetimi sayfası"""
    return render_template_string(user_management_template, users=authorized_files)

@app.route("/add_user", methods=["POST"])
def add_user():
    """Yeni kullanıcı ekle"""
    global authorized_files
    
    try:
        username = request.form.get('username', '').lower().strip()
        voice_file = request.files.get('voice_file')
        
        if not username:
            flash('Kullanıcı adı boş olamaz!', 'error')
            return redirect(url_for('user_management'))
        
        if not voice_file or voice_file.filename == '':
            flash('Ses dosyası seçilmedi!', 'error')
            return redirect(url_for('user_management'))
        
        if username in authorized_files:
            flash(f'"{username}" kullanıcısı zaten mevcut!', 'error')
            return redirect(url_for('user_management'))
        
        # Dosya güvenliği
        filename = secure_filename(voice_file.filename)
        if not filename.lower().endswith('.wav'):
            flash('Sadece WAV dosyaları kabul edilir!', 'error')
            return redirect(url_for('user_management'))
        
        # Dosyayı kaydet
        voice_filename = f"{username}.wav"
        voice_path = os.path.join(VOICES_DIR, voice_filename)
        voice_file.save(voice_path)
        
        # Kullanıcıyı ekle
        authorized_files[username] = [voice_path]
        save_authorized_users(authorized_files)
        
        flash(f'✅ "{username}" kullanıcısı başarıyla eklendi!', 'success')
        print(f"✅ Yeni kullanıcı eklendi: {username}")
        
    except Exception as e:
        flash(f'Hata: {str(e)}', 'error')
        print(f"❌ Kullanıcı ekleme hatası: {e}")
    
    return redirect(url_for('user_management'))

@app.route("/delete_user/<username>", methods=["POST"])
def delete_user(username):
    """Kullanıcı sil"""
    global authorized_files
    
    try:
        if username not in authorized_files:
            flash(f'"{username}" kullanıcısı bulunamadı!', 'error')
            return redirect(url_for('user_management'))
        
        # Ses dosyasını sil
        for voice_file in authorized_files[username]:
            if os.path.exists(voice_file):
                os.remove(voice_file)
                print(f"🗑️ Dosya silindi: {voice_file}")
        
        # Kullanıcıyı listeden çıkar
        del authorized_files[username]
        save_authorized_users(authorized_files)
        
        flash(f'✅ "{username}" kullanıcısı başarıyla silindi!', 'success')
        print(f"✅ Kullanıcı silindi: {username}")
        
    except Exception as e:
        flash(f'Hata: {str(e)}', 'error')
        print(f"❌ Kullanıcı silme hatası: {e}")
    
    return redirect(url_for('user_management'))

@app.route("/battery")
def battery_status():
    """API endpoint for battery status"""
    return jsonify(get_battery_info())

@app.route("/current_action")
def get_current_action():
    """Şu anki eylemi döndür"""
    return jsonify({
        "current_action": current_action,
        "action_history": action_history
    })

@app.route("/start")
def start():
    global recording, is_recording
    recording = []
    is_recording = True
    update_current_action("🎤 Ses kaydı başlatıldı")

    def callback(indata, frames, time, status):
        if is_recording:
            recording.append(indata.copy())
        else:
            raise sd.CallbackStop()

    def record():
        try:
            with sd.InputStream(samplerate=fs, channels=1, callback=callback):
                sd.sleep(100000)
        except sd.CallbackStop:
            pass

    threading.Thread(target=record).start()
    return redirect(url_for('index'))

@app.route("/stop")
def stop():
    global is_recording
    is_recording = False
    update_current_action("🔄 Ses kaydı durduruluyor, işleniyor...")

    if not recording:
        print("Boş kayıt.")
        update_current_action("❌ Boş ses kaydı")
        return redirect(url_for('index'))

    audio_data = np.concatenate(recording, axis=0)
    audio_int16 = np.int16(audio_data * 32767)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        wav.write(f.name, fs, audio_int16)
        wav_path = f.name

    recognizer = sr.Recognizer()
    try:
        update_current_action("🔐 Konuşmacı doğrulanıyor...")
        
        # Konuşmacı doğrulama
        authorized = False
        matched_user = None

        for name, ref_files in authorized_files.items():
            for ref_file in ref_files:
                if not os.path.exists(ref_file):
                    print(f"❌ Dosya bulunamadı: {ref_file}")
                    continue

                score, prediction = recognizer_model.verify_files(ref_file, wav_path)
                print(f"🔍 {name} ({ref_file}) skoru: {score.item():.4f}")

                if prediction and score.item() > threshold:
                    authorized = True
                    matched_user = name
                    break

            if authorized:
                break

        if not authorized:
            update_current_action("❌ Yetkisiz kullanıcı!")
            speak_text_with_elevenlabs("Yetkisiz kullanıcı. Bu komut uygulanamaz.")
            print("❌ Erişim reddedildi.")
            return redirect(url_for('index'))

        print(f"🔐 Erişim izni verildi: {matched_user}")
        update_current_action(f"✅ {matched_user} olarak tanındı")

        # STT ve komut işleme
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="tr-TR")
            print("STT Komutu:", text)

            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            command_history.insert(0, (text, timestamp))

            update_current_action("🧠 Komut AI tarafından analiz ediliyor...")
            llm_result = call_llm_for_json(text)
            llm_output.insert(0, llm_result)

            update_current_action("🎤 Komut alındı, sesli geri bildirim...")
            speak_text_with_elevenlabs("Komut alındı: " + text)

            commands = json.loads(llm_result)
            gyro.reset_heading()
            
            # GERÇEK ZAMANLI KOMUT İŞLEME 
            for cmd in commands:
                komut = cmd.get("komut")

                if komut == "ileri_git":
                    saniye = int(cmd.get("sure", "2_saniye").split("_")[0])
                    update_current_action(f"⬆️ İleri gidiyorum ({saniye} saniye)")
                    speak_text_with_elevenlabs(f"{saniye} saniye ileri gidiliyor.")
                    robot.move_forward(saniye)
                    update_current_action("✅ İleri gitme tamamlandı")

                elif komut == "sola_don":
                    derece = int(cmd.get("derece", 90))
                    update_current_action(f"↩️ Sola dönüyorum ({derece}°)")
                    speak_text_with_elevenlabs(f"{derece} derece sola dönülüyor.")
                    robot.turn_left(derece)
                    update_current_action("✅ Sola dönme tamamlandı")

                elif komut == "saga_don":
                    derece = int(cmd.get("derece", 90))
                    update_current_action(f"↪️ Sağa dönüyorum ({derece}°)")
                    speak_text_with_elevenlabs(f"{derece} derece sağa dönülüyor.")
                    robot.turn_right(derece)
                    update_current_action("✅ Sağa dönme tamamlandı")

                elif komut == "dur":
                    update_current_action("🛑 Duruyorum")
                    speak_text_with_elevenlabs("Araç durduruluyor.")
                    robot.halt()
                    update_current_action("✅ Durdurma tamamlandı")

                elif komut == "geri_git":
                    saniye = int(cmd.get("sure", "2_saniye").split("_")[0])
                    update_current_action(f"⬇️ Geri gidiyorum ({saniye} saniye)")
                    speak_text_with_elevenlabs(f"{saniye} saniye geri gidiliyor.")
                    robot.move_back(saniye)
                    update_current_action("✅ Geri gitme tamamlandı")

                elif komut == "geri_don":
                    update_current_action("🔄 Arkaya dönüyorum (180°)")
                    speak_text_with_elevenlabs("Geri dönülüyor.")
                    robot.turn_back()
                    update_current_action("✅ Arkaya dönme tamamlandı")

                elif komut == "yapilamaz":
                    message = cmd.get("mesaj", "Bu komut gerçekleştirilemiyor.")
                    update_current_action(f"❌ {message}")
                    speak_text_with_elevenlabs(message)
           
                elif komut == "engel_gorene_kadar_ileri_git":
                    update_current_action("🚧 Engel algılanana kadar ileri gidiyorum")
                    speak_text_with_elevenlabs("Engel algılanana kadar ileri gidiliyor.")
                    robot.move_until_obstacle()
                    update_current_action("✅ Engel algılandı, durdum")

            # Tüm komutlar tamamlandı
            update_current_action("😴 Bekliyor - Yeni komut bekleniyor")
            
    except Exception as e:
        update_current_action(f"❌ Hata: {str(e)}")
        print("STT hatası:", e)
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

    return redirect(url_for('index'))

def call_llm_for_json(text):
    try:
        system_prompt = """
Sen bir doğal dil işleme uzmanısın. Kullanıcının verdiği Türkçe komutları, belirli kurallara göre sıralanmış JSON komut dizisine çeviriyorsun.

🎯 AMAÇ: Kullanıcının doğal diliyle verdiği komutları aşağıdaki yapıda sade ve sıralı JSON listesi olarak döndürmek.

📌 KURALLAR:

Her komut ayrı bir JSON nesnesi olarak liste içinde yer almalıdır.
Komut sırası, cümledeki sıra ile aynı olmalıdır.
Eğer süre belirtilmişse (örneğin "2 saniye"), sure alanında "_saniye" ekli string olarak gösterilir.
Eğer açı belirtilmişse (örneğin "90 derece"), derece olarak yazılır.
"Engel çıkana kadar" gibi koşullu ifadelerde kosul alanı "engel_algilayana_kadar" olarak belirtilir.
Komutlar yalnızca aşağıdakilerden biri olabilir:
ileri_git
sola_don
saga_don
dur
geri_don
geri_git
engel_gorene_kadar_ileri_git

Eğer kullanıcı "geri dön", "arkaya dön", "geriye dön", "tam tersine dön" gibi ifadeler kullanırsa:
[{"komut": "geri_don", "derece": 180}]
Eğer kullanıcı "engel görene kadar git" gibi ifadeler kullanırsa
{"komut": "engel_gorene_kadar_ileri_git"}

Eğer kullanıcı "geri git", "arkaya git" gibi bir ifade kullanırsa:
{"komut": "geri_git", "sure": "2_saniye"} (veya belirtilen süreye göre)

Eğer verilen komut sistemin yetenekleri dışında bir komutsa (uçmak, zıplamak, renk tanımak,dans etmek vs.):
{"komut": "yapilamaz", "mesaj": "Bunu yapamam: [komut]"}

Yalnızca JSON çıktısını ver. Açıklama yapma.
Yani çıktı her zaman köşeli parantez ([ ]) ile başlamalıdır.
Tek bir komut bile olsa, liste içinde olmalıdır.
"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"LLM JSON hatası:\n{str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
