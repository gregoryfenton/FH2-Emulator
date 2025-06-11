import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import threading
import time
import json
import os
import requests
import webbrowser
import sys

CONFIG_FILE = 'fh2_config.json'
GITHUB_API_RELEASES = "https://api.github.com/repos/gregoryfenton/FH-2-Emulator/releases/latest"
GITHUB_RAW_CHANGELOG = "https://raw.githubusercontent.com/gregoryfenton/FH-2-Emulator/main/CHANGELOG.md"
GITHUB_RAW_SCRIPT = "https://raw.githubusercontent.com/gregoryfenton/FH-2-Emulator/main/fh2_emulator.py"

APP_NAME = "FH-2 Emulator"
USER_FULL_NAME = "Gregory Fenton"
USER_CALLSIGN = "M0ODZ Greg"

# Default config values - updated version to v4.2
DEFAULT_CONFIG = {
    "version": "v4.2",
    "version_last_seen": "v4.2",
    "port": "",
    "baudrate": 38400,
    "volume": 0,
    "monitor_level": 0,
    "bk_in_enabled": False,
    "window": {
        "main": {"width": 600, "height": 350, "x": 50, "y": 50},
        "log": {"width": 600, "height": 300, "x": 100, "y": 100},
        "changelog": {"width": 600, "height": 400, "x": 150, "y": 150},
        "about": {"width": 400, "height": 200, "x": 200, "y": 200}
    },
    "log_visible": False,
    "buttons": [
        {"label": "1", "command": "PB01;"},
        {"label": "2", "command": "PB02;"},
        {"label": "3", "command": "PB03;"},
        {"label": "4", "command": "PB04;"},
        {"label": "5", "command": "PB05;"},
        {"label": "MEM", "command": ""},
        {"label": "<", "command": "KC14;"},
        {"label": "^", "command": "KC13;"},
        {"label": ">", "command": "KC15;"},
        {"label": "P/B", "command": ""},
        {"label": "v", "command": "KC16;"},
        {"label": "DEC", "command": "FA000140;"}
    ],
    "cat_commands": {
        "Frequency Control": {
            "FA%07d;": "Set VFO A frequency (Hz)",
            "FB%07d;": "Set VFO B frequency (Hz)",
            "FT0;": "Select VFO A",
            "FT1;": "Select VFO B"
        },
        "Mode Control": {
            "MD%02d;": "Set mode (0=LSB,1=USB,2=AM,3=CW,4=FM,5=RY,6=ECSS,7=FM-N,8=DV,9=FM-D,10=FM-W)",
            "MD;": "Get mode"
        },
        "Memory": {
            "LM1%d;": "Recall memory channel %d",
            "MS%d;": "Set memory channel %d",
            "MR;": "Recall memory"
        },
        "Power and Audio": {
            "PC%d;": "Set power level %d",
            "AG0%03d;": "Set AF gain (volume) 0-255"
        },
        "Other": {
            "PB0%d;": "Pushbutton macro %d",
            "KC14;": "Left arrow",
            "KC13;": "Up arrow",
            "KC15;": "Right arrow",
            "KC16;": "Down arrow",
            "BI0;": "Break-In off",
            "BI1;": "Break-In on",
            "ML1;": "Get Monitor Level"
        }
    }
}

