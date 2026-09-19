//! Tie spawned processes to this one's lifetime.
//!
//! The same guarantee the Python version needed, for the same reason:
//! nothing in a process runs when it is killed outright, so without help
//! from the kernel a spawned ExifTool is simply orphaned. Fifteen of them
//! accumulated during one afternoon of testing before this existed.

#[cfg(windows)]
mod imp {
    use std::mem::size_of;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        JobObjectExtendedLimitInformation,
    };
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE};

    /// A job object whose closure terminates everything assigned to it.
    pub struct Guard(HANDLE);

    // The handle is owned solely by this struct and only ever closed once.
    unsafe impl Send for Guard {}
    unsafe impl Sync for Guard {}

    impl Guard {
        pub fn new() -> Option<Self> {
            unsafe {
                let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if job.is_null() {
                    return None;
                }
                let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let ok = SetInformationJobObject(
                    job,
                    JobObjectExtendedLimitInformation,
                    &limits as *const _ as *const _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if ok == 0 {
                    CloseHandle(job);
                    return None;
                }
                Some(Guard(job))
            }
        }

        /// Bind a spawned process, so the kernel kills it with us however
        /// we die.
        pub fn adopt(&self, pid: u32) {
            unsafe {
                let handle = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
                if handle.is_null() {
                    return;
                }
                AssignProcessToJobObject(self.0, handle);
                CloseHandle(handle);
            }
        }
    }

    impl Drop for Guard {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
}

#[cfg(not(windows))]
mod imp {
    /// POSIX has no equivalent that applies: PR_SET_PDEATHSIG is Linux
    /// only, SIGKILL cannot be caught, and ExifTool's -stay_open is
    /// documented to keep reading past end of file, so closing its stdin
    /// does not stop it either. Orderly shutdown does the work, and a
    /// later run reaps what a kill left behind.
    pub struct Guard;

    impl Guard {
        pub fn new() -> Option<Self> {
            Some(Guard)
        }
        pub fn adopt(&self, _pid: u32) {}
    }
}

pub use imp::Guard;
