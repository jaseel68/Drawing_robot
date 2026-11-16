/**
 * DRAWING ROBOT - MAIN FRONTEND APPLICATION SCRIPT
 * =================================================
 * Beginner-friendly, modular Vanilla JavaScript for:
 * 1. Image upload & drag-and-drop handling
 * 2. OpenCV parameter gathering & API requests
 * 3. HTML5 Canvas 2D Vector Path Rendering (Paper, Margins, Axes, Robot Path, Virtual Robot animation)
 * 4. Path Statistics display & JSON/CSV exports
 * 5. Real-time ESP32 / Virtual Simulator telemetry status polling & controls
 */

// Global State Store
const state = {
    uploadedFilename: null,
    imageWidth: 0,
    imageHeight: 0,
    contours: [],
    pathData: null,
    simulationMode: false,
    esp32Ip: '192.168.1.100',
    isEmergencyStopped: false,
    zoomLevel: 1.0,
    panX: 0,
    panY: 0,
    isDraggingCanvas: false,
    dragStartX: 0,
    dragStartY: 0,
    robotStatus: {
        state: 'IDLE',
        x: 0.0,
        y: 0.0,
        penState: 'UP',
        progress: 0.0,
        cmdIdx: 0,
        totalCmds: 0
    }
};

// ==========================================================================
// 1. INITIALIZATION & EVENT LISTENERS
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    initUpload();
    initSliders();
    initTabSwitching();
    initCanvasPanZoom();
    initButtons();
    
    // Start live telemetry status polling loop (every 1 second)
    startStatusPolling();
});

// ==========================================================================
// 2. IMAGE UPLOAD & DROPZONE LOGIC
// ==========================================================================
function initUpload() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('imageInput');
    const selectBtn = document.getElementById('selectFileBtn');

    selectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    dropZone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    // Drag and Drop Events
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        });
    });

    dropZone.addEventListener('drop', (e) => {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });
}

function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('image', file);

    showWarning("Processing uploaded image...");

    fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            state.uploadedFilename = data.filename;
            state.imageWidth = data.width;
            state.imageHeight = data.height;
            state.pathUploaded = false;

            // Update Metadata UI
            document.getElementById('metaFilename').textContent = data.filename;
            document.getElementById('metaDimensions').textContent = `${data.width} × ${data.height} px`;
            document.getElementById('metaSize').textContent = `${data.file_size_kb} KB`;
            document.getElementById('metadataCard').classList.remove('hidden');

            // Populate Stage 1 Original Image
            document.getElementById('imgStageOriginal').src = data.preview_url;

            // Enable Process Button
            document.getElementById('processBtn').disabled = false;
            
            showWarning(null); // Clear warnings

            // AUTOMATIC PROCESSING & PATH GENERATION (Minimal user friction)
            processImage();
        } else {
            alert(`Upload Failed: ${data.message}`);
        }
    })
    .catch(err => alert(`Network Upload Error: ${err.message}`));
}

// ==========================================================================
// 3. OPENCV SETTINGS & PROCESSING
// ==========================================================================
function initSliders() {
    const modeSelect = document.getElementById('modeSelect');
    const thresholdSlider = document.getElementById('thresholdSlider');
    const cannyLowSlider = document.getElementById('cannyLowSlider');
    const cannyHighSlider = document.getElementById('cannyHighSlider');
    const toleranceSlider = document.getElementById('toleranceSlider');
    const minAreaSlider = document.getElementById('minAreaSlider');

    // Live slider value update displays
    thresholdSlider.addEventListener('input', (e) => document.getElementById('thresholdVal').textContent = e.target.value);
    cannyLowSlider.addEventListener('input', (e) => document.getElementById('cannyLowVal').textContent = e.target.value);
    cannyHighSlider.addEventListener('input', (e) => document.getElementById('cannyHighVal').textContent = e.target.value);
    toleranceSlider.addEventListener('input', (e) => document.getElementById('toleranceVal').textContent = e.target.value);
    minAreaSlider.addEventListener('input', (e) => document.getElementById('minAreaVal').textContent = e.target.value);

    // Auto-trigger re-processing when preset style changes
    modeSelect.addEventListener('change', (e) => {
        const mode = e.target.value;
        const threshField = document.getElementById('thresholdField');
        const cannyFields = document.getElementById('cannyFields');

        if (mode === 'edge') {
            threshField.classList.add('hidden');
            cannyFields.classList.remove('hidden');
        } else if (mode === 'threshold') {
            threshField.classList.remove('hidden');
            cannyFields.classList.add('hidden');
        } else {
            threshField.classList.add('hidden');
            cannyFields.classList.add('hidden');
        }

        if (state.uploadedFilename) {
            processImage();
        }
    });

    document.getElementById('processBtn').addEventListener('click', processImage);
}