class FH2Emulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - {USER_CALLSIGN}")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.serial_port = None
        self.serial_thread = None
        self.stop_thread = False
        self.log_debug_visible = True

        self.config_data = self.load_config()

        # Set window geometry and position
        main_win = self.config_data["window"]["main"]
        self.geometry(f"{main_win['width']}x{main_win['height']}+{main_win['x']}+{main_win['y']}")

        self.create_widgets()
        self.create_menu()
        self.apply_config_to_ui()
        self.populate_serial_ports()
        self.open_serial()

        self.after(1000, self.query_initial_values)

        # Restore log window visibility
        if self.config_data.get("log_visible", False):
            self.show_log_window()
        else:
            self.log_window = None

    def create_widgets(self):
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left slider - Monitor Level
        self.monitor_var = tk.IntVar()
        monitor_frame = ttk.Frame(self.main_frame)
        monitor_frame.grid(row=0, column=0, sticky='ns', padx=(0,10))
        ttk.Label(monitor_frame, text="Monitor Level").pack(pady=(0,5))
        self.monitor_slider = ttk.Scale(monitor_frame, from_=100, to=0, orient='vertical', variable=self.monitor_var,
                                        command=self.on_monitor_slider_change)
        self.monitor_slider.pack(fill=tk.Y)

        # Buttons Frame (3 columns, horizontal then vertical)
        buttons_frame = ttk.Frame(self.main_frame)
        buttons_frame.grid(row=0, column=1, sticky='nsew')

        self.button_vars = []
        self.buttons = []
        btns = self.config_data["buttons"]
        total_buttons = len(btns)
        columns = 3
        rows = (total_buttons + columns - 1) // columns

        for i in range(total_buttons):
            label = btns[i]["label"]
            command = btns[i]["command"]
            var = tk.StringVar(value=label)
            self.button_vars.append(var)
            btn = ttk.Button(buttons_frame, textvariable=var, command=lambda c=command: self.send_command(c))
            btn.grid(row=i // columns, column=i % columns, padx=5, pady=5, sticky="ew")
            btn.bind("<Button-3>", self.on_button_right_click)
            self.buttons.append(btn)

        # Right slider - AF Gain (Volume)
        self.volume_var = tk.IntVar()
        volume_frame = ttk.Frame(self.main_frame)
        volume_frame.grid(row=0, column=2, sticky='ns', padx=(10,0))
        ttk.Label(volume_frame, text="AF Gain (Volume)").pack(pady=(0,5))
        self.volume_slider = ttk.Scale(volume_frame, from_=255, to=0, orient='vertical', variable=self.volume_var,
                                       command=self.on_volume_slider_change)
        self.volume_slider.pack(fill=tk.Y)

        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

        # Break-In checkbox
        self.bk_in_var = tk.BooleanVar()
        self.bk_in_check = ttk.Checkbutton(self.main_frame, text="Break-In (BK-IN)", variable=self.bk_in_var,
                                           command=self.toggle_bk_in)
        self.bk_in_check.grid(row=1, column=1, pady=10)

    def create_menu(self):
        menubar = tk.Menu(self)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # Help menu
        self.help_menu = tk.Menu(menubar, tearoff=0)
        self.show_log_label = tk.StringVar(value="Show Log")
        self.help_menu.add_command(labelvariable=self.show_log_label, command=self.toggle_log_window)
        self.help_menu.add_command(label="Check for Updates", command=self.check_for_updates)
        self.help_menu.add_command(label="View Changelog", command=self.show_changelog_window)
        self.help_menu.add_command(label="About", command=self.show_about_window)
        menubar.add_cascade(label="Help", menu=self.help_menu)

        self.config(menu=menubar)

    def apply_config_to_ui(self):
        self.volume_var.set(self.config_data.get("volume", 0))
        self.monitor_var.set(self.config_data.get("monitor_level", 0))
        self.bk_in_var.set(self.config_data.get("bk_in_enabled", False))

    def populate_serial_ports(self):
        # Optional: you can add a combobox for port selection if desired
        pass

    def open_serial(self):
        port = self.config_data.get("port")
        baudrate = self.config_data.get("baudrate", 38400)
        if port:
            try:
                self.serial_port = serial.Serial(port, baudrate, timeout=0.5)
                self.log(f"Opened serial port {port} at {baudrate} baud.")
                self.stop_thread = False
                self.serial_thread = threading.Thread(target=self.serial_reader_thread, daemon=True)
                self.serial_thread.start()
            except Exception as e:
                self.log(f"Error opening serial port: {e}")
                self.serial_port = None
        else:
            self.log("No serial port configured.")

    def serial_reader_thread(self):
        while not self.stop_thread:
            try:
                if self.serial_port and self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode(errors='ignore').strip()
                    if line:
                        self.handle_serial_line(line)
            except Exception as e:
                self.log(f"Serial read error: {e}")
            time.sleep(0.1)

    def handle_serial_line(self, line):
        self.log(f"Received: {line}")
        # Parse AF Gain response "AG?255;" -> set slider
        if line.startswith("AG?"):
            try:
                val = int(line[3:].strip(";"))
                self.volume_var.set(val)
                self.config_data["volume"] = val
            except:
                pass
        # Parse Monitor Level "ML1xxx" eg ML1025
        elif line.startswith("ML1"):
            try:
                val = int(line[3:])
                if 0 <= val <= 100:
                    self.monitor_var.set(val)
                    self.config_data["monitor_level"] = val
            except:
                pass
        # Parse Break-In status
        elif line.startswith("BI"):
            # BI0 or BI1
            if line[2] == "1":
                self.bk_in_var.set(True)
                self.config_data["bk_in_enabled"] = True
            else:
                self.bk_in_var.set(False)
                self.config_data["bk_in_enabled"] = False

    def send_command(self, command):
        if not command:
            self.log("No command assigned to button.")
            return
        if not self.serial_port or not self.serial_port.is_open:
            self.log("Serial port not open.")
            return
        try:
            self.serial_port.write(command.encode())
            self.log(f"Sent: {command}")
        except Exception as e:
            self.log(f"Error sending command: {e}")

    def on_volume_slider_change(self, val):
        vol = int(float(val))
        self.config_data["volume"] = vol
        self.send_command(f"AG0{vol:03d};")

    def on_monitor_slider_change(self, val):
        level = int(float(val))
        self.config_data["monitor_level"] = level
        self.send_command(f"ML1{level};")

    def toggle_bk_in(self):
        val = self.bk_in_var.get()
        self.config_data["bk_in_enabled"] = val
        cmd = "BI1;" if val else "BI0;"
        self.send_command(cmd)

    def query_initial_values(self):
        self.send_command("AG?;")
        self.send_command("ML1;")
        self.send_command("BI?;")

    def toggle_log_window(self):
        if getattr(self, "log_window", None) and self.log_window.winfo_exists():
            self.hide_log_window()
        else:
            self.show_log_window()

    def show_log_window(self):
        if getattr(self, "log_window", None) and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.show_log_label.set("Hide Log")
            return
        self.log_window = tk.Toplevel(self)
        self.log_window.title(f"{APP_NAME} Log")
        log_win_conf = self.config_data["window"]["log"]
        self.log_window.geometry(f"{log_win_conf['width']}x{log_win_conf['height']}+{log_win_conf['x']}+{log_win_conf['y']}")
        self.log_window.protocol("WM_DELETE_WINDOW", self.hide_log_window)

        self.log_text = scrolledtext.ScrolledText(self.log_window, state='disabled', wrap='word')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.debug_visible = True

        toggle_debug_btn = ttk.Button(self.log_window, text="Toggle Debug/CAT Info", command=self.toggle_debug_visibility)
        toggle_debug_btn.pack(pady=5)

        self.show_log_label.set("Hide Log")
        self.config_data["log_visible"] = True
        self.save_config()

    def hide_log_window(self):
        if getattr(self, "log_window", None):
            self.log_window.withdraw()
        self.show_log_label.set("Show Log")
        self.config_data["log_visible"] = False
        self.save_config()

    def toggle_debug_visibility(self):
        self.log_debug_visible = not self.log_debug_visible
        if self.log_debug_visible:
            self.log("Debug/CAT info shown.")
        else:
            self.log("Debug/CAT info hidden.")

    def log(self, message):
        if getattr(self, "log_text", None):
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state='disabled')
        else:
            print(message)

    def on_close(self):
        self.save_window_geometry()
        self.stop_thread = True
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except:
                pass
        self.save_config()
        self.destroy()

    def save_window_geometry(self):
        geom = self.geometry()
        width, height, x, y = self.parse_geometry(geom)
        self.config_data["window"]["main"].update({"width": width, "height": height, "x": x, "y": y})

        if getattr(self, "log_window", None) and self.log_window.winfo_exists():
            log_geom = self.log_window.geometry()
            lw, lh, lx, ly = self.parse_geometry(log_geom)
            self.config_data["window"]["log"].update({"width": lw, "height": lh, "x": lx, "y": ly})

    def parse_geometry(self, geom):
        try:
            size_part, x_y_part = geom.split('+', 1)
            width, height = map(int, size_part.split('x'))
            x_str, y_str = x_y_part.split('+')
            x, y = int(x_str), int(y_str)
            return width, height, x, y
        except:
            return 600, 350, 50, 50

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                print(f"Failed to load config, using defaults: {e}")
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config_data, f, indent=2)
        except Exception as e:
            self.log(f"Failed to save config: {e}")

    def show_about_window(self):
        if getattr(self, "about_window", None) and self.about_window.winfo_exists():
            self.about_window.deiconify()
            return
        self.about_window = tk.Toplevel(self)
        self.about_window.title(f"About {APP_NAME}")
        about_conf = self.config_data["window"]["about"]
        self.about_window.geometry(f"{about_conf['width']}x{about_conf['height']}+{about_conf['x']}+{about_conf['y']}")
        self.about_window.protocol("WM_DELETE_WINDOW", self.about_window.withdraw)

        ttk.Label(self.about_window, text=f"{APP_NAME}", font=("Arial", 14, "bold")).pack(pady=5)
        ttk.Label(self.about_window, text=f"Author: {USER_FULL_NAME}").pack(pady=5)
        ttk.Label(self.about_window, text=f"Callsign: {USER_CALLSIGN}").pack(pady=5)
        ttk.Label(self.about_window, text="Version: " + self.config_data.get("version", "v4.2")).pack(pady=5)
        ttk.Label(self.about_window, text="A Yaesu FH-2 Remote Emulator").pack(pady=5)

    def check_for_updates(self):
        def do_check():
            try:
                self.log("Checking for updates...")
                r = requests.get(GITHUB_API_RELEASES, timeout=10)
                r.raise_for_status()
                latest = r.json()
                latest_version = latest['tag_name']
                if latest_version != self.config_data.get("version", ""):
                    if messagebox.askyesno("Update Available", f"A new version {latest_version} is available. Download and update?"):
                        self.download_and_update(latest['assets'][0]['browser_download_url'])
                else:
                    messagebox.showinfo("No Update", "You are running the latest version.")
            except Exception as e:
                messagebox.showerror("Update Error", f"Failed to check for updates: {e}")

        threading.Thread(target=do_check, daemon=True).start()

    def download_and_update(self, url):
        try:
            self.log(f"Downloading update from {url}")
            # Implement update download logic here
        except Exception as e:
            self.log(f"Update download failed: {e}")

    def on_button_right_click(self, event):
        btn = event.widget
        idx = self.buttons.index(btn)
        label = self.button_vars[idx].get()
        menu = tk.Menu(self, tearoff=0)

        # Example: show CAT commands grouped
        cat_cmds = self.config_data.get("cat_commands", {})
        for group, cmds in cat_cmds.items():
            submenu = tk.Menu(menu, tearoff=0)
            for cmd, desc in cmds.items():
                submenu.add_command(label=f"{cmd} - {desc}",
                                    command=lambda c=cmd: self.send_command(c))
            menu.add_cascade(label=group, menu=submenu)

        menu.post(event.x_root, event.y_root)

    def show_changelog_window(self):
        if getattr(self, "changelog_window", None) and self.changelog_window.winfo_exists():
            self.changelog_window.deiconify()
            return
        self.changelog_window = tk.Toplevel(self)
        self.changelog_window.title(f"{APP_NAME} Changelog")
        changelog_conf = self.config_data["window"]["changelog"]
        self.changelog_window.geometry(f"{changelog_conf['width']}x{changelog_conf['height']}+{changelog_conf['x']}+{changelog_conf['y']}")
        self.changelog_window.protocol("WM_DELETE_WINDOW", self.changelog_window.withdraw)

        self.changelog_text = scrolledtext.ScrolledText(self.changelog_window, state='disabled', wrap='word')
        self.changelog_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Fetch changelog from GitHub raw
        def fetch_changelog():
            try:
                r = requests.get(GITHUB_RAW_CHANGELOG, timeout=10)
                r.raise_for_status()
                text = r.text
            except Exception as e:
                text = f"Failed to fetch changelog: {e}"

            self.changelog_text.configure(state='normal')
            self.changelog_text.delete(1.0, tk.END)
            self.changelog_text.insert(tk.END, text)
            self.changelog_text.configure(state='disabled')

        threading.Thread(target=fetch_changelog, daemon=True).start()


if __name__ == "__main__":
    app = FH2Emulator()
    app.mainloop()
