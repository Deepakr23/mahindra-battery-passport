// CLIENT-SIDE APPLICATION DRIVER - MAHINDRA BATTERY PASSPORT

const API_BASE = ""; // Relative paths since server routes APIs directly

// State variables
let activeChart = "voltage"; // Default chart tab
let simulationData = null; // Store active simulation run
let chartInstance = null; // Chart.js object reference
let lastTelemetryTime = 0; // Check heartbeat

// DOM Elements
const elements = {
    // Passport Meta
    passportId: document.getElementById("meta-passport-id"),
    manufacturer: document.getElementById("meta-manufacturer"),
    manufacturedDate: document.getElementById("meta-date"),
    batteryModel: document.getElementById("meta-model"),
    cellChemistry: document.getElementById("meta-chemistry"),
    nominalSpecs: document.getElementById("meta-specs"),
    assemblyPlant: document.getElementById("meta-plant"),
    co2Footprint: document.getElementById("meta-co2"),
    recyclabilityIndex: document.getElementById("meta-recyclability"),
    disassemblyList: document.getElementById("meta-disassembly-list"),
    
    // Telemetry Values
    telVoltage: document.getElementById("tel-voltage"),
    telCurrent: document.getElementById("tel-current"),
    telCurrentStatus: document.getElementById("tel-current-status"),
    telTemperature: document.getElementById("tel-temperature"),
    telSoC: document.getElementById("tel-soc"),
    socRadialRing: document.getElementById("soc-radial-ring"),
    telSoH: document.getElementById("tel-soh"),
    sohBadge: document.getElementById("soh-badge"),
    sohBar: document.getElementById("soh-bar"),
    telCycles: document.getElementById("tel-cycles"),
    telInternalRes: document.getElementById("tel-ir"),
    
    // Connection Info
    connectionStatus: document.getElementById("connection-status"),
    connectionStatusContainer: document.getElementById("connection-status-container"),
    wifiIndicator: document.getElementById("wifi-indicator"),
    connectionLatency: document.getElementById("connection-latency"),
    
    // Simulation Config
    simChemistry: document.getElementById("sim-chemistry"),
    simCrate: document.getElementById("sim-crate"),
    simCrateVal: document.getElementById("sim-crate-val"),
    simTemp: document.getElementById("sim-temp"),
    simTempVal: document.getElementById("sim-temp-val"),
    runSimBtn: document.getElementById("run-simulation-btn"),
    solverBadge: document.getElementById("solver-badge"),
    chartLegend: document.getElementById("chart-metrics-summary"),
    chartTabs: document.querySelectorAll(".chart-tab"),
    
    // Decision Engine UI
    decisionPanel: document.getElementById("decision-panel"),
    decisionOutcomeCard: document.getElementById("decision-outcome-card"),
    decisionText: document.getElementById("decision-text"),
    decisionStatusPill: document.getElementById("decision-status-pill"),
    decisionReasonsList: document.getElementById("decision-reasons-list"),
    
    // Suitability Matrix
    suitEV: document.getElementById("suit-ev"),
    suitTelecom: document.getElementById("suit-telecom"),
    suitBESS: document.getElementById("suit-bess"),
    suitMaterials: document.getElementById("suit-materials")
};

// INITIALIZATION
window.addEventListener("DOMContentLoaded", () => {
    // 1. Load static passport metadata
    fetchPassportMetadata();
    
    // 2. Set up slider listeners for live value feedback
    elements.simCrate.addEventListener("input", (e) => {
        elements.simCrateVal.textContent = parseFloat(e.target.value).toFixed(1) + " C";
    });
    
    elements.simTemp.addEventListener("input", (e) => {
        elements.simTempVal.textContent = parseInt(e.target.value) + " °C";
    });
    
    // 3. Set up simulation triggers
    elements.runSimBtn.addEventListener("click", triggerSimulation);
    
    // 4. Set up simulation chart tab toggles
    elements.chartTabs.forEach(tab => {
        tab.addEventListener("click", (e) => {
            elements.chartTabs.forEach(t => t.classList.remove("active"));
            e.target.classList.add("active");
            activeChart = e.target.dataset.chart;
            renderChart();
        });
    });
    
    // 5. Run simulation initially to populate charts
    triggerSimulation();
    
    // 6. Start telemetry fetch interval (every 1 second)
    fetchTelemetry();
    setInterval(fetchTelemetry, 1000);
});

