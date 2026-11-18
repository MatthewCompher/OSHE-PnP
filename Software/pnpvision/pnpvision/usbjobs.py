"""Load job files from an SD card (in a USB card reader) or a USB stick: no network needed.

    python -m pnpvision import-jobs                  # find the card, mount it read-only, copy, unmount
    python -m pnpvision import-jobs --device /dev/sda1
    python -m pnpvision import-jobs --from /some/folder   # no mounting (tests, a folder already there)

The touchscreen Job page button "Load jobs from SD/USB" runs this through the PNP_IMPORT_JOBS macro
(Software/Klipper/pnp_hmi.cfg -> scripts/pnp_cmd.sh -> pnpvision.relay).

Rules:
  * Only USB storage is looked at (/dev/disk/by-id/usb-*): never the Pi's own boot card (mmcblk0).
  * The card is mounted READ-ONLY and unmounted at the end: it can be pulled out at any time.
  * *.job.json files from the card's top folder and its first-level folders are copied into jobs/.
    Each must be valid JSON with a "placements" list, under 5 MB, and have a plain name (letters,
    digits, space, _ . -) so RUN_JOB JOB=... can name it.
  * A job already on the Pi is never replaced: if the card's file has the same name but different
    content it is saved as <name>-usb.job.json (a later import replaces that -usb copy). This keeps
    the job files tracked in git untouched, so `git pull` on the Pi keeps working.
"""
import json
import os
import re
import subprocess

MOUNT_POINT = "/mnt/pnp_usb"
BY_ID = "/dev/disk/by-id"
SYS_BLOCK = "/sys/class/block"
SUFFIX = ".job.json"
MAX_BYTES = 5_000_000
NAME_OK = re.compile(r"^[A-Za-z0-9 _.\-]+\.job\.json$")
SKIP_DIRS = {"System Volume Information", "LOST.DIR"}


class UsbError(RuntimeError):
    pass


# -- finding the card ------------------------------------------------------------------------------
def _size(dev, sys_block):
    """Sectors of a block device (0 = card reader with no card in it); -1 if unknown."""
    try:
        with open(os.path.join(sys_block, os.path.basename(dev), "size")) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return -1


def find_devices(by_id=BY_ID, sys_block=SYS_BLOCK):
    """USB storage to try, e.g. ['/dev/sda1'], and how many USB disks had no card in them.
    A disk with partitions -> its partitions; a disk without a partition table -> the disk."""
    try:
        names = sorted(os.listdir(by_id))
    except OSError:
        return [], 0
    disks = {}
    for n in names:
        if not n.startswith("usb-"):
            continue
        base, sep, part = n.rpartition("-part")
        if sep and part.isdigit():
            disks.setdefault(base, {"disk": None, "parts": []})["parts"].append(n)
        else:
            disks.setdefault(n, {"disk": None, "parts": []})["disk"] = n
    devs, empty = [], 0
    for base in sorted(disks):
        d = disks[base]
        if d["parts"]:
            devs += [os.path.realpath(os.path.join(by_id, p)) for p in d["parts"]]
        elif d["disk"]:
            dev = os.path.realpath(os.path.join(by_id, d["disk"]))
            if _size(dev, sys_block) == 0:
                empty += 1
            else:
                devs.append(dev)
    return devs, empty


def _mounts(mounts_file):
    """[(device, mount point)] from /proc/mounts."""
    try:
        with open(mounts_file) as f:
            rows = [ln.split() for ln in f]
    except OSError:
        return []
    return [(r[0], r[1].replace("\\040", " ")) for r in rows if len(r) >= 2]


# -- copying ---------------------------------------------------------------------------------------
def candidates(src):
    """*.json in src and in its first-level folders (not hidden/system folders). Job files are
    normally *.job.json; a plain *.json is kept too (Windows save dialogs can drop the ".job" part)
    and import_jobs decides from its contents."""
    out = []
    try:
        entries = sorted(os.listdir(src))
    except OSError as e:
        raise UsbError(f"can't read {src}: {e}")
    folders = [src] + [os.path.join(src, n) for n in entries
                       if not n.startswith((".", "$")) and n not in SKIP_DIRS
                       and os.path.isdir(os.path.join(src, n))]
    for folder in folders:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        out += [os.path.join(folder, n) for n in names
                if n.lower().endswith(".json") and not n.startswith(".")   # macOS leaves ._name files
                and os.path.isfile(os.path.join(folder, n))]
    return out


def job_name(name):
    """File name in jobs/: 'X.job.json' stays, 'X.json' -> 'X.job.json'."""
    if name.lower().endswith(SUFFIX):
        return name[:-len(SUFFIX)] + SUFFIX
    return name[:-len(".json")] + SUFFIX


