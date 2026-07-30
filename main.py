"""
Serial → Keyboard
Reads text from a serial port (9600, 8, N, 1) and replays it as keyboard strokes.
The device always outputs UPPERCASE; optionally convert to lowercase.
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

import serial
import serial.tools.list_ports


# ---------------------------------------------------------------------------
# Keyboard backends
# ---------------------------------------------------------------------------

class _PynputKeyboard:
    """Works on X11, XWayland, Windows, macOS."""
    def __init__(self) -> None:
        import pynput.keyboard as _kb
        self._ctrl = _kb.Controller()

    def type_char(self, ch: str) -> None:
        self._ctrl.type(ch)

    def close(self) -> None:
        pass


# evdev keymap: char → (KEY_code, needs_shift).  US QWERTY layout.
_EVDEV_MAP: dict[str, tuple[int, bool]] = {}


def _build_evdev_map() -> None:
    if _EVDEV_MAP:
        return
    from evdev import ecodes as e  # type: ignore
    letters = "abcdefghijklmnopqrstuvwxyz"
    keycodes = [
        e.KEY_A, e.KEY_B, e.KEY_C, e.KEY_D, e.KEY_E, e.KEY_F, e.KEY_G,
        e.KEY_H, e.KEY_I, e.KEY_J, e.KEY_K, e.KEY_L, e.KEY_M, e.KEY_N,
        e.KEY_O, e.KEY_P, e.KEY_Q, e.KEY_R, e.KEY_S, e.KEY_T, e.KEY_U,
        e.KEY_V, e.KEY_W, e.KEY_X, e.KEY_Y, e.KEY_Z,
    ]
    for ch, kc in zip(letters, keycodes):
        _EVDEV_MAP[ch]       = (kc, False)  # lowercase
        _EVDEV_MAP[ch.upper()] = (kc, True)  # uppercase → shift
    for digit, kc in zip("0123456789",
                          [e.KEY_0, e.KEY_1, e.KEY_2, e.KEY_3, e.KEY_4,
                           e.KEY_5, e.KEY_6, e.KEY_7, e.KEY_8, e.KEY_9]):
        _EVDEV_MAP[digit] = (kc, False)
    _EVDEV_MAP.update({
        ' ':  (e.KEY_SPACE,       False),
        '\n': (e.KEY_ENTER,       False),
        '\t': (e.KEY_TAB,         False),
        '.':  (e.KEY_DOT,         False),
        ',':  (e.KEY_COMMA,       False),
        '-':  (e.KEY_MINUS,       False),
        '=':  (e.KEY_EQUAL,       False),
        '/':  (e.KEY_SLASH,       False),
        ';':  (e.KEY_SEMICOLON,   False),
        "'":  (e.KEY_APOSTROPHE,  False),
        '[':  (e.KEY_LEFTBRACE,   False),
        ']':  (e.KEY_RIGHTBRACE,  False),
        '\\': (e.KEY_BACKSLASH,   False),
        '`':  (e.KEY_GRAVE,       False),
        '!':  (e.KEY_1,           True),
        '@':  (e.KEY_2,           True),
        '#':  (e.KEY_3,           True),
        '$':  (e.KEY_4,           True),
        '%':  (e.KEY_5,           True),
        '^':  (e.KEY_6,           True),
        '&':  (e.KEY_7,           True),
        '*':  (e.KEY_8,           True),
        '(':  (e.KEY_9,           True),
        ')':  (e.KEY_0,           True),
        '_':  (e.KEY_MINUS,       True),
        '+':  (e.KEY_EQUAL,       True),
        '?':  (e.KEY_SLASH,       True),
        ':':  (e.KEY_SEMICOLON,   True),
        '"':  (e.KEY_APOSTROPHE,  True),
        '<':  (e.KEY_COMMA,       True),
        '>':  (e.KEY_DOT,         True),
        '{':  (e.KEY_LEFTBRACE,   True),
        '}':  (e.KEY_RIGHTBRACE,  True),
        '|':  (e.KEY_BACKSLASH,   True),
        '~':  (e.KEY_GRAVE,       True),
    })


class _EvdevKeyboard:
    """Works on Wayland (and X11) via Linux uinput virtual device.
    Requires the user to be in the 'input' group or a udev rule for /dev/uinput.
    """
    def __init__(self) -> None:
        from evdev import UInput, ecodes as e  # type: ignore
        _build_evdev_map()
        keys = {kc for (kc, _) in _EVDEV_MAP.values()} | {e.KEY_LEFTSHIFT}
        self._ui = UInput({e.EV_KEY: sorted(keys)}, name="serial-keyboard")
        self._e  = e

    def type_char(self, ch: str) -> None:
        entry = _EVDEV_MAP.get(ch)
        if entry is None:
            return
        kc, shift = entry
        ev = self._e
        if shift:
            self._ui.write(ev.EV_KEY, ev.KEY_LEFTSHIFT, 1)
        self._ui.write(ev.EV_KEY, kc, 1)
        self._ui.write(ev.EV_KEY, kc, 0)
        if shift:
            self._ui.write(ev.EV_KEY, ev.KEY_LEFTSHIFT, 0)
        self._ui.syn()

    def close(self) -> None:
        self._ui.close()


def _make_keyboard() -> tuple[object, str]:
    """Return (backend, description).  Auto-detects Wayland vs X11."""
    if sys.platform == "linux" and os.environ.get("WAYLAND_DISPLAY"):
        try:
            return _EvdevKeyboard(), "evdev/uinput"
        except PermissionError:
            raise RuntimeError(
                "Cannot open /dev/uinput.\n"
                "Run once:  sudo usermod -aG input $USER\n"
                "Then log out and back in, or reboot."
            )
        except ImportError:
            pass  # evdev not installed — fall through to pynput
    return _PynputKeyboard(), "pynput"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Serial → Keyboard")
        self.root.resizable(False, False)

        self._serial: serial.Serial | None = None
        self._running = False
        self._log_q: queue.Queue[str] = queue.Queue()

        try:
            self._kb, kb_info = _make_keyboard()
        except RuntimeError as exc:
            self._kb = None
            kb_info   = f"ERROR: {exc}"

        self._build_ui(kb_info)
        self._refresh_ports()
        self._poll()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self, kb_info: str = "") -> None:
        BG        = "#111111"
        BLUE      = "#6699ff"
        TITLE_RED = "#ff3300"
        SUBTITLE  = "#ff6633"
        BTN_BG    = "#cccccc"
        BTN_FG    = "#111111"

        self.root.configure(bg=BG)
        self.root.title("Morse Academy – CW decoder")

        # Outer padding frame
        outer = tk.Frame(self.root, bg=BG, padx=10, pady=10)
        outer.pack(fill="both", expand=True)

        # -- Title --
        tk.Label(outer, text="Morse Academy",
                 bg=BG, fg=TITLE_RED,
                 font=("Arial", 26, "bold")).pack()
        tk.Label(outer, text="CW decoder",
                 bg=BG, fg=SUBTITLE,
                 font=("Arial", 21)).pack()

        # -- Text display --
        self._log = tk.Text(
            outer, width=50, height=8,
            bg=BLUE, fg="white",
            font=("Arial", 28), wrap="word",
            relief="flat", bd=0,
            state="disabled",
            insertbackground="white",
        )
        self._log.pack(fill="both", expand=False, pady=(8, 8))

        # -- Bottom control row --
        ctrl = tk.Frame(outer, bg=BG)
        ctrl.pack(fill="x")

        # Shared font for all controls in the row — drives uniform height
        CTRL_FONT = ("Arial", 10)
        BTN_PAD   = {"pady": 4, "ipady": 2}

        # Port combobox
        self._port_var = tk.StringVar()
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Port.TCombobox",
                         fieldbackground=BTN_BG, background=BTN_BG,
                         foreground=BTN_FG, arrowcolor=BTN_FG,
                         font=CTRL_FONT, padding=(4, 4))
        self._port_cb = ttk.Combobox(ctrl, textvariable=self._port_var,
                                     width=12, state="readonly",
                                     font=CTRL_FONT,
                                     style="Port.TCombobox")
        self._port_cb.pack(side="left", padx=(0, 4))

        # Refresh button
        tk.Button(ctrl, text="Refresh", width=6,
                  bg=BTN_BG, fg=BTN_FG,
                  relief="raised", bd=2,
                  font=CTRL_FONT,
                  command=self._refresh_ports).pack(side="left", padx=(0, 4), **BTN_PAD)

        # Connect button
        self._btn = tk.Button(ctrl, text="Connect", width=8,
                              bg=BTN_BG, fg=BTN_FG,
                              relief="raised", bd=2,
                              font=CTRL_FONT,
                              command=self._toggle)
        self._btn.configure(takefocus=False)
        self._btn.pack(side="left", padx=(0, 4), **BTN_PAD)

        # Clear button
        tk.Button(ctrl, text="Clear", width=6,
                  bg=BTN_BG, fg=BTN_FG,
                  relief="raised", bd=2,
                  font=CTRL_FONT,
                  command=self._clear_log).pack(side="left", **BTN_PAD)

        # -- Options row --
        opts = tk.Frame(outer, bg=BG)
        opts.pack(fill="x", pady=(6, 0))

        self._lower_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="Convert CAPS → lowercase",
                       variable=self._lower_var,
                       bg=BG, fg="#aaaaaa",
                       selectcolor=BG,
                       activebackground=BG, activeforeground="#cccccc").pack(side="left")

        # -- Status --
        self._status_var = tk.StringVar(value="Disconnected")
        tk.Label(opts, textvariable=self._status_var,
                 bg=BG, fg="#888888",
                 font=("Arial", 9)).pack(side="right")

    # --------------------------------------------------------- Port helpers --

    def _refresh_ports(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._port_cb["values"] = ports
        if ports:
            self._port_cb.current(0)

    # ------------------------------------------------- Connect / disconnect --

    def _toggle(self) -> None:
        if self._running:
            self._disconnect(lost=False)
        else:
            self._connect()

    def _connect(self) -> None:
        port = self._port_var.get()
        if not port:
            self._status_var.set("No port selected.")
            return
        try:
            # Build the Serial object WITHOUT opening it yet (port=None).
            # Setting dtr/rts BEFORE open prevents the brief DTR pulse that
            # resets Arduino (and other devices that watch that line).
            s = serial.Serial()
            s.port     = port
            s.baudrate = 9600
            s.bytesize = serial.EIGHTBITS
            s.parity   = serial.PARITY_NONE
            s.stopbits = serial.STOPBITS_ONE
            s.timeout  = 1
            s.rtscts   = False
            s.dsrdtr   = False
            s.xonxoff  = False
            s.open()

            # Disable HUPCL (Hang Up on CLose) — this is what minicom does.
            # Without it, when the Arduino resets and the USB-serial chip
            # briefly glitches, the kernel drops DTR which resets the Arduino
            # again, creating an infinite reset loop.
            if sys.platform != "win32":
                import termios
                fd    = s.fileno()
                attrs = termios.tcgetattr(fd)
                attrs[2] &= ~termios.HUPCL  # c_cflag: clear hang-up-on-close
                termios.tcsetattr(fd, termios.TCSANOW, attrs)

            self._serial = s
        except serial.SerialException as exc:
            self._status_var.set(f"Error: {exc}")
            return

        self._running = True
        self._btn.config(text="Disconnect")
        self._status_var.set(f"Connected  {port}  9600,8,N,1")
        self.root.focus_set()   # move focus away from button so Enter won't trigger it
        threading.Thread(target=self._reader, daemon=True).start()

    def _disconnect(self, *, lost: bool) -> None:
        """Clean up serial connection. Must be called from the main thread."""
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self._btn.config(text="Connect")
        self._status_var.set(
            "Connection lost." if lost else "Disconnected."
        )

    # --------------------------------------------------- Background reader --

    def _reader(self) -> None:
        """Runs in a daemon thread; reads bytes, types them, logs them."""
        # Keep a local reference so closing self._serial from the main thread
        # doesn't cause a NoneType error mid-read.
        port = self._serial
        assert port is not None

        while self._running:
            try:
                raw = port.read(1)
            except Exception as exc:
                if self._running:
                    self._log_q.put(f"\n[disconnected: {type(exc).__name__}: {exc}]\n")
                    self._running = False
                break

            if not raw:
                continue  # read timeout — loop again

            if raw == b'':
                # clean EOF — device closed the connection
                self._log_q.put("\n[device closed connection]\n")
                self._running = False
                break

            ch = raw.decode("ascii", errors="replace")
            if ch == "\r":
                continue  # skip CR — \n handles newlines; \r would double-enter
            if self._lower_var.get():
                ch = ch.lower()

            try:
                self._kb.type_char(ch)
            except Exception as exc:
                self._log_q.put(f"\n[keyboard error: {type(exc).__name__}: {exc}]\n")

            self._log_q.put(ch)

    # ----------------------------------------- Main-thread log / UI poll --

    def _poll(self) -> None:
        # Detect a lost connection flagged by the reader thread.
        if self._serial is not None and not self._running:
            self._disconnect(lost=True)

        # Drain the log queue.
        try:
            while True:
                text = self._log_q.get_nowait()
                self._log.config(state="normal")
                self._log.insert("end", text)
                self._log.see("end")
                self._log.config(state="disabled")
        except queue.Empty:
            pass

        self.root.after(40, self._poll)

    def _clear_log(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")


# ---------------------------------------------------------------------------

def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
