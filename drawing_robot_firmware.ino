#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <AccelStepper.h>
#include <ESP32Servo.h>
#include <math.h>

// ======================================================
// WIFI SETTINGS - Preserves Dashboard Communication
// ======================================================
const char* WIFI_SSID = "LAPTOP1";
const char* WIFI_PASSWORD = "123123123";

#define USE_STATIC_IP false
IPAddress local_IP(192, 168, 1, 100);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(8, 8, 8, 8);
IPAddress secondaryDNS(8, 8, 4, 4);

WebServer server(80);

// ======================================================
// ESP32 PIN CONFIGURATION (Verified Hardware Assignment)
// ======================================================
// LEFT MOTOR (HR4988 / A4988)
#define LEFT_STEP_PIN     25
#define LEFT_DIR_PIN      26

// RIGHT MOTOR (HR4988 / A4988)
#define RIGHT_STEP_PIN    32
#define RIGHT_DIR_PIN     33

// COMMON DRIVER ENABLE (Active LOW)
#define DRIVER_ENABLE_PIN 27

// PEN SERVO (MG90S)
#define SERVO_PIN         14

#define DRIVER_ENABLED    LOW
#define DRIVER_DISABLED   HIGH

AccelStepper leftMotor(AccelStepper::DRIVER, LEFT_STEP_PIN, LEFT_DIR_PIN);
AccelStepper rightMotor(AccelStepper::DRIVER, RIGHT_STEP_PIN, RIGHT_DIR_PIN);
Servo penServo;

// ======================================================
// CALIBRATION & HARDWARE MEASUREMENTS (Verified Physical Specs)
// ======================================================
float WHEEL_DIAMETER_MM    = 60.0f;   // Drive wheel diameter in mm
float WHEEL_BASE_MM        = 260.0f;  // Distance between drive-wheel centers in mm
float MOTOR_STEPS_PER_REV  = 200.0f;  // Full-step mode (1.8 deg per step)

// Motor direction signs from working standalone code:
// Right motor is physically mirrored on chassis, so sign must be -1.0f
float LEFT_MOTOR_SIGN      = 1.0f;
float RIGHT_MOTOR_SIGN     = -1.0f;

// SERVO CALIBRATION (from working standalone test code)
const int PEN_UP_ANGLE     = 90;      // Lifted above paper
const int PEN_DOWN_ANGLE   = 40;      // Touching paper for drawing
bool penDown               = false;

// ======================================================
// PEN OFFSET & DIFFERENTIAL-DRIVE ROTATION SAFEGUARD
// ======================================================
// Physical pen is 160 mm away from the midpoint of the drive-wheel axle.
float PEN_OFFSET_MM        = 160.0f;

// When the pen is DOWN, rotating in place swings the pen tip along an
// arc of radius PEN_OFFSET_MM around the wheel axle midpoint.
// AUTO_LIFT_PEN_ON_TURN automatically raises the pen during in-place turns,
// preventing circular scratch marks on the paper, and lowers it before driving straight.
bool AUTO_LIFT_PEN_ON_TURN = true;

// SPEED & ACCELERATION
const float MAX_SPEED_STEPS      = 600.0f;
const float ACCELERATION_STEPS   = 300.0f;
const float POSITION_TOLERANCE_MM = 0.05f;
const int   MAX_COMMANDS         = 600;

struct RobotCommand {
  String type; // "MOVE", "PEN_UP", "PEN_DOWN"
  float x;
  float y;
};

enum RobotState { IDLE, HOMING, DRAWING, PAUSED, STOPPED, ERROR_STATE, COMPLETE };
enum MotionPhase { MOTION_NONE, MOTION_TURNING, MOTION_DRIVING };

RobotCommand commands[MAX_COMMANDS];
int commandCount     = 0;
int currentCommand   = 0;
RobotState robotState = IDLE;
MotionPhase motionPhase = MOTION_NONE;

// Pose estimation:
// robotX, robotY: estimated Cartesian position on paper (mm)
// robotHeading: heading in radians (0 = along +X / East, PI/2 = along +Y / North)
float robotX = 0.0f, robotY = 0.0f, robotHeading = 0.0f;
float targetX = 0.0f, targetY = 0.0f, targetHeading = 0.0f;
float currentMoveDistance = 0.0f;
bool activeMove = false;
bool emergencyStopLatched = false;
bool penWasDownBeforeTurn = false;

