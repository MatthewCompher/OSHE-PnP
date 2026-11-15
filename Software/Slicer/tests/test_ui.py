"""Smoke test for the window. Skipped if PySide6 isn't installed."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    from pnpslice.ui import theme
    theme.apply(a)
    return a


@pytest.fixture
def window(app, tmp_path):
    from pnpslice.ui.main_window import MainWindow
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings=settings)
    w.show()
    yield w
    w.close()


def test_empty_window(window):
    assert window.plates == []
    assert not window.plate_btns[0].isEnabled()


def test_load_and_switch_plates(window, app, test_pcb_path):
    assert window.load(test_pcb_path)
    app.processEvents()
    assert window.plate_btns[0].text().startswith("Plate 1")
    assert "(92)" in window.plate_btns[0].text()
    assert "(64)" in window.plate_btns[1].text()
    assert window.sidebar.table.rowCount() == 92
    assert len(window.view.items_by_index) == 92
    assert "share" in window.sidebar.problems.item(0).text()  # duplicate references flagged

    window.show_plate(1)
    app.processEvents()
    assert window.sidebar.table.rowCount() == 64
    assert "mirrored" in window.view_note.text()


def test_selection_syncs_table_and_view(window, app, test_pcb_path):
    window.load(test_pcb_path)
    window.show_plate(1)
    idx = next(i for i, p in enumerate(window.plates[1].parts) if p.package.startswith("SOIC"))
    window.view.items_by_index[idx].setSelected(True)
    app.processEvents()
    assert window.sidebar.selected_index() == idx


@pytest.fixture
def board_copy(test_pcb_path, tmp_path):
    """The test board copied to a temp folder, so settings files land there."""
    import shutil
    dst = tmp_path / "board" / "Test PCB.kicad_pcb"
    dst.parent.mkdir()
    shutil.copy(test_pcb_path, dst)
    return str(dst)


def test_slice_blocked_by_duplicates(window, app, board_copy, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    window.load(board_copy)
    window.slice_current()
    assert shown and "share" in shown[0]
    assert window.mode == "prepare" and not window.export_btn.isEnabled()


def test_auto_number_slice_preview_export(window, app, board_copy, tmp_path, monkeypatch):
    import json
    from PySide6.QtWidgets import QFileDialog
    window.load(board_copy)
    window.show_plate(1)
    window.sidebar.auto_number.setChecked(True)       # saves settings next to the board
    assert os.path.isfile(board_copy.replace(".kicad_pcb", ".pnpslice.json"))
    assert window.sidebar.problems.item(0).text().startswith("✔")

    window.slice_current()
    app.processEvents()
    assert window.mode == "preview" and not window.slider_panel.isHidden()
    assert window.export_btn.isEnabled() and window.tab_preview.isEnabled()
    assert window.slider.maximum() == 64
    window.slider.setValue(10)
    states = [it.state for it in window.view.items_by_index]
    assert states.count("placed") == 9 and states.count("current") == 1 and states.count("pending") == 54
    assert "✓" in window.plate_btns[1].text()

    out = tmp_path / "bottom.job.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    window.export_current()
    job = json.loads(out.read_text())
    assert job["board"]["side"] == "bottom" and len(job["placements"]) == 64

    # changing a setting makes the slice out of date
    window.sidebar.auto_number.setChecked(False)
    assert window.mode == "prepare" and not window.sliced


def test_settings_reload_with_board(window, board_copy):
    from pnpslice.project import ProjectSettings
    s = ProjectSettings.load(board_copy)
    s.heights["R_0603_1608Metric"] = 0.6
    s.auto_number = True
    s.save()
    window.load(board_copy)
    assert window.sidebar.auto_number.isChecked()
    assert window.project.heights == {"R_0603_1608Metric": 0.6}


def test_bad_file_shows_message_not_crash(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    bad = tmp_path / "bad.kicad_pcb"
    bad.write_text("(kicad_sch (version 1))")
    assert window.load(str(bad)) is False
    assert shown and "not a KiCad board" in shown[0]


def test_alignment_shown_and_pick_by_hand(window, app, board_copy):
    from pnpslice.project import ProjectSettings
    window.load(board_copy)
    window.show_plate(1)
    assert window.sidebar.align_list.count() == 3
    assert window.sidebar.align_mode.text() == "chosen automatically"
    assert len(window.view.align.picks) == 3

    # pick mode starts from the automatic choice and is saved per side
    window.sidebar.pick_btn.setChecked(True)
    assert window.view.pick_mode and window.view.align.pick_mode
    auto_keys = list(window.project.alignment["bottom"])
    assert len(auto_keys) == 3

    # remove one by "clicking" it, then add a different pad
    window._on_align_pad_clicked(auto_keys[0])
    assert window.project.alignment["bottom"] == auto_keys[1:]
    other = next(c.key for c in window.checks[1].align_candidates if c.key not in auto_keys)
    window._on_align_pad_clicked(other)
    assert other in window.project.alignment["bottom"]
    assert window.sidebar.align_mode.text() == "picked by hand"
    assert ProjectSettings.load(board_copy).alignment["bottom"] == window.project.alignment["bottom"]

    # Auto forgets the picks
    window.sidebar.auto_btn.click()
    assert "bottom" not in window.project.alignment
    assert not window.sidebar.pick_btn.isChecked()


def test_clearance_changes_warning(window, app, board_copy):
    window.load(board_copy)
    window.show_plate(1)
    def lookalike_warning():
        return any("look-alike" in i.message for i in window.checks[1].warnings)
    assert window.sidebar.align_clear.value() == 3.0   # JOB_FORMAT.md default
    assert lookalike_warning()                          # 1206 twins are 2.92 mm apart
    window.sidebar.align_clear.setValue(2.5)
    assert not lookalike_warning()


def _click_part(window, app, idx, button):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    v = window.view
    it = v.items_by_index[idx]
    v.centerOn(it)
    app.processEvents()
    pos = v.mapFromScene(it.sceneBoundingRect().center())
    QTest.mouseClick(v.viewport(), button, Qt.NoModifier, pos)
    app.processEvents()


def test_real_left_click_selects_a_part(window, app, board_copy):
    """Regression: the alignment layer used to swallow clicks on parts."""
    from PySide6.QtCore import Qt
    window.load(board_copy)
    window.show_plate(1)
    window.view.zoom_by(4)
    _click_part(window, app, 5, Qt.LeftButton)
    assert window.view.items_by_index[5].isSelected()
    assert window.sidebar.selected_index() == 5


def test_right_click_on_a_part_asks_for_its_menu(window, app, board_copy):
    from PySide6.QtCore import Qt
    window.load(board_copy)
    window.show_plate(1)
    window.view.zoom_by(4)
    got = []
    window.view.partMenuRequested.disconnect()
    window.view.partMenuRequested.connect(lambda i, p: got.append(i))
    _click_part(window, app, 7, Qt.RightButton)
    assert got == [7]


def test_untick_in_table_excludes_and_saves(window, app, board_copy):
    from PySide6.QtCore import Qt
    from pnpslice.project import ProjectSettings
    window.load(board_copy)
    window.show_plate(1)
    window.sidebar.auto_number.setChecked(True)
    t = window.sidebar.table
    row = next(r for r in range(t.rowCount()) if t.item(r, 0).text().startswith("SOIC8"))
    idx = window.sidebar.index_at_row(row)
    key = window.plates[1].parts[idx].key
    t.item(row, 0).setCheckState(Qt.Unchecked)
    assert key in window.project.excluded
    assert key in ProjectSettings.load(board_copy).excluded
    assert window.view.items_by_index[idx].excluded
    assert "(63)" in window.plate_btns[1].text()
    assert window.sidebar.include_all_btn.isVisibleTo(window.sidebar.widget())

    window.slice_current()
    assert window.mode == "preview"
    skip = [p for p in window.sliced[1].placements if p.skip]
    assert len(skip) == 1 and skip[0].excluded

    window.sidebar.include_all_btn.click()
    assert not window.project.excluded and "(64)" in window.plate_btns[1].text()


def test_exclude_whole_package_from_menu_action(window, app, board_copy):
    window.load(board_copy)
    window.show_plate(1)
    keys = {p.key for p in window.plates[1].parts if p.package.startswith("R_1206")}
    window.set_excluded(keys, True)          # what the menu's "Exclude all … on this plate" does
    assert "(34)" in window.plate_btns[1].text()
    assert sum(it.excluded for it in window.view.items_by_index) == 30