#!/usr/bin/env python3
"""
MAHINDRA BATTERY PASSPORT - AUTOMATED TEST SUITE
Starts the backend server on a test port, executes requests to all REST APIs,
and verifies correct responses for passport metadata, telemetry updates,
electrochemical simulation outputs, and the Recycle vs. Reuse decision engine.
"""

import json
import urllib.request
import urllib.parse
import threading
import time
import sys
from http.server import HTTPServer
from server import BatteryPassportAPIHandler

TEST_PORT = 8081
BASE_URL = f"http://localhost:{TEST_PORT}"

def start_test_server():
    server_address = ("", TEST_PORT)
    httpd = HTTPServer(server_address, BatteryPassportAPIHandler)
    httpd_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    httpd_thread.start()
    print(f"[TEST] Test server started in background thread on {BASE_URL}")
    return httpd

def perform_get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200, f"Expected HTTP 200, got {response.status}"
        return json.loads(response.read().decode('utf-8'))

def perform_post(url, data):
    req = urllib.request.Request(url, method="POST")
    req.add_header('Content-Type', 'application/json')
    jsondata = json.dumps(data).encode('utf-8')
    req.add_header('Content-Length', len(jsondata))
    with urllib.request.urlopen(req, jsondata) as response:
        assert response.status == 200, f"Expected HTTP 200, got {response.status}"
        return json.loads(response.read().decode('utf-8'))

def run_tests():
    print("[TEST] Running automated checks...")
    
    # 1. Test GET /api/passport
    print("[TEST] Checking /api/passport metadata...")
    passport = perform_get(f"{BASE_URL}/api/passport")
    assert passport["passport_id"] == "M-BATT-LFP-982361A", "Incorrect Passport ID"
    assert passport["manufacturer"] == "Mahindra & Mahindra Ltd.", "Incorrect Manufacturer"
    assert "chemistry" in passport, "Chemistry field missing"
    assert "recyclability_index_pct" in passport, "Recyclability index missing"
    print(" -> [PASS] /api/passport metadata structure matches Mahindra specifications.")

    # 2. Test POST /api/telemetry (Update state)
    print("[TEST] Testing POST /api/telemetry updates...")
    test_telemetry = {
        "voltage": 315.4,
        "current": -22.5,
        "temperature": 34.8,
        "soc": 72.5,
        "soh": 74.2,
        "cycle_count": 1050,
        "internal_resistance_mohm": 1.58
    }
    post_res = perform_post(f"{BASE_URL}/api/telemetry", test_telemetry)
    assert post_res["status"] == "success", "Telemetry post did not return success status"
    print(" -> [PASS] Telemetry update accepted.")

    # 3. Test GET /api/telemetry/live (Read updated state)
    print("[TEST] Verifying live telemetry updates via GET...")
    live_telemetry = perform_get(f"{BASE_URL}/api/telemetry/live")
    assert abs(live_telemetry["voltage"] - 315.4) < 0.01, "Voltage did not update"
    assert abs(live_telemetry["current"] - (-22.5)) < 0.01, "Current did not update"
    assert abs(live_telemetry["temperature"] - 34.8) < 0.01, "Temperature did not update"
    assert abs(live_telemetry["soc"] - 72.5) < 0.01, "SoC did not update"
    assert abs(live_telemetry["soh"] - 74.2) < 0.01, "SoH did not update"
    assert live_telemetry["cycle_count"] == 1050, "Cycle count did not update"
    assert abs(live_telemetry["internal_resistance_mohm"] - 1.58) < 0.01, "Internal resistance did not update"
    print(" -> [PASS] Live telemetry cache reflects posted IoT data exactly.")

    # 4. Test GET /api/simulate
    print("[TEST] Testing PyBaMM / fallback electrochemical simulation endpoint...")
    sim_data = perform_get(f"{BASE_URL}/api/simulate?chemistry=LFP&crate=1.5&temp=20")
    assert "time" in sim_data, "Simulation results missing 'time'"
    assert "voltage" in sim_data, "Simulation results missing 'voltage'"
    assert "temperature" in sim_data, "Simulation results missing 'temperature'"
    assert len(sim_data["voltage"]) > 0, "Simulation voltage data is empty"
    # Voltage should decrease during discharge
    assert sim_data["voltage"][0] > sim_data["voltage"][-1], "Discharge simulation did not drop voltage"
    print(f" -> [PASS] Simulation returns correct values. Solver: {sim_data['sim_source']}")

    # 5. Test GET /api/decision (Recycle vs Reuse rules)
    print("[TEST] Verifying EoL Decision Engine logical rules...")
    
    # Case A: Healthy (> 80% SoH) -> Primary EV Use
    res_a = perform_get(f"{BASE_URL}/api/decision?soh=85.0&ir=1.1&cycles=150&temp_max=32.0")
    assert res_a["status_code"] == 2, "Should recommend Primary EV Use for 85% SoH"
    assert "PRIMARY AUTOMOTIVE USE" in res_a["decision"], "Decision mismatch for 85% SoH"
    
    # Case B: Reuse / Second Life (70-79% SoH) -> BESS
    res_b = perform_get(f"{BASE_URL}/api/decision?soh=75.0&ir=1.4&cycles=900&temp_max=36.0")
    assert res_b["status_code"] == 1, "Should recommend Second-Life for 75% SoH"
    assert "REUSE (SECOND LIFE)" in res_b["decision"], "Decision mismatch for 75% SoH"
    
    # Case C: Recycle (< 70% SoH) -> Raw extraction
    res_c = perform_get(f"{BASE_URL}/api/decision?soh=65.0&ir=1.8&cycles=1800&temp_max=38.0")
    assert res_c["status_code"] == 0, "Should recommend Recycle for 65% SoH"
    assert "RECYCLE" in res_c["decision"], "Decision mismatch for 65% SoH"
    
    # Case D: Safety override (High IR) -> Overrules to Recycle even if SoH is high
    res_d = perform_get(f"{BASE_URL}/api/decision?soh=76.0&ir=2.5&cycles=800&temp_max=35.0")
    assert res_d["status_code"] == 0, "Should recommend Recycle due to IR safety override"
    assert "RECYCLE" in res_d["decision"], "Safety override did not trigger Recycle"
    assert any("Internal Pack Resistance" in r for r in res_d["reasons"]), "Safety warning reason not present"
    
    print(" -> [PASS] Decision engine evaluated all categories (Primary Use, Reuse/Second Life, Recycle, Safety Override) correctly.")
    print("[TEST] All automated checks PASSED successfully.")

if __name__ == "__main__":
    # Start server in daemon thread
    server = start_test_server()
    
    # Allow socket to bind
    time.sleep(1)
    
    success = True
    try:
        run_tests()
    except AssertionError as e:
        print(f"[TEST FAILURE] Assertion failed: {e}", file=sys.stderr)
        success = False
    except Exception as e:
        print(f"[TEST ERROR] Unexpected error: {e}", file=sys.stderr)
        success = False
        
    if not success:
        sys.exit(1)
    else:
        sys.exit(0)
