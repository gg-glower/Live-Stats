import ctypes
import platform
import subprocess
import tkinter as tk

WARN_THRESHOLD = 70.0
HIGH_THRESHOLD = 90.0

GREEN_COLOR = "#3fb950"
YELLOW_COLOR = "#d29922"
RED_COLOR = "#f85149"
DIM_COLOR = "#8b949e"


def hide_console():
    if platform.system() == "Windows":
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)


hide_console()


def color_for_percent(val):
    if val is None:
        return DIM_COLOR
    try:
        num = float(val)
    except (TypeError, ValueError):
        return DIM_COLOR
    if num >= HIGH_THRESHOLD:
        return RED_COLOR
    if num >= WARN_THRESHOLD:
        return YELLOW_COLOR
    return GREEN_COLOR


def get_windows_memory():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(stat)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    total_gb = stat.ullTotalPhys / (1024 ** 3)
    used_gb = (stat.ullTotalPhys - stat.ullAvailPhys) / (1024 ** 3)
    return used_gb, total_gb, float(stat.dwMemoryLoad)


def get_linux_memory():
    meminfo = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = int(parts[1].strip().split()[0])
                meminfo[key] = val
    total_kb = meminfo.get("MemTotal", 1)
    avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    used_kb = total_kb - avail_kb
    percent = (used_kb / total_kb) * 100.0
    return used_kb / (1024 ** 2), total_kb / (1024 ** 2), percent


def get_memory():
    sys_name = platform.system()
    try:
        if sys_name == "Windows":
            return get_windows_memory()
        if sys_name == "Linux":
            return get_linux_memory()
    except Exception:
        pass
    return 0.0, 0.0, 0.0


def get_windows_cpu():
    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_uint32),
            ("dwHighDateTime", ctypes.c_uint32),
        ]

    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )

    def to_int(ft):
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    return to_int(idle), to_int(kernel) + to_int(user)


def get_linux_cpu():
    with open("/proc/stat", "r", encoding="utf-8") as f:
        fields = [int(x) for x in f.readline().split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    total = sum(fields)
    return idle, total


def get_gpu_usage():
    try:
        startupinfo = None
        creationflags = 0
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
            timeout=1,
        )
        raw = output.decode("utf-8").strip().splitlines()[0].strip()
        return max(0.0, min(100.0, float(raw)))
    except Exception:
        return None


def get_uptime_seconds():
    sys_name = platform.system()
    try:
        if sys_name == "Windows":
            return ctypes.windll.kernel32.GetTickCount64() / 1000.0
        if sys_name == "Linux":
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                return float(f.readline().split()[0])
    except Exception:
        pass
    return 0.0


class StatsWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Live Statistics V 0.1.0")
        self.root.geometry("380x215")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d1117")
        self.root.attributes("-topmost", True)

        self.prev_idle = None
        self.prev_total = None

        # Top Bar
        top = tk.Frame(root, bg="#0d1117")
        top.pack(fill="x", padx=12, pady=(8, 4))

        tk.Label(
            top,
            text="Live Statistics",
            font=("Segoe UI", 10, "bold"),
            fg="#58a6ff",
            bg="#0d1117",
        ).pack(side="left")

        tk.Label(
            top,
            text=platform.node(),
            font=("Consolas", 9),
            fg="#8b949e",
            bg="#0d1117",
        ).pack(side="right")

        # Main Panel
        panel = tk.Frame(
            root, bg="#161b22", highlightbackground="#30363d", highlightthickness=1
        )
        panel.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        panel.columnconfigure(1, weight=1)

        self.cpu_var = tk.StringVar(value="0.0%")
        self.gpu_var = tk.StringVar(value="--")
        self.ram_gb_var = tk.StringVar(value="--")
        self.ram_pct_var = tk.StringVar(value="--")
        self.uptime_var = tk.StringVar(value="--")

        self.value_labels = {}

        items = [
            ("CPU Load", "cpu", self.cpu_var, GREEN_COLOR, (6, 5)),
            ("GPU Load", "gpu", self.gpu_var, DIM_COLOR, (5, 5)),
            ("Memory", "memory", self.ram_gb_var, "#58a6ff", (5, 0)),
            ("RAM Load", "ram", self.ram_pct_var, GREEN_COLOR, (0, 5)),
            ("Uptime", "uptime", self.uptime_var, "#e6edf3", (5, 6)),
        ]

        for row, (title, key, var, initial_color, pad_y) in enumerate(items):
            tk.Label(
                panel,
                text=title,
                font=("Segoe UI", 9, "bold"),
                fg="#8b949e",
                bg="#161b22",
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=12, pady=pad_y)

            val_lbl = tk.Label(
                panel,
                textvariable=var,
                font=("Consolas", 10, "bold"),
                fg=initial_color,
                bg="#161b22",
                anchor="e",
            )
            val_lbl.grid(row=row, column=1, sticky="e", padx=12, pady=pad_y)
            self.value_labels[key] = val_lbl

        self.refresh()

    def calc_cpu_percent(self) -> float:
        sys_name = platform.system()
        try:
            if sys_name == "Windows":
                idle, total = get_windows_cpu()
            elif sys_name == "Linux":
                idle, total = get_linux_cpu()
            else:
                return 0.0

            if self.prev_idle is None:
                self.prev_idle, self.prev_total = idle, total
                return 0.0

            diff_idle = idle - self.prev_idle
            diff_total = total - self.prev_total
            self.prev_idle, self.prev_total = idle, total

            if diff_total <= 0:
                return 0.0
            return max(0.0, min(100.0, (1.0 - diff_idle / diff_total) * 100.0))
        except Exception:
            return 0.0

    def format_uptime(self, secs: float) -> str:
        s = int(secs)
        days, rem = divmod(s, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"
        return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

    def refresh(self):
        self.root.attributes("-topmost", True)

        cpu = self.calc_cpu_percent()
        self.cpu_var.set(f"{cpu:.1f}%")
        self.value_labels["cpu"].config(fg=color_for_percent(cpu))

        gpu = get_gpu_usage()
        if gpu is not None:
            self.gpu_var.set(f"{gpu:.1f}%")
            self.value_labels["gpu"].config(fg=color_for_percent(gpu))
        else:
            self.gpu_var.set("N/A")
            self.value_labels["gpu"].config(fg=DIM_COLOR)

        used_gb, total_gb, ram_pct = get_memory()
        self.ram_gb_var.set(f"{used_gb:.1f} / {total_gb:.1f} GB")
        self.ram_pct_var.set(f"{ram_pct:.0f}%")
        self.value_labels["ram"].config(fg=color_for_percent(ram_pct))

        self.uptime_var.set(self.format_uptime(get_uptime_seconds()))

        self.root.after(1000, self.refresh)


if __name__ == "__main__":
    app_root = tk.Tk()
    StatsWindow(app_root)
    app_root.mainloop()