function processImage() {
    const processBtn = document.getElementById('processBtn');
    processBtn.disabled = true;
    processBtn.innerHTML = "<span>⏳ Processing...</span>";

    const payload = {
        mode: document.getElementById('modeSelect').value,
        threshold: parseInt(document.getElementById('thresholdSlider').value),
        canny_low: parseInt(document.getElementById('cannyLowSlider').value),
        canny_high: parseInt(document.getElementById('cannyHighSlider').value),
        blur_type: document.getElementById('blurSelect').value,
        contour_retrieval: document.getElementById('retrievalSelect').value,
        simplification_tolerance: parseFloat(document.getElementById('toleranceSlider').value),
        min_contour_area: parseFloat(document.getElementById('minAreaSlider').value),
        invert_image: document.getElementById('invertCheckbox').checked
    };

    fetch('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        processBtn.disabled = false;
        processBtn.innerHTML = "<span>⚙️ PROCESS IMAGE</span>";

        if (data.success) {
            state.contours = data.contours;

            // Update Image Stage Previews
            if (data.previews) {
                document.getElementById('imgStageGrayscale').src = data.previews.grayscale;
                document.getElementById('imgStageProcessed').src = data.previews.processed;
                document.getElementById('imgStageContours').src = data.previews.contours_preview;
            }

            // Show Warning if any
            showWarning(data.warning);

            // Enable Generate Path button
            document.getElementById('generatePathBtn').disabled = false;
            
            // Auto generate path after processing
            generateRobotPath();
        } else {
            alert(`Processing Error: ${data.message}`);
        }
    })
    .catch(err => {
        processBtn.disabled = false;
        processBtn.innerHTML = "<span>⚙️ PROCESS IMAGE</span>";
        alert(`Error: ${err.message}`);
    });
}

// ==========================================================================
// 4. PATH GENERATION & COORDINATE TRANSFORMATION
// ==========================================================================
function generateRobotPath() {
    const generateBtn = document.getElementById('generatePathBtn');
    generateBtn.disabled = true;
    generateBtn.textContent = "📐 Generating Path...";

    const paperSize = document.getElementById('paperSizeSelect').value;
    const payload = {
        paper_size: paperSize,
        paper_width_mm: parseFloat(document.getElementById('customWidthInput').value),
        paper_height_mm: parseFloat(document.getElementById('customHeightInput').value),
        margin_left: parseFloat(document.getElementById('marginLeft').value),
        margin_right: parseFloat(document.getElementById('marginRight').value),
        margin_top: parseFloat(document.getElementById('marginTop').value),
        margin_bottom: parseFloat(document.getElementById('marginBottom').value),
        origin: document.getElementById('originSelect').value,
        scale_mode: document.getElementById('scaleModeSelect').value,
        maintain_aspect: true
    };

    fetch('/api/generate-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        generateBtn.disabled = false;
        generateBtn.textContent = "📐 GENERATE ROBOT PATH";

        if (data.success) {
            state.pathData = data.path_data;
            updateStatsUI(data.path_data.stats);
            renderPathCanvas();

            // Enable Export & Send buttons
            document.getElementById('exportJsonBtn').disabled = false;
            document.getElementById('exportCsvBtn').disabled = false;
            document.getElementById('savePathBtn').disabled = false;
            document.getElementById('btnSendRobot').disabled = false;
        } else {
            alert(`Path Generation Error: ${data.message}`);
        }
    })
    .catch(err => {
        generateBtn.disabled = false;
        generateBtn.textContent = "📐 GENERATE ROBOT PATH";
        alert(`Error: ${err.message}`);
    });
}