// 1. METADATA loader
function fetchPassportMetadata() {
    fetch(`${API_BASE}/api/passport`)
        .then(res => res.json())
        .then(data => {
            elements.passportId.textContent = data.passport_id;
            elements.manufacturer.textContent = data.manufacturer;
            elements.manufacturedDate.textContent = data.manufacturing_date;
            elements.batteryModel.textContent = data.battery_model;
            elements.cellChemistry.textContent = data.chemistry;
            elements.nominalSpecs.textContent = `${data.nominal_voltage_v}V / ${data.nominal_capacity_ah}Ah (${data.nominal_energy_kwh} kWh)`;
            elements.assemblyPlant.textContent = data.assembly_location;
            elements.co2Footprint.textContent = data.carbon_footprint_kg_co2;
            elements.recyclabilityIndex.textContent = data.recyclability_index_pct;
            
            // Render materials progress bars
            const recycled = data.recycled_materials_pct;
            const barList = document.querySelector(".material-bar-list");
            barList.innerHTML = "";
            for (const [mat, pct] of Object.entries(recycled)) {
                if (pct > 0) {
                    const cleanName = mat.charAt(0).toUpperCase() + mat.slice(1);
                    barList.innerHTML += `
                        <div class="material-bar-item">
                            <span class="mat-name">${cleanName}</span>
                            <div class="progress-track"><div class="progress-fill" style="width: ${pct}%"></div></div>
                            <span class="mat-pct">${pct}%</span>
                        </div>
                    `;
                }
            }
            
            // Load disassembly list
            elements.disassemblyList.innerHTML = "";
            data.disassembly_instructions.forEach(step => {
                const li = document.createElement("li");
                li.textContent = step;
                elements.disassemblyList.appendChild(li);
            });
        })
        .catch(err => console.error("Error loading passport metadata:", err));
}

// 2. LIVE TELEMETRY polling
function fetchTelemetry() {
    const startTime = Date.now();
    fetch(`${API_BASE}/api/telemetry/live`)
        .then(res => res.json())
        .then(data => {
            const latency = Date.now() - startTime;
            lastTelemetryTime = Date.now();
            
            // Set Connection status
            elements.connectionStatus.textContent = data.device_status;
            elements.connectionStatus.className = `status-val ${data.device_status.toLowerCase()}`;
            elements.wifiIndicator.className = `wifi-pulse ${data.device_status === "Connected" ? "" : "idle"}`;
            elements.connectionLatency.innerHTML = `Signal: -65dBm &bull; Latency ${latency}ms &bull; Pack: IoT-ESP32`;
            
            // Populate numerical text
            elements.telVoltage.textContent = data.voltage.toFixed(1);
            elements.telCurrent.textContent = data.current.toFixed(1);
            elements.telTemperature.textContent = data.temperature.toFixed(1);
            
            // Update current description
            if (data.current < -0.5) {
                elements.telCurrentStatus.textContent = "Discharging";
                elements.telCurrentStatus.style.color = "var(--mahindra-red)";
            } else if (data.current > 0.5) {
                elements.telCurrentStatus.textContent = "Charging";
                elements.telCurrentStatus.style.color = "var(--neon-green)";
            } else {
                elements.telCurrentStatus.textContent = "Standby (Idle)";
                elements.telCurrentStatus.style.color = "var(--color-text-secondary)";
            }
            
            // Radial SoC gauge update
            const soc = Math.round(data.soc);
            elements.telSoC.textContent = soc;
            
            // SVG circle circumference is 2 * PI * r = 2 * 3.14159 * 40 = 251.3
            const circumference = 251.2;
            const offset = circumference - (soc / 100) * circumference;
            elements.socRadialRing.style.strokeDashoffset = offset;
            
            // Update SoH text and indicators
            elements.telSoH.textContent = data.soh.toFixed(1) + "%";
            elements.sohBar.style.width = data.soh.toFixed(1) + "%";
            
            // Evaluate status badges
            if (data.soh >= 80.0) {
                elements.sohBadge.textContent = "Automotive Grade (Primary)";
                elements.sohBadge.className = "status-badge success";
                elements.sohBar.className = "bar-fill success";
            } else if (data.soh >= 70.0) {
                elements.sohBadge.textContent = "Second-Life Repurposed";
                elements.sohBadge.className = "status-badge warning";
                elements.sohBar.className = "bar-fill warning";
            } else {
                elements.sohBadge.textContent = "Degraded (Recycle Priority)";
                elements.sohBadge.className = "status-badge danger";
                elements.sohBar.className = "bar-fill danger";
            }
            
            elements.telCycles.textContent = data.cycle_count;
            elements.telInternalRes.textContent = data.internal_resistance_mohm.toFixed(2) + " mΩ";
            
            // Run EoL decision engine logic based on live telemetries
            evaluateDecision(data.soh, data.internal_resistance_mohm, data.cycle_count, data.temperature);
        })
        .catch(err => {
            console.error("Telemetry server communication error:", err);
            elements.connectionStatus.textContent = "Offline";
            elements.connectionStatus.className = "status-val idle";
            elements.wifiIndicator.className = "wifi-pulse idle";
            elements.connectionLatency.textContent = "Connection timed out. Retrying link...";
        });
}

