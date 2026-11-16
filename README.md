# 🤖 2-Wheel Drawing Robot Web Application

A beginner-friendly, modular, and full-featured web application designed to convert standard raster images (PNG, JPG, BMP, WEBP) into physical 2D vector drawing paths for a 2-wheel ESP32 drawing robot.

---

## 🌟 Project Features

- **Modular Architecture**: Clean separation between Frontend, Flask Web Server, OpenCV Image Processor, Path Generator, Coordinate Converter, ESP32 Communication, and Configuration modules.
- **OpenCV Computer Vision Pipeline**:
  - Image Loading & Auto-Downscaling (max 2000×2000 for fast performance)
  - Grayscale Conversion
  - Noise Reduction (Gaussian & Median Blur)
  - Binarization (Global Threshold, Otsu Threshold, Adaptive Threshold, Canny Edge Detection)
  - Vector Contour Extraction (`cv2.findContours`)
  - Noise Contour Filtering (min area & length)
  - **Douglas-Peucker Point Simplification** (`cv2.approxPolyDP`) to prevent thousands of unnecessary robot moves while preserving shape geometry.
- **Physical Millimetre Coordinate Converter**:
  - Image Pixel space $\rightarrow$ Normalized space $[0.0, 1.0]$ $\rightarrow$ Paper Millimetre space.
  - Paper Size presets (**A4**, **A3**, **A5**, **Custom**).
  - Margin safety enforcement (Left, Right, Top, Bottom).
  - **Cartesian Y-Axis Inversion** (OpenCV Y-down $\rightarrow$ Robot Y-up).
  - Configurable Robot Origins (**Bottom-Left (0,0)**, Top-Left, Center).
- **Interactive HTML5 Vector Path Canvas**:
  - Live paper canvas preview with paper sheet background, margin boundary lines, coordinate axes, and origin markers.
  - Interactive Pan & Zoom.
  - Visual distinction between **Pen-DOWN** draw lines (solid green) and **Pen-UP** travel moves (dotted blue).
  - Start (Green dot) & End (Red dot) markers.
- **Built-in Virtual Robot Simulator**:
  - Allows full end-to-end testing without physical hardware attached.
  - Live animated robot marker (`ROBOT ●`) follows drawing paths on canvas step-by-step.
  - Real-time progress bar, command index counter, and position telemetry (`X`, `Y`, `Pen State`).
- **Path Optimization & Exports**:
  - Greedy Nearest-Neighbor contour reordering to minimize pen-up travel distance.
  - Path statistics (Draw distance mm, Travel distance mm, Total distance mm, Estimated drawing time).
  - **JSON** & **CSV** path file export (`MOVE, X_MM, Y_MM, PEN_STATE`).
- **ESP32 Wi-Fi REST API Client**:
  - Test connection, send paths, and control robot operations (`HOME`, `START`, `PAUSE`, `RESUME`, `STOP`, `PEN UP`, `PEN DOWN`, `EMERGENCY STOP`).
  - Manual Robot Jog Controls (Up, Down, Left, Right with selectable mm step size).

---

## 📂 Project Structure

```text
drawing_robot/
├── app.py                      # Flask web server & REST API controller
├── requirements.txt            # Python package dependencies
├── config.py                   # System configuration & default settings
├── image_processor.py          # OpenCV computer vision pipeline
├── path_processor.py           # Path optimization, commands & statistics
├── coordinate_converter.py     # Pixel to Millimetre transformations
├── robot_communication.py      # ESP32 REST client & Virtual Robot Simulator
├── utils.py                    # File handling, base64 encoding & helpers
├── calibration.json            # Saved robot hardware parameters
├── README.md                   # Beginner guide & documentation
├── uploads/                    # Uploaded image storage directory
├── generated_paths/            # Saved JSON & CSV robot path files
├── templates/
│   └── index.html              # Main dashboard UI HTML5 template
└── static/
    ├── css/
    │   └── style.css           # Cyberpunk dark-mode stylesheet
    ├── js/
    │   └── app.js              # Vanilla JavaScript frontend logic
    └── images/
        └── sample_drawing.png  # Pre-packaged test line art drawing
```

---

## 📐 Understanding the Mathematical Transformation

To transform a standard digital image into a physical robot drawing, the application performs this step-by-step pipeline:

$$\text{IMAGE (Pixels)} \rightarrow \text{GRAYSCALE} \rightarrow \text{CANNY / THRESHOLD} \rightarrow \text{CONTOURS} \rightarrow \text{SIMPLIFIED POINTS} \rightarrow \text{NORMALIZED} \rightarrow \text{MILLIMETRES} \rightarrow \text{ROBOT PATH}$$

### 1. Pixel Normalization
Given an image point $(x_{px}, y_{px})$ inside an image of width $W_{img}$ and height $H_{img}$:

$$x_{norm} = \frac{x_{px}}{W_{img}}, \quad y_{norm} = \frac{y_{px}}{H_{img}} \quad \in [0.0, 1.0]$$

### 2. Physical Paper Scaling
Available drawing width and height inside paper margins:

$$W_{avail} = W_{paper} - \text{Margin}_{left} - \text{Margin}_{right}$$

$$H_{avail} = H_{paper} - \text{Margin}_{top} - \text{Margin}_{bottom}$$

The image aspect ratio $AR = W_{img} / H_{img}$ is maintained:

$$\text{If } AR > \frac{W_{avail}}{H_{avail}} \implies W_{draw} = W_{avail}, \quad H_{draw} = \frac{W_{avail}}{AR}$$

$$\text{Else } \implies H_{draw} = H_{avail}, \quad W_{draw} = H_{avail} \cdot AR$$

### 3. Robot Cartesian Transformation (Bottom-Left Origin & Y-Inversion)
Since OpenCV places $(0,0)$ at Top-Left ($+Y$ Down) and standard Cartesian robots place $(0,0)$ at Bottom-Left ($+Y$ Upward/Forward):

$$X_{mm} = \text{Margin}_{left} + x_{norm} \cdot W_{draw}$$

$$Y_{mm} = \text{Margin}_{bottom} + (1.0 - y_{norm}) \cdot H_{draw}$$

---

## 🚀 Quick Start & Installation

### Step 1: Clone or Navigate to Project Directory
```bash
cd "c:\Users\moham\Desktop\web app for drawing robo"
```

### Step 2: Install Python Dependencies
Make sure Python 3.8+ is installed. Run:
```bash
pip install -r requirements.txt
```

### Step 3: Launch the Flask Server
```bash
python app.py
```

You will see the terminal output:
```text
============================================================
 🤖 2-WHEEL DRAWING ROBOT WEB APPLICATION SERVER 
============================================================
 * Server running on: http://127.0.0.1:5000/
 * Simulation Mode: ENABLED
============================================================
```

### Step 4: Open Browser Dashboard
Open your web browser and navigate to:
[http://127.0.0.1:5000/](http://127.0.0.1:5000/)

---

## 🎮 How to Use the Web Application

1. **Upload an Image**:
   - Drag and drop an image file (PNG, JPG, BMP, WEBP) onto the upload box or click **Choose File**.
   - An image summary (filename, pixel dimensions, file size) will appear.
2. **Process Image**:
   - Choose a mode (e.g. **Edge Detection (Canny)**).
   - Adjust the **Point Simplification Tolerance** slider (higher tolerance = fewer points & smoother curves).
   - Click **⚙️ PROCESS IMAGE**.
   - Switch to the **Image Processing Stages** tab to inspect Grayscale, Threshold, and Extracted Contours.
3. **Configure Paper & Generate Path**:
   - Select your paper size (**A4**, **A3**, **A5**, or **Custom**).
   - Click **📐 GENERATE ROBOT PATH**.
   - The path statistics panel will display total contours, point count, draw distance, travel distance, and estimated time.
4. **Test in Simulation Mode**:
   - Simulation Mode is **ON** by default in the top header.
   - Click **▶️ START**.
   - Watch the glowing virtual robot marker (`ROBOT ●`) navigate your drawing on the paper canvas in real time!
5. **Export Path**:
   - Click **JSON** or **CSV** to download the generated command list.

---

## 📡 ESP32 Hardware Integration & REST API

When you are ready to connect a physical ESP32 drawing robot:

1. Connect your computer and ESP32 to the same Wi-Fi network.
2. Find the IP address assigned to your ESP32 (e.g. `192.168.1.100`).
3. Enter the IP in the **ESP32 IP Address** field in the right panel.
4. Uncheck **Simulation Mode** in the header.
5. Click **Test Connection** or **Connect**.

### ESP32 REST API Endpoints Required on Micro-controller Firmware:

- `GET /status` $\rightarrow$ Returns JSON telemetry: `{"state": "IDLE", "x": 0.0, "y": 0.0, "pen": "UP"}`
- `POST /draw` $\rightarrow$ Accepts JSON payload containing drawing command array `[{"type": "MOVE", "x": 15.0, "y": 20.0}, ...]`
- `POST /start` $\rightarrow$ Starts motor execution.
- `POST /pause` $\rightarrow$ Pauses motor execution.
- `POST /resume` $\rightarrow$ Resumes motor execution.
- `POST /stop` $\rightarrow$ Immediately halts motor movement and lifts pen.
- `POST /home` $\rightarrow$ Moves robot back to physical origin $(0, 0)$.
- `POST /pen/up` $\rightarrow$ Lifts pen servo (e.g. Servo angle $90^\circ$).
- `POST /pen/down` $\rightarrow$ Lowers pen servo (e.g. Servo angle $0^\circ$).

---

## 🛠️ Troubleshooting & FAQ

- **Q: Why does the processed image have no contours?**
  - **A**: The threshold or Canny high threshold might be too high. Decrease Canny High/Low sliders or try **Simple Outline (Otsu Threshold)** mode.
- **Q: The drawing is too large for my paper!**
  - **A**: Keep **Scale Mode** set to `Fit to Paper Area` and make sure paper margins are set to at least 15 mm.
- **Q: Why are there so many points?**
  - **A**: Increase the **Point Simplification Tolerance** slider (e.g. from 1.5 to 3.0 or 5.0). This uses Douglas-Peucker simplification to reduce point counts dramatically.
- **Q: How does the robot lift the pen between lines?**
  - **A**: The generator automatically inserts `PEN_UP` before moving to a new contour, moves to the start point, sends `PEN_DOWN`, draws the contour points, and sends `PEN_UP` at the end.

---

## 📄 License & Open Source

Built with Python, Flask, OpenCV, NumPy, HTML5, CSS3, and Vanilla JavaScript. Free for educational and open-source robotics projects!