def _problem(path, data, name=None):
    """Why this file can't be a job (None if it can)."""
    if not NAME_OK.match(name or os.path.basename(path)):
        return "name may only use letters, digits, space, _ . -"
    return _not_a_job(data)


def _not_a_job(data):
    try:
        job = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        return f"not a valid job file ({e.__class__.__name__})"
    if not isinstance(job, dict) or not isinstance(job.get("placements"), list):
        return "no placements list (not a job file?)"
    return None


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def import_jobs(src, jobs_dir):
    """Copy the job files found in src into jobs_dir. Returns [(file name in jobs_dir, status)],
    status = 'new' | 'updated' | 'already there' | 'skipped: why'."""
    os.makedirs(jobs_dir, exist_ok=True)
    out, seen = [], set()
    for path in candidates(src):
        orig = os.path.basename(path)
        plain = not orig.lower().endswith(SUFFIX)          # X.json: only if it really is a job
        name = job_name(orig)
        if name in seen:
            out.append((name, "skipped: same name in two folders"))
            continue
        seen.add(name)
        try:
            if os.path.getsize(path) > MAX_BYTES:
                out.append((name, "skipped: bigger than 5 MB"))
                continue
            data = _read(path)
        except OSError as e:
            out.append((name, f"skipped: can't read ({e.strerror or e})"))
            continue
        if plain and _not_a_job(data):
            continue                                          # some other .json on the stick: ignore
        why = _problem(path, data, name)
        if why:
            out.append((name, "skipped: " + why))
            continue
        dest = os.path.join(jobs_dir, name)
        if os.path.exists(dest) and _read(dest) != data:          # never replace a job on the Pi
            dest = os.path.join(jobs_dir, name[:-len(SUFFIX)] + "-usb" + SUFFIX)
        if os.path.exists(dest) and _read(dest) == data:
            out.append((os.path.basename(dest), "already there"))
            continue
        status = "updated" if os.path.exists(dest) else "new"
        tmp = dest + ".tmp"                                       # the Job page never sees half a file
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        out.append((os.path.basename(dest), status))
    return out


def summary(results):
    """One short line for the touchscreen."""
    stem = lambda n: n[:-len(SUFFIX)] if n.endswith(SUFFIX) else n
    got = [stem(n) for n, s in results if s in ("new", "updated")]
    same = sum(1 for _, s in results if s == "already there")
    bad = sum(1 for _, s in results if s.startswith("skipped"))
    if not results:
        return "no job files (*.job.json) on the card"
    parts = [f"loaded {len(got)} job{'s' if len(got) != 1 else ''}" + (f" ({', '.join(got)})" if got else "")]
    if same:
        parts.append(f"{same} already there")
    if bad:
        parts.append(f"{bad} skipped (see console)")
    return ", ".join(parts)


# -- mount, copy, unmount --------------------------------------------------------------------------
def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def import_from_device(jobs_dir, device=None, run=_run, mount_point=MOUNT_POINT, log=print,
                       mounts_file="/proc/mounts", by_id=BY_ID, sys_block=SYS_BLOCK):
    """Find the card (or use device), mount it read-only, import, unmount. Returns the results
    of import_jobs over every readable partition. Raises UsbError if nothing could be read."""
    if device:
        devs, empty = [device], 0
    else:
        devs, empty = find_devices(by_id, sys_block)
    if not devs:
        raise UsbError("card reader found, but no card in it" if empty
                       else "no SD card / USB stick found: plug in the card reader with the card in it")
    results, errors, read_any = [], [], False
    for dev in devs:
        log(f"reading {dev}")
        already = [mp for d, mp in _mounts(mounts_file) if os.path.realpath(d) == os.path.realpath(dev)]
        if already:                                              # mounted by someone else: just read it
            results += import_jobs(already[0], jobs_dir)
            read_any = True
            continue
        if any(mp == mount_point for _, mp in _mounts(mounts_file)):
            run(["sudo", "-n", "umount", mount_point])           # left over from an interrupted import
        run(["sudo", "-n", "mkdir", "-p", mount_point])
        r = run(["sudo", "-n", "mount", "-o", "ro,nosuid,nodev,noexec", dev, mount_point])
        if r.returncode:
            errors.append(f"{dev}: {' '.join((r.stderr or r.stdout or 'mount failed').split())}")
            continue
        try:
            results += import_jobs(mount_point, jobs_dir)
            read_any = True
        finally:
            u = run(["sudo", "-n", "umount", mount_point])
            if u.returncode:
                log(f"warning: could not unmount {dev}: {(u.stderr or '').strip()}")
    if not read_any:
        raise UsbError("could not read the card: " + "; ".join(errors))
    return results
