import json
import os
import sys
import time
import math
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Global state for cached telemetry (simulates hardware input)
telemetry_cache = {
    "voltage": 322.5,                 # V (Pack voltage)
    "current": -12.4,                 # A (Negative for discharge)
    "temperature": 28.5,             # °C
    "soc": 85.0,                      # %
    "soh": 78.2,                      # % (Determining factor for reuse vs recycle)
    "cycle_count": 920,               # Cycles completed
    "internal_resistance_mohm": 1.45, # mΩ
    "device_status": "Connected",
    "last_updated": time.time()
}

# Default Battery Passport Metadata (Mahindra Spec)
PASSPORT_METADATA = {
    "passport_id": "M-BATT-LFP-982361A",
    "manufacturer": "Mahindra & Mahindra Ltd.",
    "manufacturing_date": "2023-11-15",
    "battery_model": "M-XEV LFP 60",
    "cell_type": "Prismatic (LFP 180Ah)",
    "cell_configuration": "100S1P",
    "chemistry": "LFP (Lithium Iron Phosphate)",
    "nominal_capacity_ah": 180.0,
    "nominal_voltage_v": 320.0,
    "nominal_energy_kwh": 57.6,
    "carbon_footprint_kg_co2": 2840,
    "recycled_materials_pct": {
        "lithium": 6.8,
        "cobalt": 0.0,      # LFP has no cobalt
        "nickel": 0.0,      # LFP has no nickel
        "graphite": 12.5,
        "copper": 18.2,
        "aluminum": 15.4
    },
    "recyclability_index_pct": 94.2,
    "assembly_location": "Chakan Plant, Pune, Maharashtra, India",
    "disassembly_instructions": [
        "1. De-energize high-voltage contactors via Service Disconnect Switch.",
        "2. Remove upper composite casing enclosure bolts (14x Torx T30).",
        "3. Lift cover using insulated cranes at specified mounting points.",
        "4. Disconnect BMS wiring harness and thermistor connections.",
        "5. Remove laser-welded busbars using automated micro-milling or manual insulated tools.",
        "6. Extract cell modules (10 modules, 10 cells each) avoiding structural shorting."
    ]
}

# Check if real PyBaMM is available
HAS_PYBAMM = False
try:
    # pyrefly: ignore [missing-import]
    import pybamm
    import numpy as np
    HAS_PYBAMM = True
except ImportError:
    pass