// ------------------------------------------------------
// Status Helpers & CORS
// ------------------------------------------------------
String getRobotState() {
  switch (robotState) {
    case IDLE:        return "IDLE";
    case HOMING:      return "HOMING";
    case DRAWING:     return "DRAWING";
    case PAUSED:      return "PAUSED";
    case STOPPED:     return "STOPPED";
    case ERROR_STATE: return "ERROR";
    case COMPLETE:    return "COMPLETE";
  }
  return "UNKNOWN";
}

void addCORS() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void sendJson(int status, JsonDocument& doc) {
  String response;
  serializeJson(doc, response);
  server.send(status, "application/json", response);
}

// ------------------------------------------------------
// Driver Enable / Disable (Active LOW)
// ------------------------------------------------------
void enableDrivers() {
  digitalWrite(DRIVER_ENABLE_PIN, DRIVER_ENABLED);
  leftMotor.enableOutputs();
  rightMotor.enableOutputs();
}

void disableDrivers() {
  digitalWrite(DRIVER_ENABLE_PIN, DRIVER_DISABLED);
  leftMotor.disableOutputs();
  rightMotor.disableOutputs();
}

// ------------------------------------------------------
// Kinematics Conversions
// ------------------------------------------------------
float stepsPerMM() {
  return MOTOR_STEPS_PER_REV / (PI * WHEEL_DIAMETER_MM);
}

long mmToSteps(float mm) {
  return lroundf(mm * stepsPerMM());
}

float normalizeAngle(float angle) {
  while (angle > PI)  angle -= 2.0f * PI;
  while (angle < -PI) angle += 2.0f * PI;
  return angle;
}

// ------------------------------------------------------
// Pen Servo Controls
// ------------------------------------------------------
void penUp() {
  penServo.write(PEN_UP_ANGLE);
  penDown = false;
  Serial.println("PEN UP");
}

void penDownNow() {
  penServo.write(PEN_DOWN_ANGLE);
  penDown = true;
  Serial.println("PEN DOWN");
}

// ------------------------------------------------------
// Differential Drive Movement
// ------------------------------------------------------
// Rotate in place by specified angle in radians.
// Positive angle is counter-clockwise (left turn).
void startTurn(float angle) {
  float wheelTravel = (WHEEL_BASE_MM * 0.5f) * angle;
  long turnSteps = mmToSteps(fabsf(wheelTravel));
  int sign = (angle >= 0.0f) ? 1 : -1;

  // Counter-clockwise: left motor moves backward, right motor moves forward
  leftMotor.move((long)(-turnSteps * sign * LEFT_MOTOR_SIGN));
  rightMotor.move((long)(turnSteps * sign * RIGHT_MOTOR_SIGN));
  motionPhase = MOTION_TURNING;
}

// Drive both wheels forward in a straight line by distance in mm.
void startStraight(float distance) {
  long steps = mmToSteps(distance);
  leftMotor.move((long)(steps * LEFT_MOTOR_SIGN));
  rightMotor.move((long)(steps * RIGHT_MOTOR_SIGN));
  motionPhase = MOTION_DRIVING;
  Serial.printf("Straight distance: %.2f mm (%ld steps)\n", distance, steps);
}

// ------------------------------------------------------
// Prepare Move to Target (X, Y)
// ------------------------------------------------------
void prepareMoveTo(float x, float y) {
  targetX = x;
  targetY = y;

  float dx = targetX - robotX;
  float dy = targetY - robotY;
  currentMoveDistance = sqrtf(dx * dx + dy * dy);

  if (currentMoveDistance < POSITION_TOLERANCE_MM) {
    currentCommand++;
    activeMove = false;
    motionPhase = MOTION_NONE;
    return;
  }

  targetHeading = atan2f(dy, dx);
  float turnAngle = normalizeAngle(targetHeading - robotHeading);

  Serial.println("\n===== NEW MOVE =====");
  Serial.printf("From (%.2f, %.2f) to (%.2f, %.2f)\n", robotX, robotY, targetX, targetY);
  Serial.printf("Distance: %.2f mm; Turn: %.2f deg (Heading now: %.2f deg -> target: %.2f deg)\n",
                currentMoveDistance, turnAngle * 180.0f / PI,
                robotHeading * 180.0f / PI, targetHeading * 180.0f / PI);

  long turnSteps = mmToSteps(fabsf((WHEEL_BASE_MM * 0.5f) * turnAngle));
  activeMove = true;

  if (turnSteps > 0) {
    // If the pen is touching the paper, rotating around the axle midpoint
    // swings the pen tip in an arc of radius PEN_OFFSET_MM.
    // Safeguard: Lift the pen during in-place turns, then lower it before driving straight.
    if (AUTO_LIFT_PEN_ON_TURN && penDown) {
      penWasDownBeforeTurn = true;
      penServo.write(PEN_UP_ANGLE);
      delay(80); // Brief settling time for servo
    } else {
      penWasDownBeforeTurn = false;
    }
    startTurn(turnAngle);
  } else {
    penWasDownBeforeTurn = false;
    startStraight(currentMoveDistance);
  }
}

