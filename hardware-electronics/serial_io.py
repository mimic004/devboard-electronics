"""serial_io.py - shared serial plumbing for board_cli.py and probe_client.py.

Three things here are not incidental:

1. **Bluetooth COM ports are excluded from auto-detect**, and more than one
   candidate is an *error* that demands ``--port``. Never a coin flip.

2. **DTR and RTS are deasserted before the port is opened, and reset is opt-in.**
   Many ESP32 boards auto-reset when DTR is asserted. A reset restarts setup and
   can disconnect someone who is mid-configuration, so watching must not disturb
   the device.

3. **``source`` is "hardware" only when a serial port was genuinely opened.**
   There is no flag that fakes it. A recorded transport reports "recorded" and
   cannot be talked out of it, which is what lets the whole harness be tested
   with no board attached without ever producing a result that *looks* measured.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

#: Substrings that mark a COM port as a Bluetooth serial profile rather than a
#: real USB device. These enumerate on Windows whether or not anything is paired,
#: and picking one wastes a long timeout for no reason.
BLUETOOTH_MARKERS = ("bluetooth", "bthenum", "rfcomm", "standard serial over bluetooth")


class SerialUnavailable(RuntimeError):
    """pyserial is not installed."""


class NoPortFound(RuntimeError):
    pass


class AmbiguousPort(RuntimeError):
    def __init__(self, candidates: List[Dict[str, Any]]) -> None:
        self.candidates = candidates
        super().__init__(
            "More than one serial port is a candidate: "
            + ", ".join(c["port"] for c in candidates)
        )


def _pyserial():
    try:
        import serial  # type: ignore
        import serial.tools.list_ports  # type: ignore

        return serial
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SerialUnavailable(
            "pyserial is not installed. Run: "
            ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from exc


def is_bluetooth(name: str, hwid: str) -> bool:
    blob = f"{name} {hwid}".lower()
    return any(m in blob for m in BLUETOOTH_MARKERS)


def list_ports(include_bluetooth: bool = False) -> List[Dict[str, Any]]:
    """Enumerate serial ports. Cross-platform, unlike a WMI query."""
    serial = _pyserial()
    out: List[Dict[str, Any]] = []
    for p in serial.tools.list_ports.comports():
        name = p.description or ""
        hwid = p.hwid or ""
        bt = is_bluetooth(name, hwid)
        if bt and not include_bluetooth:
            continue
        out.append(
            {
                "port": p.device,
                "name": name,
                "hwid": hwid,
                "vid": f"0x{p.vid:04x}" if p.vid is not None else None,
                "pid": f"0x{p.pid:04x}" if p.pid is not None else None,
                "serial_number": p.serial_number,
                "bluetooth": bt,
            }
        )
    return sorted(out, key=lambda c: c["port"])


def pick_port(explicit: Optional[str] = None) -> Tuple[str, List[Dict[str, Any]]]:
    """Choose a port, or refuse to guess.

    Returns ``(port, candidates)``. Raises :class:`AmbiguousPort` when more than
    one plausible device is present - guessing there is how you flash the wrong
    board.
    """
    candidates = list_ports()
    if explicit:
        return explicit, candidates
    if not candidates:
        raise NoPortFound(
            "No non-Bluetooth serial port found. Try a DATA-capable USB cable "
            "first - a charge-only cable enumerates nothing at all - and only "
            "then hold BOOT while tapping RESET."
        )
    if len(candidates) > 1:
        raise AmbiguousPort(candidates)
    return candidates[0]["port"], candidates


# --------------------------------------------------------------------------
# transports
# --------------------------------------------------------------------------


class Transport:
    """A line-oriented channel. ``source`` is the honesty marker."""

    source = "recorded"
    port: Optional[str] = None

    def write_line(self, line: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def read_line(self, timeout: float) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        pass

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class SerialTransport(Transport):
    """A real serial port. This is the ONLY transport that reports 'hardware'."""

    source = "hardware"

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        reset: bool = False,
        read_timeout: float = 1.0,
    ) -> None:
        serial = _pyserial()
        self.port = port
        self._buf = ""
        self.transcript: List[str] = []

        # Construct without opening so DTR/RTS can be deasserted first. Opening
        # with DTR asserted resets many ESP32 boards, and a reset is the one
        # side effect a diagnostic must not have by accident.
        self._ser = serial.Serial()
        self._ser.port = port
        self._ser.baudrate = baud
        self._ser.timeout = read_timeout
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        self._ser.dtr = False
        self._ser.rts = False

        if reset:
            self.pulse_reset()
        time.sleep(0.05)
        self._ser.reset_input_buffer()

    def pulse_reset(self) -> None:
        """Deliberate, opt-in reset. Never done implicitly."""
        self._ser.dtr = False
        self._ser.rts = True
        time.sleep(0.1)
        self._ser.rts = False
        time.sleep(0.4)

    def write_line(self, line: str) -> None:
        self.transcript.append(f"> {line}")
        self._ser.write((line + "\n").encode("utf-8", "replace"))
        self._ser.flush()

    def read_line(self, timeout: float) -> Optional[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                line = line.rstrip("\r")
                self.transcript.append(f"< {line}")
                return line
            chunk = self._ser.read(256)
            if chunk:
                self._buf += chunk.decode("utf-8", "replace")
            else:
                time.sleep(0.01)
        return None

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:  # pragma: no cover - best effort
            pass


class RecordedTransport(Transport):
    """Replays a captured session. Always reports source='recorded'.

    A transcript is a request/response log, which is exactly enough to test a
    parser, a plausibility check and an exit code with no board on the desk.
    """

    source = "recorded"

    def __init__(self, transcript: Dict[str, Any]) -> None:
        self.port = transcript.get("port")
        self._exchanges = list(transcript.get("exchanges", []))
        self._pending: List[str] = list(transcript.get("banner", []))
        self.transcript: List[str] = [f"< {b}" for b in self._pending]

    def write_line(self, line: str) -> None:
        self.transcript.append(f"> {line}")
        for i, ex in enumerate(self._exchanges):
            pattern = ex.get("tx")
            if pattern is None:
                continue
            if line.strip() == pattern.strip() or re.fullmatch(pattern, line.strip()):
                self._pending.extend(ex.get("rx", []))
                self._exchanges.pop(i)
                return
        self._pending.append(f"probe.error unknown-command {line.strip()}")

    def read_line(self, timeout: float) -> Optional[str]:
        if not self._pending:
            return None
        line = self._pending.pop(0)
        self.transcript.append(f"< {line}")
        return line


def load_transcript(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# recorded subprocess output, for the esptool / arduino-cli paths
# --------------------------------------------------------------------------


class RecordedCommands:
    """Replays captured stdout for external tools.

    ``board_cli.py identify --transcript <file>`` uses this so the parser and the
    profile-match logic are testable without a board, without ever claiming a
    hardware source.
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self.entries = list(data.get("commands", []))

    def match(self, argv: List[str]) -> Optional[Tuple[str, str, int]]:
        joined = " ".join(argv)
        for e in self.entries:
            if re.search(e["match"], joined):
                return e.get("stdout", ""), e.get("stderr", ""), int(e.get("returncode", 0))
        return None


def find_arduino_cli() -> Optional[str]:
    """Locate arduino-cli. It is a binary, not a pip package."""
    import shutil

    local = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "arduino-cli", "arduino-cli.exe"
    )
    if os.path.isfile(local):
        return local
    return shutil.which("arduino-cli")