function updateStatsUI(stats) {
    if (!stats) return;
    document.getElementById('statContours').textContent = stats.total_contours;
    document.getElementById('statPoints').textContent = stats.total_points.toLocaleString();
    document.getElementById('statDrawDist').textContent = `${stats.pen_down_distance_mm} mm`;
    document.getElementById('statTravelDist').textContent = `${stats.pen_up_distance_mm} mm`;
    document.getElementById('statEstTime').textContent = stats.estimated_time_formatted;
    document.getElementById('statBounds').textContent = `${stats.drawing_width_mm} × ${stats.drawing_height_mm} mm`;
}

// ==========================================================================
// 5. HTML5 CANVAS VECTOR PATH RENDERER
// ==========================================================================
function renderPathCanvas() {
    const canvas = document.getElementById('pathCanvas');
    const ctx = canvas.getContext('2d');
    
    if (!state.pathData) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
    }

    const paper = state.pathData.paper;
    const paperW = paper.width_mm;
    const paperH = paper.height_mm;
    const margins = paper.margins;
    const originMode = state.pathData.origin;

    // Update Paper & Origin badges
    document.getElementById('paperDimensionsBadge').textContent = `Paper: ${paperW} × ${paperH} mm`;
    document.getElementById('originBadge').textContent = `Origin: ${originMode.toUpperCase()} (0,0)`;

    // Calculate screen scaling pixels-per-mm so paper fits nicely in view
    const viewW = canvas.parentElement.clientWidth || 800;
    const viewH = canvas.parentElement.clientHeight || 600;
    
    canvas.width = viewW;
    canvas.height = viewH;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();

    // Apply Pan and Zoom transforms
    ctx.translate(canvas.width / 2 + state.panX, canvas.height / 2 + state.panY);
    ctx.scale(state.zoomLevel, state.zoomLevel);

    const scale = Math.min((viewW - 60) / paperW, (viewH - 60) / paperH);
    const sheetW = paperW * scale;
    const sheetH = paperH * scale;

    // Center of paper sheet
    const sheetX = -sheetW / 2;
    const sheetY = -sheetH / 2;

    // 1. Draw Paper Sheet (White rectangular sheet)
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.5)';
    ctx.shadowBlur = 20;
    ctx.fillRect(sheetX, sheetY, sheetW, sheetH);
    ctx.shadowBlur = 0; // Reset shadow

    // 2. Draw Margins (Dashed red box)
    const marginLx = sheetX + margins.left_mm * scale;
    const marginRx = sheetX + (paperW - margins.right_mm) * scale;
    const marginTy = sheetY + margins.top_mm * scale;
    const marginBy = sheetY + (paperH - margins.bottom_mm) * scale;

    ctx.strokeStyle = 'rgba(255, 82, 82, 0.4)';
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(marginLx, marginTy, marginRx - marginLx, marginBy - marginTy);
    ctx.setLineDash([]); // Reset dash

    // Coordinate conversion function: mm on paper -> Canvas screen pixels
    const mmToCanvasPx = (x_mm, y_mm) => {
        let px, py;
        if (originMode === 'bottom_left') {
            px = sheetX + x_mm * scale;
            py = sheetY + (paperH - y_mm) * scale; // Invert Y so +Y is UP
        } else if (originMode === 'top_left') {
            px = sheetX + x_mm * scale;
            py = sheetY + y_mm * scale;
        } else {
            // center
            px = sheetX + (paperW / 2 + x_mm) * scale;
            py = sheetY + (paperH / 2 - y_mm) * scale;
        }
        return { x: px, y: py };
    };

    // 3. Draw Coordinate Axes & Origin Marker
    const originPx = mmToCanvasPx(0, 0);
    
    // Draw Axis arrows
    ctx.lineWidth = 2;
    // X Axis (Red Arrow pointing Right)
    ctx.strokeStyle = '#ff1744';
    ctx.beginPath();
    ctx.moveTo(originPx.x, originPx.y);
    ctx.lineTo(originPx.x + 40, originPx.y);
    ctx.stroke();

    // Y Axis (Green Arrow pointing Up)
    ctx.strokeStyle = '#00e676';
    ctx.beginPath();
    ctx.moveTo(originPx.x, originPx.y);
    ctx.lineTo(originPx.x, originPx.y - 40);
    ctx.stroke();

    // Origin Dot
    ctx.fillStyle = '#00f2fe';
    ctx.beginPath();
    ctx.arc(originPx.x, originPx.y, 5, 0, Math.PI * 2);
    ctx.fill();

    // 4. Render Robot Path Commands
    const commands = state.pathData.commands || [];
    let curPx = mmToCanvasPx(0, 0);
    let penState = 'UP';

    for (let i = 0; i < commands.length; i++) {
        const cmd = commands[i];
        if (cmd.type === 'PEN_UP') {
            penState = 'UP';
        } else if (cmd.type === 'PEN_DOWN') {
            penState = 'DOWN';
        } else if (cmd.type === 'MOVE') {
            const nextPx = mmToCanvasPx(cmd.x, cmd.y);

            ctx.beginPath();
            ctx.moveTo(curPx.x, curPx.y);
            ctx.lineTo(nextPx.x, nextPx.y);

            if (penState === 'DOWN') {
                // Solid Cyan Draw Line
                ctx.strokeStyle = '#00c853'; // Vibrant Green Pen-down
                ctx.lineWidth = 1.8;
                ctx.setLineDash([]);
                ctx.stroke();
            } else {
                // Dotted Blue Travel Line
                ctx.strokeStyle = 'rgba(79, 172, 254, 0.4)';
                ctx.lineWidth = 1.0;
                ctx.setLineDash([3, 3]);
                ctx.stroke();
            }

            curPx = nextPx;
        }
    }
    ctx.setLineDash([]);

    // 5. Draw Start Point (Green circle) & End Point (Red circle)
    if (state.pathData.contours_mm && state.pathData.contours_mm.length > 0) {
        const firstCnt = state.pathData.contours_mm[0];
        const lastCnt = state.pathData.contours_mm[state.pathData.contours_mm.length - 1];

        if (firstCnt.length > 0) {
            const startPx = mmToCanvasPx(firstCnt[0][0], firstCnt[0][1]);
            ctx.fillStyle = '#00e676';
            ctx.beginPath();
            ctx.arc(startPx.x, startPx.y, 6, 0, Math.PI * 2);
            ctx.fill();
        }

        if (lastCnt.length > 0) {
            const endPx = mmToCanvasPx(lastCnt[lastCnt.length - 1][0], lastCnt[lastCnt.length - 1][1]);
            ctx.fillStyle = '#ff5252';
            ctx.beginPath();
            ctx.arc(endPx.x, endPx.y, 6, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    // 6. Draw Virtual Robot Animation Indicator ( Glowing Robot ● Marker )
    const robotPx = mmToCanvasPx(state.robotStatus.x, state.robotStatus.y);
    ctx.shadowColor = '#00f2fe';
    ctx.shadowBlur = 12;
    ctx.fillStyle = state.robotStatus.penState === 'DOWN' ? '#00e676' : '#ffb300';
    ctx.beginPath();
    ctx.arc(robotPx.x, robotPx.y, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Label: ROBOT ●
    ctx.fillStyle = '#000000';
    ctx.font = 'bold 10px monospace';
    ctx.fillText("ROBOT", robotPx.x + 10, robotPx.y + 3);

    ctx.restore();
}

function initCanvasPanZoom() {
    const viewport = document.getElementById('canvasViewport');
    
    document.getElementById('zoomInBtn').addEventListener('click', () => {
        state.zoomLevel *= 1.2;
        renderPathCanvas();
    });

    document.getElementById('zoomOutBtn').addEventListener('click', () => {
        state.zoomLevel /= 1.2;
        renderPathCanvas();
    });

    document.getElementById('zoomResetBtn').addEventListener('click', () => {
        state.zoomLevel = 1.0;
        state.panX = 0;
        state.panY = 0;
        renderPathCanvas();
    });

    // Mouse Pan Dragging
    viewport.addEventListener('mousedown', (e) => {
        state.isDraggingCanvas = true;
        state.dragStartX = e.clientX - state.panX;
        state.dragStartY = e.clientY - state.panY;
    });

    window.addEventListener('mousemove', (e) => {
        if (state.isDraggingCanvas) {
            state.panX = e.clientX - state.dragStartX;
            state.panY = e.clientY - state.dragStartY;
            renderPathCanvas();
        }
    });

    window.addEventListener('mouseup', () => {
        state.isDraggingCanvas = false;
    });
}

// ==========================================================================
// 6. ROBOT TELEMETRY & CONTROL ACTIONS
// ==========================================================================
function startStatusPolling() {
    setInterval(() => {
        fetch('/api/robot/status')
        .then(res => res.json())
        .then(data => {
            if (data) {
                if (state.isEmergencyStopped) {
                    data.state = 'STOPPED';
                    data.pen_state = 'UP';
                }
                state.robotStatus.state = data.state || 'IDLE';
                if (data.position) {
                    state.robotStatus.x = data.position.x || 0.0;
                    state.robotStatus.y = data.position.y || 0.0;
                }
                state.robotStatus.penState = data.pen_state || 'UP';
                state.robotStatus.progress = data.progress || 0.0;
                state.robotStatus.cmdIdx = data.command_index || 0;
                state.robotStatus.totalCmds = data.total_commands || 0;

                updateTelemetryUI(data);
                renderPathCanvas(); // Update animated robot position on paper canvas
            }
        })
        .catch(() => {});
    }, 1000);
}

function updateTelemetryUI(status) {
    const badge = document.getElementById('robotStateBadge');
    badge.textContent = status.state;
    badge.className = `t-badge ${status.state.toLowerCase()}`;

    document.getElementById('robotPosText').textContent = `X: ${status.position?.x.toFixed(2)} mm | Y: ${status.position?.y.toFixed(2)} mm`;
    document.getElementById('robotPenText').textContent = status.pen_state;
    document.getElementById('robotProgressBar').style.width = `${status.progress}%`;
    document.getElementById('robotProgressText').textContent = `${status.progress.toFixed(0)}%`;
    document.getElementById('robotCmdCounter').textContent = `${status.command_index} / ${status.total_commands}`;
}

function initButtons() {
    // Test & Connect ESP32
    document.getElementById('testConnectBtn').addEventListener('click', testConnection);
    document.getElementById('connectBtn').addEventListener('click', testConnection);

    // Robot Control Buttons (SEND TO ROBOT uploads path & immediately starts drawing)
    document.getElementById('btnSendRobot').addEventListener('click', () => {
        sendPathAndStartRobot();
    });
    
    document.getElementById('btnEmergencyStop').addEventListener('click', () => {
        triggerEmergencyStop();
    });

    document.getElementById('btnHome').addEventListener('click', () => sendAction('home'));
    document.getElementById('btnPenUp').addEventListener('click', () => sendAction('pen_up'));
    document.getElementById('btnPenDown').addEventListener('click', () => sendAction('pen_down'));

    // Export Buttons
    document.getElementById('exportJsonBtn').addEventListener('click', () => window.location.href = '/api/path/export/json');
    document.getElementById('exportCsvBtn').addEventListener('click', () => window.location.href = '/api/path/export/csv');
    document.getElementById('savePathBtn').addEventListener('click', () => {
        fetch('/api/path/save', { method: 'POST' })
        .then(res => res.json())
        .then(d => alert(d.message));
    });
}

function testConnection() {
    state.esp32Ip = document.getElementById('esp32IpInput').value;
    fetch('/api/robot/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ esp32_ip: state.esp32Ip, simulation_mode: false })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            updateConnectionBadge(true, `Connected (${state.esp32Ip})`);
            alert(`Successfully connected to ESP32 at ${state.esp32Ip}`);
        } else {
            updateConnectionBadge(false, "ESP32 Disconnected");
            alert(`Connection Failed: ${data.message}`);
        }
    });
}

function updateConnectionBadge(connected, text) {
    const badge = document.getElementById('connectionBadge');
    const badgeText = document.getElementById('connectionBadgeText');

    if (connected) {
        badge.className = "connection-badge connected";
        badgeText.textContent = text;
    } else {
        badge.className = "connection-badge disconnected";
        badgeText.textContent = text;
    }
}

function sendPathAndStartRobot() {
    if (!state.pathData) {
        alert("Please generate a robot path first!");
        return;
    }

    if (!confirm(`Confirm sending ${state.pathData.stats.total_points} point path to ESP32 (${state.esp32Ip})? The robot will start moving immediately!`)) {
        return;
    }

    state.isEmergencyStopped = false;

    // 1. Upload path to ESP32
    fetch('/api/robot/upload-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            state.pathUploaded = true;
            // 2. Immediately trigger robot start motion
            sendAction('start');
            alert("Path uploaded! Physical robot drawing started.");
        } else {
            alert(`Upload Error: ${data.message}`);
        }
    })
    .catch(err => alert(`Network Error: ${err.message}`));
}