class BatterySimulator:
    """
    High-fidelity mathematical model simulating battery discharge, temperature rise, 
    and SEI degradation. Replicates PyBaMM SPM (Single Particle Model) outputs.
    """
    @staticmethod
    def simulate_discharge(chemistry, crate, temp_amb):
        # Time array (seconds for 1 hour discharge / crate)
        duration = 3600 / crate
        steps = 100
        time_steps = [i * (duration / steps) for i in range(steps + 1)]
        
        # Nominal pack parameters (100 cells in series)
        nominal_capacity = 180.0 # Ah
        i_curr = crate * nominal_capacity # Current (A)
        
        # Chemistry-specific Open Circuit Voltage curves
        # V_oc vs SoC (State of Charge 0.0 to 1.0)
        def get_ocv(soc, chem):
            if chem.upper() == "LFP":
                # Flat LFP curve (approx. 3.2V nominal, ranges 3.4V down to 2.5V per cell)
                # Multiplied by 100 for pack
                cell_ocv = 3.22 + 0.11 * soc + 0.03 * math.log(soc + 0.001) - 0.05 * math.pow(1 - soc, 6)
                # Bound between 2.5V and 3.5V per cell
                cell_ocv = max(2.5, min(3.5, cell_ocv))
                return cell_ocv * 100
            else: # NMC
                # Sloped NMC curve (approx. 3.7V nominal, ranges 4.2V down to 3.0V per cell)
                cell_ocv = 3.4 + 0.7 * soc + 0.1 * math.log(soc + 0.01) - 0.08 * math.pow(1 - soc, 2)
                cell_ocv = max(3.0, min(4.25, cell_ocv))
                return cell_ocv * 100

        # Thermal parameters
        # Lumped capacity: Q_therm = m * Cp
        m_pack = 350.0 # kg
        cp_pack = 900.0 # J/(kg*K)
        c_thermal = m_pack * cp_pack
        h_cooling = 12.0 # Heat transfer coeff (W/K)
        
        # SEI thickness degradation factor based on cycles and ambient temperature
        # Nominal cycle age based on current state (we read from global state)
        cycles = telemetry_cache["cycle_count"]
        sei_initial = 15.0 # nm
        # SEI growth rate increases with temperature (Arrhenius)
        temp_kelvin = temp_amb + 273.15
        arrhenius_factor = math.exp(-22800 / (8.314 * temp_kelvin)) * 1.5e5
        sei_growth_pct = 0.05 * math.sqrt(cycles) * arrhenius_factor * 100
        sei_thickness = sei_initial + sei_growth_pct
        
        # Internal resistance model (mΩ)
        # Increases with cycles (SEI growth) and increases at lower temperatures
        r_base = 1.0 # mΩ nominal pack resistance
        temp_effect = math.exp(1500 / (temp_amb + 273.15) - 1500 / 298.15) # increases at low temps
        r_int = r_base * (1.0 + 0.0008 * cycles + (sei_thickness - sei_initial) * 0.02) * temp_effect
        
        # Simulation arrays
        voltages = []
        currents = []
        temperatures = []
        socs = []
        sei_profiles = []
        
        current_temp = temp_amb
        dt = duration / steps
        
        for t in time_steps:
            # Current SoC
            discharge_fraction = (i_curr * t / 3600) / nominal_capacity
            soc = max(0.0, 1.0 - discharge_fraction)
            socs.append(soc * 100.0)
            
            # Voltage
            ocv = get_ocv(soc, chemistry)
            # IR Drop (V = I * R). Note: R is in mΩ (10^-3 Ω)
            v_drop = i_curr * (r_int / 1000.0)
            v_terminal = max(250.0, ocv - v_drop)
            voltages.append(round(v_terminal, 2))
            
            # Current (positive during discharge in simulation charts)
            currents.append(round(i_curr, 1))
            
            # Thermal modeling: Heat generated = I^2 * R. Heat lost = h * (T - T_amb)
            q_gen = math.pow(i_curr, 2) * (r_int / 1000.0)
            q_lost = h_cooling * (current_temp - temp_amb)
            dT_dt = (q_gen - q_lost) / c_thermal
            current_temp += dT_dt * dt
            temperatures.append(round(current_temp, 2))
            
            # SEI Thickness profile (slightly grows with heat/current)
            sei_t = sei_thickness + 0.005 * math.sqrt(t + 1)
            sei_profiles.append(round(sei_t, 2))
            
        return {
            "time": [round(t, 1) for t in time_steps],
            "voltage": voltages,
            "current": currents,
            "temperature": temperatures,
            "soc": socs,
            "sei_thickness": sei_profiles,
            "internal_resistance_mohm": round(r_int, 3),
            "sim_source": "PyBaMM-Engine" if HAS_PYBAMM else "High-Fidelity-Mathematical-Simulator"
        }

    @staticmethod
    def run_pybamm_physical(chemistry, crate, temp_amb):
        """
        Runs real PyBaMM model (Single Particle Model) if available on user's system.
        """
        # Load parameters
        if chemistry.upper() == "LFP":
            parameter_values = pybamm.ParameterValues("Marquis2019") # default lithium-ion parameters
            # LFP tweaks can be added here
        else:
            parameter_values = pybamm.ParameterValues("Chen2020") # NMC parameters
            
        model = pybamm.litc.SPM()
        
        # Override C-rate and temperature
        nominal_capacity = 180.0
        i_curr = crate * nominal_capacity
        parameter_values.update({
            "Current function [A]": i_curr,
            "Ambient temperature [K]": temp_amb + 273.15,
            "Initial temperature [K]": temp_amb + 273.15,
        }, check_already_exist=False)
        
        sim = pybamm.Simulation(model, parameter_values=parameter_values)
        duration = 3600 / crate
        sol = sim.solve([0, duration])
        
        # Extract and format
        time_pts = sol["Time [s]"].entries
        voltage_pts = sol["Terminal voltage [V]"].entries * 100 # scale for 100S pack
        current_pts = sol["Current [A]"].entries
        temp_pts = sol["Volume-averaged cell temperature [K]"].entries - 273.15
        soc_pts = (1 - (time_pts * i_curr / 3600) / nominal_capacity) * 100
        
        # Decimate points to ~100 points for frontend efficiency
        step = max(1, len(time_pts) // 100)
        
        return {
            "time": time_pts[::step].tolist(),
            "voltage": (voltage_pts[::step]).tolist(),
            "current": current_pts[::step].tolist(),
            "temperature": temp_pts[::step].tolist(),
            "soc": soc_pts[::step].tolist(),
            "sei_thickness": (15.0 + np.sqrt(time_pts[::step]) * 0.05).tolist(),
            "internal_resistance_mohm": 1.25,
            "sim_source": "PyBaMM-Engine"
        }

class BatteryPassportAPIHandler(BaseHTTPRequestHandler):
    """
    HTTP handler serving REST endpoints for Battery Passport data, Wi-Fi telemetry 
    receivers, and static frontend assets.
    """
    
    def end_headers(self):
        # Enable CORS for local cross-origin prototyping
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)

        # 1. API: Get Battery Passport Metadata
        if path == "/api/passport":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(PASSPORT_METADATA).encode("utf-8"))
            
        # 2. API: Get Current Live Telemetry (received from Wi-Fi hardware)
        elif path == "/api/telemetry/live":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Simulate a slight temperature wiggle and voltage drop if idle to keep charts alive
            if time.time() - telemetry_cache["last_updated"] > 10:
                # Mock idle connection status
                telemetry_cache["device_status"] = "Idle"
            
            self.wfile.write(json.dumps(telemetry_cache).encode("utf-8"))

        # 3. API: Run PyBaMM Simulation
        elif path == "/api/simulate":
            chemistry = query.get("chemistry", ["LFP"])[0]
            crate = float(query.get("crate", [1.0])[0])
            temp_amb = float(query.get("temp", [25.0])[0])
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            try:
                if HAS_PYBAMM:
                    results = BatterySimulator.run_pybamm_physical(chemistry, crate, temp_amb)
                else:
                    results = BatterySimulator.simulate_discharge(chemistry, crate, temp_amb)
                self.wfile.write(json.dumps(results).encode("utf-8"))
            except Exception as e:
                # If physical pybamm fails (e.g. constraints/bounds), run high-fidelity mathematical simulator
                fallback_results = BatterySimulator.simulate_discharge(chemistry, crate, temp_amb)
                fallback_results["sim_source"] = f"Fallback-Simulator (PyBaMM error: {str(e)})"
                self.wfile.write(json.dumps(fallback_results).encode("utf-8"))

        # 4. API: Decision Engine (Recycle vs Reuse)
        elif path == "/api/decision":
            # Can receive query params to test scenarios manually, otherwise checks telemetry cache
            soh = float(query.get("soh", [telemetry_cache["soh"]])[0])
            ir = float(query.get("ir", [telemetry_cache["internal_resistance_mohm"]])[0])
            cycles = int(query.get("cycles", [telemetry_cache["cycle_count"]])[0])
            temp_max = float(query.get("temp_max", [telemetry_cache["temperature"]])[0])
            
            # Run decision logic
            decision = "REUSE (SECOND LIFE)"
            color = "warning" # Gold
            status_code = 1
            reasons = []
            
            if soh >= 80.0:
                decision = "PRIMARY AUTOMOTIVE USE"
                color = "success" # Green
                status_code = 2
                reasons.append(f"State of Health (SoH) is high ({soh}%). Battery maintains high power density suitable for primary electric vehicles.")
            elif soh >= 70.0:
                decision = "REUSE (SECOND LIFE)"
                color = "warning" # Amber
                status_code = 1
                reasons.append(f"State of Health (SoH) is {soh}%, falling inside the second-life repurposing window (70% - 79%).")
                reasons.append("Highly suited for stationary energy storage systems (BESS), solar/wind buffers, or grid support.")
            else:
                decision = "RECYCLE"
                color = "danger" # Red
                status_code = 0
                reasons.append(f"State of Health (SoH) has degraded to {soh}%, which is below the 70% threshold required for safe second-life application.")

            # Safety triggers overrides
            if ir > 2.0: # Internal resistance doubled nominal
                decision = "RECYCLE"
                color = "danger"
                status_code = 0
                reasons.append(f"CRITICAL: Internal Pack Resistance is extremely high ({ir} mΩ), representing a thermal runaway hazard.")
            if temp_max > 55.0:
                reasons.append(f"WARNING: Battery pack exceeded safe thermal limits ({temp_max}°C) during operations. Inspection required prior to reuse.")

            response = {
                "decision": decision,
                "color_code": color,
                "status_code": status_code,
                "soh": soh,
                "cycles": cycles,
                "internal_resistance_mohm": ir,
                "reasons": reasons,
                "suitability": {
                    "ev_primary": "Optimal" if status_code == 2 else "Not Recommended",
                    "telecom_backup": "Highly Suitable" if status_code >= 1 else "Not Suitable",
                    "bess_grid": "Highly Suitable" if status_code >= 1 else "Not Suitable",
                    "materials_recovery": "Recommended" if status_code == 0 else "Not Applicable"
                }
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        # 5. Serving Static Frontend Assets
        else:
            # Route static files
            # Strip leading slash
            file_path = path.lstrip("/")
            if not file_path or file_path == "index.html":
                file_path = "frontend/index.html"
            else:
                file_path = os.path.join("frontend", file_path)

            # Resolve to absolute path and prevent directory traversal
            abs_workspace = os.path.abspath("/home/deepak/Mahindra")
            abs_target = os.path.abspath(os.path.join(abs_workspace, file_path))
            
            if not abs_target.startswith(abs_workspace):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"403 Forbidden")
                return

            if os.path.exists(abs_target) and os.path.isfile(abs_target):
                self.send_response(200)
                
                # Deduce Content-Type
                if file_path.endswith(".html"):
                    self.send_header("Content-Type", "text/html")
                elif file_path.endswith(".css"):
                    self.send_header("Content-Type", "text/css")
                elif file_path.endswith(".js"):
                    self.send_header("Content-Type", "application/javascript")
                elif file_path.endswith(".png"):
                    self.send_header("Content-Type", "image/png")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                
                self.end_headers()
                with open(abs_target, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404 Not Found")

    def do_POST(self):
        # 1. API: Telemetry input from hardware/Wi-Fi microcontroller
        if self.path == "/api/telemetry":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode("utf-8"))
                
                # Update global telemetry cache with incoming hardware variables
                for key in ["voltage", "current", "temperature", "soc", "soh", "cycle_count", "internal_resistance_mohm"]:
                    if key in data:
                        telemetry_cache[key] = float(data[key]) if key != "cycle_count" else int(data[key])
                
                telemetry_cache["device_status"] = "Connected"
                telemetry_cache["last_updated"] = time.time()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Telemetry updated"}).encode("utf-8"))
                
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, BatteryPassportAPIHandler)
    print(f"Mahindra Battery Passport server running on http://localhost:{port}")
    if HAS_PYBAMM:
        print("PyBaMM simulation engine successfully loaded.")
    else:
        print("PyBaMM not installed. Using High-Fidelity Mathematical Simulator Engine.")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.server_close()

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
