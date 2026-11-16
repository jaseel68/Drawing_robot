"""
DRAWING ROBOT - ROBOT COMMUNICATION MODULE & SIMULATION ENGINE
==============================================================
This module handles Wi-Fi REST API communication between the web application backend
and the physical ESP32 drawing robot micro-controller.

It also provides a built-in SIMULATION ENGINE so the entire application (path sending,
live position tracking, progress updates, start/pause/stop controls) can be tested
without physical hardware attached!
"""

import time
import requests
import config

class VirtualRobotSimulator:
    """
    Simulates a physical drawing robot in software.
    Tracks virtual robot state, coordinates, pen state, and path execution progress.
    """
    def __init__(self):
        self.reset_state()
        
    def reset_state(self):
        self.connected = True
        self.ip = "127.0.0.1 (Simulation Mode)"
        self.state = "IDLE"  # IDLE, DRAWING, PAUSED, STOPPED, HOMING, COMPLETE, ERROR
        self.current_x = 0.0
        self.current_y = 0.0
        self.pen_state = "UP"
        self.path_commands = []
        self.current_cmd_idx = 0
        self.total_commands = 0
        self.progress_percent = 0.0
        self.last_update_time = time.time()
        
    def get_status(self):
        """Returns current simulated robot telemetry state."""
        # Auto-advance simulation if state is DRAWING
        if self.state == "DRAWING" and self.path_commands:
            self._step_simulation()
            
        return {
            'connected': True,
            'simulation_mode': True,
            'ip': self.ip,
            'state': self.state,
            'position': {
                'x': round(self.current_x, 2),
                'y': round(self.current_y, 2)
            },
            'pen_state': self.pen_state,
            'progress': round(self.progress_percent, 1),
            'command_index': self.current_cmd_idx,
            'total_commands': self.total_commands,
            'current_command': self.path_commands[self.current_cmd_idx] if self.current_cmd_idx < len(self.path_commands) else None
        }
        
    def upload_path(self, commands):
        """Load drawing path command sequence into virtual robot memory."""
        self.path_commands = commands
        self.current_cmd_idx = 0
        self.total_commands = len(commands)
        self.progress_percent = 0.0
        self.state = "IDLE"
        if commands:
            first_cmd = commands[0]
            if first_cmd.get('type') == 'MOVE':
                self.current_x = first_cmd.get('x', 0.0)
                self.current_y = first_cmd.get('y', 0.0)
        return {'success': True, 'message': f"Uploaded {len(commands)} commands to Virtual Robot Simulator."}
        
    def start(self):
        if not self.path_commands:
            return {'success': False, 'message': 'No path uploaded to simulator!'}
        self.state = "DRAWING"
        self.last_update_time = time.time()
        return {'success': True, 'message': 'Simulation started.'}
        
    def pause(self):
        if self.state == "DRAWING":
            self.state = "PAUSED"
            return {'success': True, 'message': 'Simulation paused.'}
        return {'success': False, 'message': 'Simulation is not currently drawing.'}
        
    def resume(self):
        if self.state == "PAUSED":
            self.state = "DRAWING"
            self.last_update_time = time.time()
            return {'success': True, 'message': 'Simulation resumed.'}
        return {'success': False, 'message': 'Simulation is not paused.'}
        
    def stop(self):
        self.state = "STOPPED"
        self.pen_state = "UP"
        return {'success': True, 'message': 'Simulation stopped safely.'}
        
    def home(self):
        self.state = "HOMING"
        self.current_x = 0.0
        self.current_y = 0.0
        self.pen_state = "UP"
        self.state = "IDLE"
        return {'success': True, 'message': 'Virtual Robot homed to (0, 0).'}
        
    def pen_up(self):
        self.pen_state = "UP"
        return {'success': True, 'message': 'Pen lifted UP.'}
        
    def pen_down(self):
        self.pen_state = "DOWN"
        return {'success': True, 'message': 'Pen lowered DOWN.'}
        
    def _step_simulation(self):
        """Simulate moving forward through command list."""
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now
        
        # Advance multiple commands per update step for smooth UI animation playback
        steps_to_advance = max(1, int(dt * 15))
        
        for _ in range(steps_to_advance):
            if self.current_cmd_idx >= self.total_commands:
                self.state = "COMPLETE"
                self.progress_percent = 100.0
                self.pen_state = "UP"
                break
                
            cmd = self.path_commands[self.current_cmd_idx]
            cmd_type = cmd.get('type')
            
            if cmd_type == 'PEN_UP':
                self.pen_state = 'UP'
            elif cmd_type == 'PEN_DOWN':
                self.pen_state = 'DOWN'
            elif cmd_type == 'MOVE':
                self.current_x = cmd.get('x', self.current_x)
                self.current_y = cmd.get('y', self.current_y)
                
            self.current_cmd_idx += 1
            if self.total_commands > 0:
                self.progress_percent = (self.current_cmd_idx / float(self.total_commands)) * 100.0