function sendAction(action) {
    if (action === 'start' || action === 'upload_path') {
        state.isEmergencyStopped = false;
    }
    fetch(`/api/robot/control/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (!data.success) {
            alert(`Action Failed: ${data.message}`);
        }
    });
}

function triggerEmergencyStop() {
    // 1. Immediately set emergency stopped flag & force local state to STOPPED & Pen UP
    state.isEmergencyStopped = true;
    state.robotStatus.state = 'STOPPED';
    state.robotStatus.penState = 'UP';
    
    // 2. Force immediate UI update
    updateTelemetryUI({
        state: 'STOPPED',
        position: { x: state.robotStatus.x || 0.0, y: state.robotStatus.y || 0.0 },
        pen_state: 'UP',
        progress: state.robotStatus.progress || 0.0,
        command_index: state.robotStatus.cmdIdx || 0,
        total_commands: state.robotStatus.totalCmds || 0
    });
    
    showWarning("🚨 EMERGENCY STOP ACTIVATED: Robot motion halted and pen lifted!");

    // 3. Dispatch POST to /api/robot/control/estop
    fetch('/api/robot/control/estop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    }).catch(() => {});

    alert("🚨 EMERGENCY STOP ACTIVATED! Robot motion halted.");
}

// ==========================================================================
// 7. TAB SWITCHING
// ==========================================================================
function initTabSwitching() {
    const tabPath = document.getElementById('tabPath');
    const tabStages = document.getElementById('tabStages');
    const pathWrapper = document.getElementById('pathCanvasWrapper');
    const stagesWrapper = document.getElementById('stagesWrapper');

    tabPath.addEventListener('click', () => {
        tabPath.classList.add('active');
        tabStages.classList.remove('active');
        pathWrapper.classList.remove('hidden');
        stagesWrapper.classList.add('hidden');
        renderPathCanvas();
    });

    tabStages.addEventListener('click', () => {
        tabStages.classList.add('active');
        tabPath.classList.remove('active');
        stagesWrapper.classList.remove('hidden');
        pathWrapper.classList.add('hidden');
    });
}

function showWarning(msg) {
    const alertBox = document.getElementById('warningAlert');
    const alertMsg = document.getElementById('warningMessage');

    if (msg) {
        alertMsg.textContent = msg;
        alertBox.classList.remove('hidden');
    } else {
        alertBox.classList.add('hidden');
    }
}
