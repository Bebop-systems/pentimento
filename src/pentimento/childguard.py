"""Make sure the ExifTool child dies with us.

`stop()` handles an orderly exit, but nothing in Python runs when the
process is killed outright — task manager, an EDR action, a crash. Without
an operating system guarantee the child is simply orphaned, and they
accumulate: fifteen of them turned up during one afternoon of testing.

Windows has one: a Job Object with KILL_ON_JOB_CLOSE terminates every
assigned process when the last handle to the job closes, which the kernel
does for us however the parent died. POSIX gets a process group, which
lets an orderly shutdown sweep the whole tree.
"""
from __future__ import annotations

import os
import subprocess
import sys

_IS_WINDOWS = os.name == "nt"

# winnt.h
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class ChildGuard:
    """Ties spawned processes to this one's lifetime."""

    def __init__(self) -> None:
        self._job = None
        if _IS_WINDOWS:
            self._job = self._create_job()

    @staticmethod
    def _create_job():
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return None

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in (
                    "ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount",
                    "WriteTransferCount", "OtherTransferCount")]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation",
                     JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return None

            limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limits.BasicLimitInformation.LimitFlags = (
                _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            ok = kernel32.SetInformationJobObject(
                job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits), ctypes.sizeof(limits),
            )
            if not ok:
                kernel32.CloseHandle(job)
                return None
            return job
        except Exception:
            # A missing privilege or an already-assigned job is not worth
            # failing over; orderly shutdown still works.
            return None

    def adopt(self, process: subprocess.Popen) -> None:
        """Bind a spawned process to this one's lifetime."""
        if not _IS_WINDOWS or self._job is None:
            return
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(
                _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, process.pid
            )
            if not handle:
                return
            try:
                kernel32.AssignProcessToJobObject(self._job, handle)
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return

    @staticmethod
    def spawn_kwargs() -> dict:
        """Extra Popen arguments that keep a child quiet and attached."""
        if _IS_WINDOWS:
            # No console window flashing up behind a windowed app, which is
            # both visible to the user and noisy to anything watching
            # process creation.
            return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

        # Deliberately nothing on POSIX. An earlier version passed
        # start_new_session=True, reasoning that its own process group
        # would be tidier. It does the opposite: a new session detaches the
        # child from the parent entirely, so it survives anything that
        # happens to the parent. macOS CI caught it.
        #
        # Staying in the same session means the child keeps the parent's
        # stdin pipe, and ExifTool in -stay_open mode exits when that pipe
        # reaches EOF, which is what happens when the parent dies.
        return {}

    def close(self) -> None:
        if self._job is not None:
            try:
                import ctypes

                ctypes.WinDLL("kernel32").CloseHandle(self._job)
            except Exception:
                pass
            self._job = None