// ------------------------------------------------------
// Non-Blocking Motion Processor
// ------------------------------------------------------
void processMotion() {
  if (!activeMove || robotState != DRAWING) return;

  leftMotor.run();
  rightMotor.run();

  if (leftMotor.distanceToGo() == 0 && rightMotor.distanceToGo() == 0) {
    if (motionPhase == MOTION_TURNING) {
      robotHeading = targetHeading;
      Serial.println("Turn complete.");

      // If pen was raised for the turn, lower it before the straight move
      if (penWasDownBeforeTurn) {
        penServo.write(PEN_DOWN_ANGLE);
        delay(100); // Allow pen to seat on paper before moving forward
        penWasDownBeforeTurn = false;
      }

      startStraight(currentMoveDistance);
      return;
    }

    if (motionPhase == MOTION_DRIVING) {
      robotX = targetX;
      robotY = targetY;
      Serial.printf("Reached Target: X=%.2f Y=%.2f\n", robotX, robotY);
      activeMove = false;
      motionPhase = MOTION_NONE;
      currentCommand++;
    }
  }
}

// ------------------------------------------------------
// Drawing Command Sequencer
// ------------------------------------------------------
void processDrawing() {
  if (robotState != DRAWING) return;

  if (activeMove) {
    processMotion();
    return;
  }

  if (currentCommand >= commandCount) {
    robotState = COMPLETE;
    penUp();
    disableDrivers();
    Serial.println("===== DRAWING COMPLETE =====");
    return;
  }

  RobotCommand &cmd = commands[currentCommand];

  if (cmd.type == "PEN_UP") {
    penUp();
    currentCommand++;
    return;
  }

  if (cmd.type == "PEN_DOWN") {
    penDownNow();
    currentCommand++;
    return;
  }

  if (cmd.type == "MOVE") {
    prepareMoveTo(cmd.x, cmd.y);
    return;
  }

  currentCommand++;
}

// ======================================================
// HTTP ENDPOINTS (100% Compatible with Dashboard & Backend)
// ======================================================
void handleRoot() {
  addCORS();
  String msg = "Drawing Robot ESP32\nStatus: OK\nIP: " + WiFi.localIP().toString() +
               "\nState: " + getRobotState() + "\n";
  server.send(200, "text/plain", msg);
}

void handleStatus() {
  addCORS();
  JsonDocument doc;
  doc["status"] = "ok";
  doc["robot_state"] = getRobotState();
  doc["x"] = robotX;
  doc["y"] = robotY;
  doc["heading"] = robotHeading;
  doc["pen"] = penDown ? "DOWN" : "UP";
  doc["progress"] = commandCount ? (100.0f * currentCommand / commandCount) : 0.0f;
  doc["current_command"] = currentCommand;
  doc["total_commands"] = commandCount;
  doc["ip"] = WiFi.localIP().toString();
  doc["emergency_stop"] = emergencyStopLatched;
  sendJson(200, doc);
}

