"""Slice one plate: check it, resolve heights, choose the placement order.

Errors stop slicing (no job file). Warnings are shown but don't stop it.

Placement order (JOB_FORMAT.md: file order = placement order, lowest first):
  1. by height, lowest first, so the nozzle never meets a part already placed
     that is taller than the one it is carrying;
  2. parts of the same height and package together (one feeder at a time),
     smaller packages first;
  3. within a package, a short path: nearest unplaced part next, starting
     from where the previous group ended.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .alignment import AlignCandidate, AlignPick, auto_pick, candidates, name_picks, spread
from .board import Board
from .heights import resolve_height
from .plate import ORIGIN_OFFSET_WARN_MM, JobPart, Plate
from .project import ProjectSettings

EDGE_WARN_MM = 0.5  # pick point this close to the board edge -> warning


@dataclass
class Issue:
    level: str          # "error" | "warning"
    message: str
    refs: list[str] = field(default_factory=list)

    @property
    def is_error(self) -> bool:
        return self.level == "error"


@dataclass
class Placement:
    order: int          # 1-based
    ref: str            # as written to the job (may be auto-numbered)
    part: JobPart
    part_index: int     # index into plate.parts
    height: float | None
    height_source: str
    excluded: bool = False   # un-included in pnpslice (saved per board)

    @property
    def original_ref(self) -> str:
        return self.part.ref

    @property
    def skip(self) -> bool:
        """In the job with "skip": true, not placed: do-not-populate in KiCad, or excluded here."""
        return self.part.dnp or self.excluded

    @property
    def skip_reason(self) -> str:
        return "DNP" if self.part.dnp else ("excluded" if self.excluded else "")


@dataclass
class SliceResult:
    plate: Plate
    placements: list[Placement]
    issues: list[Issue]
    renamed: dict[int, str]            # part index -> auto-numbered ref
    alignment: list[AlignPick] = field(default_factory=list)
    align_candidates: list[AlignCandidate] = field(default_factory=list)
    align_manual: bool = False         # True if the pads were picked by hand

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.is_error]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if not i.is_error]

    @property
    def ok(self) -> bool:
        return not self.errors and bool(self.placements)


def _natural_key(ref: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", ref)]


def _is_unnumbered(ref: str) -> bool:
    return not ref or ref.endswith("?")


def auto_number(parts: list[JobPart]) -> dict[int, str]:
    """New names for parts whose reference is shared or unnumbered.

    'R0805' x30 -> 'R0805_1' .. 'R0805_30', numbered in reading order on this
    plate (rows top to bottom, then left to right). Unique refs are untouched.
    """
    counts = Counter(p.ref for p in parts)
    taken = {p.ref for p in parts if counts[p.ref] == 1 and not _is_unnumbered(p.ref)}
    groups: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(parts):
        if counts[p.ref] > 1 or _is_unnumbered(p.ref):
            base = p.ref.rstrip("?") or "U"
            groups[base].append(i)
    renamed: dict[int, str] = {}
    for base, idxs in sorted(groups.items()):
        idxs.sort(key=lambda i: (-round(parts[i].y * 2) / 2, parts[i].x))  # reading order
        n = 0
        for i in idxs:
            n += 1
            while f"{base}_{n}" in taken:
                n += 1
            renamed[i] = f"{base}_{n}"
            taken.add(renamed[i])
    return renamed


def _body_area(part: JobPart) -> float:
    xs = [p.x for p in part.pads]
    ys = [p.y for p in part.pads]
    pad = max((max(p.w, p.h) for p in part.pads), default=0)
    return (max(xs) - min(xs) + pad) * (max(ys) - min(ys) + pad)


def placement_order(parts: list[JobPart], heights: list[float | None]) -> list[int]:
    """Indices of ``parts`` in placement order (see module docstring)."""
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, p in enumerate(parts):
        groups[(heights[i] if heights[i] is not None else math.inf, p.package)].append(i)

    pkg_area: dict[str, float] = {}
    for i, p in enumerate(parts):
        pkg_area[p.package] = max(pkg_area.get(p.package, 0.0), _body_area(p))

    order: list[int] = []
    here = (0.0, 0.0)
    for (h, pkg) in sorted(groups, key=lambda k: (k[0], pkg_area[k[1]], k[1])):
        left = sorted(groups[(h, pkg)], key=lambda i: _natural_key(parts[i].ref))
        while left:
            j = min(left, key=lambda i: (parts[i].x - here[0]) ** 2 + (parts[i].y - here[1]) ** 2)
            left.remove(j)
            order.append(j)
            here = (parts[j].x, parts[j].y)
    return order


def slice_plate(board: Board, plate: Plate, settings: ProjectSettings | None = None) -> SliceResult:
    settings = settings or ProjectSettings()
    parts = plate.parts
    issues: list[Issue] = []

    excluded = {i for i, p in enumerate(parts) if p.key in settings.excluded and not p.dnp}
    skipped = {i for i, p in enumerate(parts) if p.dnp} | excluded
    if len(skipped) == len(parts):
        if parts:
            msg = (f"Nothing to place on the {plate.side} side: every part is excluded or do-not-populate. "
                   "Include some parts (right-click › Include).")
        else:
            msg = f"There are no SMD parts to place on the {plate.side} side."
        issues.append(Issue("error", msg))
        return SliceResult(plate, [], issues, {})

    # -- references (every ref once, DNP parts included: JOB_FORMAT.md) ---------
    renamed: dict[int, str] = {}
    counts = Counter(p.ref for p in parts)
    dupes = sorted((r for r, n in counts.items() if n > 1), key=_natural_key)
    unnumbered = sorted({p.ref or "(blank)" for p in parts if _is_unnumbered(p.ref)})
    if dupes or unnumbered:
        if settings.auto_number:
            renamed = auto_number(parts)
            issues.append(Issue(
                "warning",
                f"{len(renamed)} part(s) were numbered automatically (e.g. {next(iter(renamed.values()))}). "
                "These names exist only in the job file, not in KiCad. For testing only: "
                "annotate in KiCad for real jobs.",
                sorted({parts[i].ref for i in renamed})))
        else:
            if dupes:
                n = sum(counts[r] for r in dupes)
                issues.append(Issue(
                    "error",
                    f"{n} parts share {len(dupes)} reference(s): {', '.join(dupes[:8])}"
                    f"{'…' if len(dupes) > 8 else ''}. Every part needs its own reference. "
                    "Fix it in KiCad (PCB editor: Tools › Geographical Reannotate), "
                    "or tick “Auto-number duplicate references” for testing.", dupes))
            if unnumbered:
                issues.append(Issue("error", f"Unnumbered reference(s): {', '.join(unnumbered)}. "
                                    "Annotate in KiCad, or tick “Auto-number duplicate references”.",
                                    unnumbered))

    # -- positions ------------------------------------------------------------
    off_board = {i for i, p in enumerate(parts) if not plate.contains(p.x, p.y)}
    outside = [parts[i].ref for i in sorted(off_board - skipped)]
    if outside:
        issues.append(Issue("error", f"Part centre outside the board outline: {', '.join(outside)}. "
                            "Fix it in KiCad, or exclude the part.", outside))
    skip_off_board = sorted(off_board & skipped)
    if skip_off_board:  # every entry must lie on the board (JOB_FORMAT.md), so leave these out
        issues.append(Issue("warning", "Part(s) you won't place are off the board, so they were left out of "
                            "the job file: " + ", ".join(parts[i].ref for i in skip_off_board) + ".",
                            [parts[i].ref for i in skip_off_board]))

    near_edge = []
    for p in parts:
        if p.ref in outside:
            continue
        d = min(p.x, p.y, plate.width - p.x, plate.height - p.y)
        if d < EDGE_WARN_MM and board.outline.is_rectangle:
            near_edge.append(p.ref)
    if near_edge:
        issues.append(Issue("warning", f"Within {EDGE_WARN_MM} mm of the board edge: {', '.join(near_edge)}.",
                            near_edge))

    offset = [p.ref for p in parts if p.origin_offset > ORIGIN_OFFSET_WARN_MM]
    if offset:
        issues.append(Issue(
            "warning",
            f"Footprint origin isn't the pad centre for: {', '.join(offset[:8])}{'…' if len(offset) > 8 else ''}. "
            "These are picked at the pad centre, as JOB_FORMAT.md asks; check that this is the "
            "part's middle.", offset))

    # -- heights --------------------------------------------------------------
    resolved = [resolve_height(p.package, p.footprint.properties, settings.heights) for p in parts]
    include = [i for i in range(len(parts)) if i not in skip_off_board]
    skip_no_height = [i for i in include if i in skipped and resolved[i][0] is None]
    if skip_no_height:
        include = [i for i in include if i not in skip_no_height]
        issues.append(Issue("warning", "Part(s) you won't place have no known height, so they were left out of "
                            "the job file: " + ", ".join(parts[i].ref for i in skip_no_height) + ".",
                            [parts[i].ref for i in skip_no_height]))
    missing = sorted({parts[i].package for i in include if resolved[i][0] is None})
    if missing:
        issues.append(Issue("error", "No height for package(s): " + ", ".join(missing) +
                            ". Set them with “Edit heights…”, or add a Height field to the footprint in KiCad.",
                            missing))
    typical = sorted({parts[i].package for i in include if resolved[i][1] == "typical"})
    if typical:
        issues.append(Issue("warning", f"{len(typical)} package height(s) are typical values, not your parts' "
                            "datasheet values. Check them in “Edit heights…”.", typical))
    dnp = [parts[i].ref for i in include if parts[i].dnp]
    exc = [parts[i].ref for i in include if i in excluded]
    if dnp or exc:
        bits = ([f"{len(dnp)} do-not-populate"] if dnp else []) + ([f"{len(exc)} excluded by you"] if exc else [])
        refs = dnp + exc
        issues.append(Issue("warning", f"Not placed, but kept in the job with \"skip\": true "
                            f"({', '.join(bits)}): {', '.join(refs[:8])}{'…' if len(refs) > 8 else ''}.", refs))

    # -- order ------------------------------------------------------------------
    sub = [parts[i] for i in include]
    order = [include[j] for j in placement_order(sub, [resolved[i][0] for i in include])]
    placements = [
        Placement(order=n, ref=renamed.get(i, parts[i].ref), part=parts[i], part_index=i,
                  height=resolved[i][0], height_source=resolved[i][1], excluded=i in excluded)
        for n, i in enumerate(order, start=1)
    ]

    # -- alignment ----------------------------------------------------------------
    # pads of placed parts get covered from their step on; skipped parts never cover anything
    in_job = {pl.part.footprint.uuid: (pl.order, pl.ref) for pl in placements
              if pl.part.footprint.uuid and not pl.skip}
    cands = candidates(board, plate, in_job)
    picks, manual = _choose_alignment(cands, plate, settings, len(placements), issues)
    issues.sort(key=lambda x: 0 if x.is_error else 1)
    return SliceResult(plate, placements, issues, renamed, alignment=picks,
                       align_candidates=cands, align_manual=manual)


def _choose_alignment(cands: list[AlignCandidate], plate: Plate, settings: ProjectSettings,
                      n_steps: int, issues: list[Issue]) -> tuple[list[AlignPick], bool]:
    tol = settings.align_clearance
    by_key = {c.key: c for c in cands}
    saved = settings.alignment.get(plate.side, [])
    manual = False
    chosen: list[AlignCandidate] = []
    if saved:
        found = [by_key[k] for k in saved if k in by_key]
        if len(found) >= 2:
            chosen, manual = found, True
            if len(found) < len(saved):
                issues.append(Issue("warning", f"{len(saved) - len(found)} alignment pad(s) you picked are no "
                                    "longer on the board; using the ones that are left."))
        elif len(found) == len(saved):
            issues.append(Issue("warning", f"You've picked {len(found)} alignment pad; pick at least 2. "
                                "Until then they're chosen automatically."))
        else:
            issues.append(Issue("warning", "The alignment pads you picked aren't on the board any more, "
                                "so they were chosen automatically."))
    if not chosen:
        chosen = auto_pick(cands, plate.width, plate.height, settings.align_count, tol, n_steps)

    if len(chosen) < 2:
        issues.append(Issue("error", f"Fewer than 2 visible copper pads on the {plate.side} side, so the board "
                            "can't be aligned. Pads need a solder-mask opening on this side."))
        return name_picks(chosen), manual

    picks = name_picks(chosen)
    not_distinct = [p for p in picks if not p.cand.distinct(tol)]
    if not_distinct:
        issues.append(Issue(
            "warning",
            "Alignment pad(s) " + ", ".join(f"{p.name} ({p.cand.label()}, look-alike {p.cand.clearance:.2f} mm away)"
                                             for p in not_distinct) +
            f" have a look-alike pad closer than {tol:g} mm. Vision could lock onto the wrong one. "
            "Pick other pads, add fiducials, or lower the look-alike clearance if the board sits "
            "accurately on the machine.",
            [p.cand.ref for p in not_distinct]))
    s = spread([(p.cand.x, p.cand.y) for p in picks], plate.width, plate.height)
    if s < 0.25:
        issues.append(Issue("warning", "The alignment pads are close together or nearly in a line, so "
                            "rotation and position will be less accurate. Spread them out across the board."))
    covered = [p for p in picks if p.cand.covered_at is not None]
    if covered:
        first = min(p.cand.covered_at for p in covered)
        who = "All alignment pads" if len(covered) == len(picks) else \
            "Alignment pad(s) " + ", ".join(p.name for p in covered)
        issues.append(Issue(
            "warning",
            f"{who} belong to parts in this job and get covered as it runs (first at #{first}). Aligning "
            "again after a stop would need other pads; fiducials on the board fix this for good."))
    return picks, manual