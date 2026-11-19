"""import-jobs (pnpvision/usbjobs.py): finding the USB card, which files are copied and how, and
that the card is always unmounted. Mounting itself is faked (sudo mount only exists on the Pi)."""
import json
import types

import pytest

from pnpvision import usbjobs as U

JOB = {"board": {"name": "Test PCB", "side": "top"}, "placements": [{"ref": "R1"}]}


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)


def test_copies_new_skips_bad_and_never_replaces(tmp_path):
    card, jobs = tmp_path / "card", tmp_path / "jobs"
    _write(card / "A.job.json", JOB)
    _write(card / "exports" / "B board-top.job.json", JOB)          # one folder down: found
    _write(card / "exports" / "deep" / "C.job.json", JOB)           # two down: not looked at
    _write(card / "._A.job.json", "mac junk")                       # macOS AppleDouble: ignored
    _write(card / "System Volume Information" / "D.job.json", JOB)  # system folder: ignored
    _write(card / "bad.job.json", "{not json")
    _write(card / "nolist.job.json", {"board": {}})
    _write(card / "we(ird).job.json", JOB)
    _write(card / "notes.txt", "x")
    _write(jobs / "Existing.job.json", {"placements": [], "v": 1})   # e.g. tracked in git
    _write(card / "Existing.job.json", {"placements": [], "v": 2})

    res = dict(U.import_jobs(str(card), str(jobs)))
    assert res["A.job.json"] == "new"
    assert res["B board-top.job.json"] == "new"
    assert res["Existing-usb.job.json"] == "new"                    # Pi's own file kept
    assert json.loads((jobs / "Existing.job.json").read_text())["v"] == 1
    assert res["bad.job.json"].startswith("skipped")
    assert res["nolist.job.json"].startswith("skipped")
    assert res["we(ird).job.json"].startswith("skipped")
    assert "C.job.json" not in res and "D.job.json" not in res and "._A.job.json" not in res
    assert not list(jobs.glob("*.tmp"))
    assert "loaded 3 jobs" in U.summary(list(res.items()))

    # same card again: nothing changes; an updated export replaces only the -usb copy
    res2 = dict(U.import_jobs(str(card), str(jobs)))
    assert res2["A.job.json"] == "already there" and res2["Existing-usb.job.json"] == "already there"
    _write(card / "Existing.job.json", {"placements": [], "v": 3})
    assert dict(U.import_jobs(str(card), str(jobs)))["Existing-usb.job.json"] == "updated"
    assert json.loads((jobs / "Existing-usb.job.json").read_text())["v"] == 3
    assert json.loads((jobs / "Existing.job.json").read_text())["v"] == 1


def test_summary_lines():
    assert U.summary([]) == "no job files (*.job.json) on the card"
    s = U.summary([("A.job.json", "new"), ("B.job.json", "already there"), ("c.job.json", "skipped: x")])
    assert s == "loaded 1 job (A), 1 already there, 1 skipped (see console)"


def test_find_devices(tmp_path):
    by_id, sysb = tmp_path / "by-id", tmp_path / "sys"
    by_id.mkdir()
    for n in ("usb-Reader_SD-0_0", "usb-Reader_SD-0_0-part1",        # card with a partition
              "usb-Stick-0_0",                                        # stick, no partition table
              "usb-Empty_Reader-0_0",                                 # reader with no card
              "ata-SomeDisk", "mmc-SD32G_0x1234", "mmc-SD32G_0x1234-part2"):  # not USB: ignored
        (by_id / n).write_text("")
    for n, size in (("usb-Stick-0_0", "1000"), ("usb-Empty_Reader-0_0", "0")):
        (sysb / n).mkdir(parents=True)
        (sysb / n / "size").write_text(size)
    devs, empty = U.find_devices(str(by_id), str(sysb))
    names = sorted(d.replace("\\", "/").rsplit("/", 1)[-1] for d in devs)
    assert names == ["usb-Reader_SD-0_0-part1", "usb-Stick-0_0"]
    assert empty == 1


class _FakeSudo:
    """Records sudo commands; 'mount' copies nothing but makes the card folder the mount point."""
    def __init__(self, fail_mount=False):
        self.calls, self.fail_mount = [], fail_mount

    def __call__(self, cmd):
        self.calls.append(cmd[2])
        rc = 1 if (cmd[2] == "mount" and self.fail_mount) else 0
        return types.SimpleNamespace(returncode=rc, stdout="", stderr="wrong fs type" if rc else "")


def test_mount_copy_unmount(tmp_path):
    card, jobs, mounts = tmp_path / "card", tmp_path / "jobs", tmp_path / "mounts"
    _write(card / "A.job.json", JOB)
    mounts.write_text("")
    sudo = _FakeSudo()
    res = U.import_from_device(str(jobs), device="/dev/sda1", run=sudo, mount_point=str(card),
                               log=lambda *a: None, mounts_file=str(mounts))
    assert res == [("A.job.json", "new")]
    assert sudo.calls == ["mkdir", "mount", "umount"]


def test_unmounts_even_if_copy_fails(tmp_path, monkeypatch):
    mounts = tmp_path / "mounts"
    mounts.write_text("")
    sudo = _FakeSudo()
    monkeypatch.setattr(U, "import_jobs", lambda src, dst: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        U.import_from_device(str(tmp_path / "jobs"), device="/dev/sda1", run=sudo,
                             mount_point=str(tmp_path), log=lambda *a: None, mounts_file=str(mounts))
    assert sudo.calls[-1] == "umount"


def test_errors_are_clear(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("")
    empty_by_id = tmp_path / "by-id"
    empty_by_id.mkdir()
    with pytest.raises(U.UsbError, match="no SD card / USB stick found"):
        U.import_from_device(str(tmp_path / "jobs"), by_id=str(empty_by_id), log=lambda *a: None,
                             mounts_file=str(mounts))
    with pytest.raises(U.UsbError, match="could not read the card: /dev/sda1: wrong fs type"):
        U.import_from_device(str(tmp_path / "jobs"), device="/dev/sda1", run=_FakeSudo(fail_mount=True),
                             mount_point=str(tmp_path / "mnt"), log=lambda *a: None, mounts_file=str(mounts))


def test_already_mounted_is_read_in_place(tmp_path):
    card, mounts = tmp_path / "media" / "CARD", tmp_path / "mounts"
    _write(card / "A.job.json", JOB)
    mounts.write_text(f"/dev/sda1 {card} vfat ro 0 0\n")
    sudo = _FakeSudo()
    res = U.import_from_device(str(tmp_path / "jobs"), device="/dev/sda1", run=sudo,
                               log=lambda *a: None, mounts_file=str(mounts))
    assert res == [("A.job.json", "new")] and sudo.calls == []      # no mount, no unmount