// 3. PyBaMM SIMULATION handler
function triggerSimulation() {
    const chem = elements.simChemistry.value;
    const crate = elements.simCrate.value;
    const temp = elements.simTemp.value;
    
    // UI Loading state
    elements.runSimBtn.disabled = true;
    elements.runSimBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Solving PyBaMM...`;
    elements.solverBadge.textContent = "Computing Electrochemical Equations...";
    
    fetch(`${API_BASE}/api/simulate?chemistry=${chem}&crate=${crate}&temp=${temp}`)
        .then(res => res.json())
        .then(data => {
            simulationData = data;
            
            // Reset button and load source
            elements.runSimBtn.disabled = false;
            elements.runSimBtn.innerHTML = `<i class="fa-solid fa-play"></i> Run PyBaMM Simulation`;
            elements.solverBadge.textContent = data.sim_source.replace(/-/g, " ");
            
            // Render plot
            renderChart();
        })
        .catch(err => {
            console.error("Simulation run failed:", err);
            elements.runSimBtn.disabled = false;
            elements.runSimBtn.innerHTML = `<i class="fa-solid fa-play"></i> Run PyBaMM Simulation`;
            elements.solverBadge.textContent = "Simulation Solver Failure";
            elements.chartLegend.textContent = "Error occurred: Could not connect to PyBaMM backend solver.";
        });
}

// 4. CHART RENDERING Engine
function renderChart() {
    if (!simulationData) return;
    
    const ctx = document.getElementById("simulationChart").getContext("2d");
    
    // Destroy previous Chart instance to redraw cleanly
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    let labelX = "Time (seconds)";
    let labelY = "";
    let dataY = [];
    let dataX = [];
    let datasetLabel = "";
    let colorLine = "#e31837";
    let colorFillBg = "rgba(227, 24, 55, 0.08)";
    
    const chemType = elements.simChemistry.value;
    
    if (activeChart === "voltage") {
        labelX = "State of Charge (%)";
        labelY = "Pack Voltage (V)";
        datasetLabel = `${chemType} Discharge Curve`;
        // Reverse SoC array so curve goes 100% -> 0% matching standard battery representations
        dataX = simulationData.soc.map(v => Math.round(v));
        dataY = simulationData.voltage;
        colorLine = "#00f2fe";
        colorFillBg = "rgba(0, 242, 254, 0.08)";
        
        elements.chartLegend.innerHTML = `
            <strong>Simulation Metrics Summary:</strong> 
            Nominal Resistance: <strong>${simulationData.internal_resistance_mohm} mΩ</strong> &bull; 
            Starting SoC: <strong>${Math.round(simulationData.soc[0])}%</strong> &bull; 
            Cutoff Voltage: <strong>${simulationData.voltage[simulationData.voltage.length-1]} V</strong>. 
            Solves the physical terminal voltage using single-particle lithium diffusion dynamics.
        `;
    } else if (activeChart === "thermal") {
        labelX = "Simulation Time (s)";
        labelY = "Cell Temperature (°C)";
        datasetLabel = `Lumped Thermal Runaway Rise`;
        dataX = simulationData.time;
        dataY = simulationData.temperature;
        colorLine = "#ffb830";
        colorFillBg = "rgba(255, 184, 48, 0.08)";
        
        const tempMax = Math.max(...simulationData.temperature).toFixed(1);
        const tempDelta = (tempMax - simulationData.temperature[0]).toFixed(1);
        
        elements.chartLegend.innerHTML = `
            <strong>Thermal Results:</strong> 
            Initial Temp: <strong>${simulationData.temperature[0]}°C</strong> &bull; 
            Peak Temp: <strong style="color: ${tempMax > 50 ? 'var(--mahindra-red)' : 'var(--neon-amber)'}">${tempMax}°C</strong> &bull; 
            Temperature Rise ($\u0394T$): <strong>+${tempDelta}°C</strong>. 
            Calculates internal heat generation ($I^2R$) against external convection cooling boundary conditions.
        `;
    } else if (activeChart === "degradation") {
        labelX = "Simulation Time (s)";
        labelY = "SEI Layer Thickness (nm)";
        datasetLabel = `Solid Electrolyte Interphase (SEI) Growth`;
        dataX = simulationData.time;
        dataY = simulationData.sei_thickness;
        colorLine = "#e31837";
        colorFillBg = "rgba(227, 24, 55, 0.08)";
        
        const seiGrowth = (simulationData.sei_thickness[simulationData.sei_thickness.length - 1] - simulationData.sei_thickness[0]).toFixed(3);
        
        elements.chartLegend.innerHTML = `
            <strong>SEI Degradation Analysis:</strong> 
            Starting SEI: <strong>${simulationData.sei_thickness[0]} nm</strong> &bull; 
            Current Cycle Growth: <strong>+${seiGrowth} nm</strong>. 
            Predicts the electrochemical degradation layer forming on the graphite anode, reducing capacity.
        `;
    }
    
    // Create new Chart.js configuration
    chartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: dataX,
            datasets: [{
                label: datasetLabel,
                data: dataY,
                borderColor: colorLine,
                backgroundColor: colorFillBg,
                borderWidth: 2.5,
                pointRadius: 0,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: "#8b949e",
                        font: { family: "Outfit", size: 12 }
                    }
                },
                tooltip: {
                    mode: "index",
                    intersect: false
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: labelX,
                        color: "#8b949e",
                        font: { family: "Inter", size: 11 }
                    },
                    grid: { color: "rgba(255, 255, 255, 0.03)" },
                    ticks: { color: "#8b949e" }
                },
                y: {
                    title: {
                        display: true,
                        text: labelY,
                        color: "#8b949e",
                        font: { family: "Inter", size: 11 }
                    },
                    grid: { color: "rgba(255, 255, 255, 0.03)" },
                    ticks: { color: "#8b949e" }
                }
            }
        }
    });
}

// 5. PASSPORT END-OF-LIFE DECISION ENGINE
function evaluateDecision(soh, ir, cycles, temp) {
    // Call the backend decision API to get the standardized decision
    fetch(`${API_BASE}/api/decision?soh=${soh}&ir=${ir}&cycles=${cycles}&temp_max=${temp}`)
        .then(res => res.json())
        .then(data => {
            // Update decision outcome card visual classes
            elements.decisionOutcomeCard.className = "decision-output-card"; // reset
            elements.decisionOutcomeCard.classList.add(`${data.color_code}-state`);
            
            elements.decisionText.textContent = data.decision;
            elements.decisionStatusPill.textContent = `STATUS: ${data.decision.split(" ")[0]}`;
            
            // Build logs list
            elements.decisionReasonsList.innerHTML = "";
            data.reasons.forEach(reason => {
                const li = document.createElement("li");
                li.textContent = reason;
                elements.decisionReasonsList.appendChild(li);
            });
            
            // Update Suitability Matrix
            updateMatrixBadge(elements.suitEV, data.suitability.ev_primary);
            updateMatrixBadge(elements.suitTelecom, data.suitability.telecom_backup);
            updateMatrixBadge(elements.suitBESS, data.suitability.bess_grid);
            updateMatrixBadge(elements.suitMaterials, data.suitability.materials_recovery);
        })
        .catch(err => console.error("Error running decision engine:", err));
}

function updateMatrixBadge(element, statusText) {
    element.textContent = statusText;
    element.className = "suit-status"; // reset
    
    if (statusText === "Optimal") {
        element.classList.add("optimal");
    } else if (statusText === "Highly Suitable" || statusText === "Recommended") {
        element.classList.add("suitable");
    } else if (statusText === "Not Recommended") {
        element.classList.add("not-rec");
    } else {
        element.classList.add("not-suitable");
    }
}