void handleDraw() {
  addCORS();
  if (emergencyStopLatched) {
    server.send(423, "application/json", "{\"received\":false,\"error\":\"Emergency stop latched. Use RESET after inspecting robot.\"}");
    return;
  }
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"received\":false,\"error\":\"No JSON data received\"}");
    return;
  }

  String body = server.arg("plain");
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, body);
  if (error) {
    Serial.print("JSON error: ");
    Serial.println(error.c_str());
    server.send(400, "application/json", "{\"received\":false,\"error\":\"Invalid JSON\"}");
    return;
  }

  JsonArray arr = doc["commands"].as<JsonArray>();
  if (arr.isNull()) {
    server.send(400, "application/json", "{\"received\":false,\"error\":\"commands array missing\"}");
    return;
  }

  commandCount = 0;
  currentCommand = 0;
  activeMove = false;
  motionPhase = MOTION_NONE;

  for (JsonObject item : arr) {
    if (commandCount >= MAX_COMMANDS) break;
    String type = item["type"] | "";
    if (type != "MOVE" && type != "PEN_UP" && type != "PEN_DOWN") {
      continue;
    }
    commands[commandCount].type = type;
    commands[commandCount].x = item["x"] | 0.0f;
    commands[commandCount].y = item["y"] | 0.0f;
    commandCount++;
  }

  Serial.printf("Path received: %d commands\n", commandCount);

  // AUTO-START: receiving a valid path begins drawing execution
  if (commandCount > 0) {
    enableDrivers();
    currentCommand = 0;
    activeMove = false;
    motionPhase = MOTION_NONE;
    robotState = DRAWING;
    Serial.println("==============================");
    Serial.println("DRAWING AUTO STARTED");
    Serial.println("==============================");
  } else {
    robotState = IDLE;
  }

  JsonDocument response;
  response["received"] = true;
  response["commands"] = commandCount;
  response["status"] = (commandCount > 0) ? "started" : "empty";
  sendJson(200, response);
}

void handleStart() {
  addCORS();
  if (emergencyStopLatched || robotState == ERROR_STATE) {
    server.send(423, "application/json", "{\"status\":\"error\",\"message\":\"Emergency stop active. Use RESET after inspection.\"}");
    return;
  }
  if (commandCount == 0) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"No drawing loaded\"}");
    return;
  }

  enableDrivers();
  robotState = DRAWING;
  currentCommand = 0;
  activeMove = false;
  motionPhase = MOTION_NONE;
  Serial.println("===== DRAWING STARTED =====");

  JsonDocument response;
  response["status"] = "started";
  sendJson(200, response);
}

void handlePause() {
  addCORS();
  if (robotState == DRAWING) {
    robotState = PAUSED;
    Serial.println("Drawing paused.");
  }
  server.send(200, "application/json", "{\"status\":\"paused\"}");
}

void handleResume() {
  addCORS();
  if (emergencyStopLatched || robotState == ERROR_STATE) {
    server.send(423, "application/json", "{\"status\":\"error\",\"message\":\"Emergency stop active. Use RESET after inspection.\"}");
    return;
  }
  if (robotState == PAUSED) {
    enableDrivers();
    robotState = DRAWING;
    Serial.println("Drawing resumed.");
  }
  server.send(200, "application/json", "{\"status\":\"resumed\"}");
}

void handleStop() {
  addCORS();
  robotState = STOPPED;
  activeMove = false;
  motionPhase = MOTION_NONE;
  leftMotor.setCurrentPosition(leftMotor.currentPosition());
  rightMotor.setCurrentPosition(rightMotor.currentPosition());
  penUp();
  disableDrivers();
  Serial.println("!!! ROBOT STOPPED !!!");
  server.send(200, "application/json", "{\"status\":\"stopped\"}");
}

void handleEmergencyStop() {
  addCORS();
  // Latch E-stop: immediate halt and motor driver shutdown
  emergencyStopLatched = true;
  robotState = ERROR_STATE;
  activeMove = false;
  motionPhase = MOTION_NONE;

  leftMotor.setCurrentPosition(leftMotor.currentPosition());
  rightMotor.setCurrentPosition(rightMotor.currentPosition());
  penUp();
  disableDrivers();

  Serial.println("!!! EMERGENCY STOP LATCHED: MOTION DISABLED !!!");
  server.send(200, "application/json", "{\"status\":\"emergency_stop\",\"latched\":true}");
}

void handleReset() {
  addCORS();
  // Reset clears the software E-stop latch after inspection
  emergencyStopLatched = false;
  commandCount = 0;
  currentCommand = 0;
  activeMove = false;
  motionPhase = MOTION_NONE;
  penWasDownBeforeTurn = false;
  robotX = robotY = robotHeading = 0.0f;
  penUp();
  robotState = IDLE;
  disableDrivers();
  Serial.println("Robot reset. Software origin cleared.");
  server.send(200, "application/json", "{\"status\":\"reset\"}");
}

