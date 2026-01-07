# Extremely Pedantic Perl Matching

Code snippets for matching Perl's exact syscall behavior when needed for the extremely-pedantic version.

## RC File Checking with stat (like Perl's -r)

Perl's `-r` test uses `stat` and checks mode bits internally. To match this syscall pattern:

```python
import grp
import os
import stat


def _is_readable_by_effective_uid(st: os.stat_result) -> bool:
    """Check if a file is readable by the effective UID, like Perl's -r test.

    This mirrors Perl's -r operator which checks readability based on
    the stat structure's mode bits and the effective UID/GID.
    """
    mode = st.st_mode
    euid = os.geteuid()
    egid = os.getegid()

    # Root can read anything
    if euid == 0:
        return True

    # Check owner permission
    if st.st_uid == euid:
        return bool(mode & stat.S_IRUSR)

    # Check group permission
    if st.st_gid == egid or st.st_gid in os.getgroups():
        return bool(mode & stat.S_IRGRP)

    # Check other permission
    return bool(mode & stat.S_IROTH)


# Usage in get_config_file_options():
for file_path in stowrc_candidate_paths:
    # Check readability like Perl's -r test: stat and check mode bits
    try:
        st = os.stat(file_path)
    except OSError:
        continue
    # Check if readable by effective uid (mirrors Perl's -r behavior)
    if not _is_readable_by_effective_uid(st):
        continue
    # File exists and is readable, now open it
    try:
        with open(file_path, "r") as f:
            # ... read file
```

This produces the same `stat` syscall as Perl's `-r` test before attempting to open the file.