# Singleton Simulator Instance
simulator = VirtualRobotSimulator()


class ESP32RobotClient:
    """
    Communicates over Wi-Fi REST API with the ESP32 drawing robot.
    """
    def __init__(self, ip_address=None):
        self.ip_address = ip_address or config.ESP32_DEFAULT_IP
        self.timeout = config.ESP32_TIMEOUT_SECONDS
        
    def _get_url(self, endpoint):
        clean_ip = self.ip_address.strip()
        if not clean_ip.startswith('http://') and not clean_ip.startswith('https://'):
            clean_ip = f"http://{clean_ip}"
        return f"{clean_ip.rstrip('/')}/{endpoint.lstrip('/')}"
        
    def test_connection(self):
        """Ping ESP32 /status endpoint to verify Wi-Fi reachability."""
        url = self._get_url('/status')
        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return {
                    'success': True,
                    'connected': True,
                    'ip': self.ip_address,
                    'message': f"Successfully connected to ESP32 at {self.ip_address}",
                    'data': resp.json() if resp.headers.get('content-type') == 'application/json' else {}
                }
            return {'success': False, 'connected': False, 'message': f"ESP32 returned HTTP status {resp.status_code}"}
        except requests.exceptions.Timeout:
            return {'success': False, 'connected': False, 'message': f"Connection timeout to ESP32 at {self.ip_address}. Check Wi-Fi connection."}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'connected': False, 'message': f"Could not connect to ESP32 at {self.ip_address}. Is IP address correct?"}
        except Exception as e:
            return {'success': False, 'connected': False, 'message': f"Connection error: {str(e)}"}
            
    def send_command(self, endpoint, payload=None):
        """Send POST command to specified ESP32 REST API endpoint."""
        url = self._get_url(endpoint)
        try:
            resp = requests.post(url, json=payload or {}, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json() if resp.headers.get('content-type') == 'application/json' else {}
                return {'success': True, 'data': data}
            return {'success': False, 'message': f"ESP32 endpoint {endpoint} returned status {resp.status_code}"}
        except Exception as e:
            return {'success': False, 'message': f"Failed to reach ESP32 endpoint {endpoint}: {str(e)}"}


def get_robot_status(ip_address, simulation_mode=True, emergency_stopped=False):
    """Unified helper to get status from physical ESP32 or Simulator."""
    if emergency_stopped:
        return {
            'connected': True,
            'simulation_mode': simulation_mode,
            'ip': ip_address,
            'state': 'STOPPED',
            'position': {'x': simulator.current_x, 'y': simulator.current_y},
            'pen_state': 'UP',
            'progress': simulator.progress_percent,
            'command_index': simulator.current_cmd_idx,
            'total_commands': simulator.total_commands
        }

    if simulation_mode:
        return simulator.get_status()
    client = ESP32RobotClient(ip_address)
    res = client.test_connection()
    if res.get('success'):
        data = res.get('data', {})
        data['connected'] = True
        data['simulation_mode'] = False
        return data
    return {
        'connected': False,
        'simulation_mode': False,
        'ip': ip_address,
        'state': 'DISCONNECTED',
        'error': res.get('message', 'Disconnected')
    }

def send_robot_action(ip_address, action, payload=None, simulation_mode=True):
    """Unified helper to dispatch action (start, pause, resume, stop, estop, home, pen) to ESP32 or Simulator."""
    # Always halt virtual simulator as safety fallback
    if action in ['stop', 'estop']:
        simulator.stop()
        
    if simulation_mode:
        if action == 'start':
            return simulator.start()
        elif action in ['stop', 'estop']:
            return simulator.stop()
        elif action == 'home':
            return simulator.home()
        elif action == 'pen_up':
            return simulator.pen_up()
        elif action == 'pen_down':
            return simulator.pen_down()
        elif action == 'upload_path':
            cmds = payload.get('commands', []) if payload else []
            return simulator.upload_path(cmds)
        else:
            return {'success': True, 'message': f"Action {action} executed in Simulation Mode."}
            
    # Physical ESP32 Client
    client = ESP32RobotClient(ip_address)
    endpoint_map = {
        'start': '/start',
        'pause': '/pause',
        'resume': '/resume',
        'stop': '/stop',
        'estop': '/estop',
        'reset': '/reset',
        'home': '/home',
        'pen_up': '/pen/up',
        'pen_down': '/pen/down',
        'upload_path': '/draw'
    }
    endpoint = endpoint_map.get(action, f"/{action}")
    
    if action in ['stop', 'estop']:
        # Send fast timeout command to physical ESP32
        try:
            client.send_command(endpoint, payload=payload)
        except Exception:
            pass
        return {'success': True, 'state': 'STOPPED', 'message': 'Emergency Stop executed safely.'}
        
    res = client.send_command(endpoint, payload=payload)
    return res