void handleHome() {
  addCORS();
  // Note: No physical limit switches are installed.
  // This defines the current physical position as software origin (0, 0, 0 rad).
  robotState = IDLE;
  activeMove = false;
  motionPhase = MOTION_NONE;
  leftMotor.setCurrentPosition(0);
  rightMotor.setCurrentPosition(0);
  robotX = robotY = robotHeading = 0.0f;
  penUp();
  Serial.println("Software zero set. Place robot at origin facing +X before sending drawing.");
  server.send(200, "application/json", "{\"status\":\"home_complete\"}");
}

void handlePenUp() {
  addCORS();
  penUp();
  server.send(200, "application/json", "{\"status\":\"pen_up\"}");
}

void handlePenDown() {
  addCORS();
  penDownNow();
  server.send(200, "application/json", "{\"status\":\"pen_down\"}");
}

void handleOptions() {
  addCORS();
  server.send(204);
}

// ======================================================
// Wi-Fi Connection
// ======================================================
void connectWiFi() {
  Serial.println("\nConnecting to Wi-Fi...");
  if (USE_STATIC_IP) {
    if (!WiFi.config(local_IP, gateway, subnet, primaryDNS, secondaryDNS)) {
      Serial.println("Static IP configuration failed.");
    }
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWi-Fi connected!");
  Serial.print("ESP32 IP address: ");
  Serial.println(WiFi.localIP());
}

// ======================================================
// SETUP
// ======================================================
void setup() {
  Serial.begin(115200);
  delay(800);

  pinMode(DRIVER_ENABLE_PIN, OUTPUT);
  digitalWrite(DRIVER_ENABLE_PIN, DRIVER_DISABLED);

  leftMotor.setMaxSpeed(MAX_SPEED_STEPS);
  rightMotor.setMaxSpeed(MAX_SPEED_STEPS);
  leftMotor.setAcceleration(ACCELERATION_STEPS);
  rightMotor.setAcceleration(ACCELERATION_STEPS);
  leftMotor.setMinPulseWidth(3);
  rightMotor.setMinPulseWidth(3);
  leftMotor.setCurrentPosition(0);
  rightMotor.setCurrentPosition(0);

  penServo.setPeriodHertz(50);
  penServo.attach(SERVO_PIN, 500, 2400);
  penUp();

  connectWiFi();

  // Register API endpoints
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/draw", HTTP_POST, handleDraw);
  server.on("/start", HTTP_POST, handleStart);
  server.on("/pause", HTTP_POST, handlePause);
  server.on("/resume", HTTP_POST, handleResume);
  server.on("/stop", HTTP_POST, handleStop);
  server.on("/estop", HTTP_POST, handleEmergencyStop);
  server.on("/reset", HTTP_POST, handleReset);
  server.on("/home", HTTP_POST, handleHome);
  server.on("/pen/up", HTTP_POST, handlePenUp);
  server.on("/pen/down", HTTP_POST, handlePenDown);

  server.on("/", HTTP_OPTIONS, handleOptions);
  server.on("/status", HTTP_OPTIONS, handleOptions);
  server.on("/draw", HTTP_OPTIONS, handleOptions);
  server.on("/start", HTTP_OPTIONS, handleOptions);
  server.on("/pause", HTTP_OPTIONS, handleOptions);
  server.on("/resume", HTTP_OPTIONS, handleOptions);
  server.on("/stop", HTTP_OPTIONS, handleOptions);
  server.on("/estop", HTTP_OPTIONS, handleOptions);
  server.on("/reset", HTTP_OPTIONS, handleOptions);
  server.on("/home", HTTP_OPTIONS, handleOptions);
  server.on("/pen/up", HTTP_OPTIONS, handleOptions);
  server.on("/pen/down", HTTP_OPTIONS, handleOptions);

  server.begin();
  Serial.println("HTTP server started.");
  Serial.println("Drawing Robot Firmware Ready.");
}

// ======================================================
// MAIN LOOP (Non-blocking: steppers + HTTP server)
// ======================================================
void loop() {
  server.handleClient();
  if (!emergencyStopLatched) {
    processDrawing();
  }
  yield();
}
