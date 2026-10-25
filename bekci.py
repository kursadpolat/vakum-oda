"""Windows icin bekci: sunucu.py'yi gizli pencerede calistirir, cokerse 5 sn sonra yeniden baslatir.
Gorev Zamanlayici bunu .venv\\Scripts\\pythonw.exe ile oturum acilisinda calistirir (kurulum/windows-kur.ps1).
Cikti .gizli/sunucu.log'a eklenir (5 MB'yi asinca tarihli ada tasinir, silinmez)."""
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent
LOG = KOK / ".gizli" / "sunucu.log"


def is_nesnesi():
    """Windows Job Object (KILL_ON_JOB_CLOSE): bekci durdurulunca sunucu da kapanir, yetim kalmaz."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("R", "W", "O", "RB", "WB", "OB")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32.CreateJobObjectW.restype = wintypes.HANDLE
    is_ = k32.CreateJobObjectW(None, None)
    bilgi = EXT()
    bilgi.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(wintypes.HANDLE(is_), 9, ctypes.byref(bilgi), ctypes.sizeof(bilgi))
    return k32, is_


def ise_ekle(job, p):
    if not job:
        return
    import ctypes
    from ctypes import wintypes
    k32, is_ = job
    k32.AssignProcessToJobObject(wintypes.HANDLE(is_), wintypes.HANDLE(int(p._handle)))


def main():
    job = is_nesnesi()
    while True:
        try:
            if LOG.exists() and LOG.stat().st_size > 5_000_000:
                LOG.rename(LOG.with_name("sunucu-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"))
        except OSError:
            pass
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} bekci: sunucu baslatiliyor\n")
            f.flush()
            bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            p = subprocess.Popen([sys.executable, "-u", str(KOK / "sunucu.py")], cwd=KOK,
                                 stdout=f, stderr=subprocess.STDOUT, creationflags=bayrak,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            ise_ekle(job, p)
            kod = p.wait()
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} bekci: sunucu cikti (kod {kod}), 5 sn sonra yeniden\n")
        time.sleep(5)


if __name__ == "__main__":
    main()
