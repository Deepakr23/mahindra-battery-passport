#!/usr/bin/env python3
"""
MAHINDRA BATTERY PASSPORT - IoT HARDWARE SIMULATOR
Sends live battery telemetry (voltage, current, temperature, SoC, SoH) 
via HTTP POST to the backend server to simulate Wi-Fi connected hardware.
"""

import time
import urllib.request
import json
import math
import random
import sys
import argparse

def send_telemetry(url, data):
    req = urllib.request.Request(url)
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    jsondata = json.dumps(data)
    jsondataasbytes = jsondata.encode('utf-8')
    req.add_header('Content-Length', len(jsondataasbytes))
    
    try:
        with urllib.request.urlopen(req, jsondataasbytes, timeout=2) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data
    except Exception as e:
        print(f"Error posting telemetry to server: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Simulate Mahindra Battery Pack IoT Wifi Transceiver")
    parser.add_argument("--url", default="http://localhost:8000/api/telemetry", help="Target API telemetry endpoint")
    parser.add_argument("--mode", default="secondlife", choices=["healthy", "secondlife", "recycle", "danger"],
                        help="Battery condition preset to simulate (determines EoL recommendation)")
    parser.add_argument("--rate", type=float, default=1.0, help="Updates frequency in seconds")
    
    args = parser.parse_args()
    
    # Configure battery state presets
    presets = {
        "healthy": {
            "soh": 89.4,
            "cycle_count": 140,
            "internal_resistance_mohm": 1.05,
            "voltage_base": 332.0,
            "temp_base": 24.5,
            "soc": 95.0,
            "desc": "Healthy Primary Automotive Use (SoH >= 80%)"
        },
        "secondlife": {
            "soh": 76.8,
            "cycle_count": 940,
            "internal_resistance_mohm": 1.48,
            "voltage_base": 321.0,
            "temp_base": 28.0,
            "soc": 82.0,
            "desc": "Second-Life Repurposing Range (SoH 70% - 79%)"
        },
        "recycle": {
            "soh": 62.1,
            "cycle_count": 1820,
            "internal_resistance_mohm": 1.95,
            "voltage_base": 308.0,
            "temp_base": 31.5,
            "soc": 48.0,
            "desc": "Recycling Recommended (SoH < 70%)"
        },
        "danger": {
            "soh": 75.2,
            "cycle_count": 890,
            "internal_resistance_mohm": 4.15, # Extremely high resistance (thermal risk)
            "voltage_base": 312.0,
            "temp_base": 42.0,
            "soc": 60.0,
            "desc": "Thermal Hazard Recycle Overrule (High IR > 2.0 mΩ)"
        }
    }
    
    preset = presets[args.mode]
    print("=" * 60)
    print(f"MAHINDRA BATTERY PASSPORT - IoT WI-FI SIMULATOR")
    print(f"Target URL : {args.url}")
    print(f"Active Mode: {args.mode.upper()} - {preset['desc']}")
    print("=" * 60)
    
    soc = preset["soc"]
    temp = preset["temp_base"]
    
    step = 0
    try:
        while True:
            # Simulate active battery discharge
            step += 1
            # Current draws fluctuates around 15A
            current = -15.0 + math.sin(step / 10.0) * 8.0 + random.uniform(-1, 1)
            
            # SoC decreases slowly
            soc -= 0.08
            if soc < 5.0:
                soc = 95.0 # Recharge loop
                
            # Voltage calculation based on SoC and IR drop
            ir_ohms = preset["internal_resistance_mohm"] / 1000.0
            ocv = preset["voltage_base"] + (soc - 50.0) * 0.4 # linear voltage relationship helper
            voltage = ocv + (current * ir_ohms) + random.uniform(-0.3, 0.3)
            
            # Thermal heat dissipation: I^2 * R heating up
            q_gen = math.pow(current, 2) * ir_ohms
            cooling = 0.8 * (temp - preset["temp_base"])
            temp += (q_gen - cooling) * 0.05 + random.uniform(-0.1, 0.1)
            
            # Build payload
            payload = {
                "voltage": round(voltage, 1),
                "current": round(current, 1),
                "temperature": round(temp, 1),
                "soc": round(soc, 1),
                "soh": preset["soh"],
                "cycle_count": preset["cycle_count"],
                "internal_resistance_mohm": preset["internal_resistance_mohm"]
            }
            
            res = send_telemetry(args.url, payload)
            if res:
                print(f"[TX] Packet #{step:03d} | SoC: {payload['soc']}% | V: {payload['voltage']}V | I: {payload['current']}A | T: {payload['temperature']}°C | Result: {res['status']}")
            else:
                print(f"[TX] Packet #{step:03d} | Server connection failed.")
                
            time.sleep(args.rate)
            
    except KeyboardInterrupt:
        print("\nSimulator stopped.")

if __name__ == "__main__":
    main()
