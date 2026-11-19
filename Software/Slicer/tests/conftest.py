import os

import pytest

from pnpslice.crosscheck import find_gerber_dir

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TEST_PCB_NAME = "Test PCB.kicad_pcb"


def _find_file(top: str, name: str) -> str | None:
    """First file called ``name`` anywhere under ``top`` (hidden folders skipped)."""
    for folder, dirs, files in os.walk(top):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if name in files:
            return os.path.join(folder, name)
    return None


# The test board can sit anywhere under tests/fixtures, e.g. a copy of the
# whole KiCad project folder. The Gerbers are found next to it or below it.
TEST_PCB = _find_file(FIXTURES, TEST_PCB_NAME)
TEST_PCB_DIR = find_gerber_dir(TEST_PCB) if TEST_PCB else None


@pytest.fixture(scope="session")
def test_pcb_path():
    if TEST_PCB is None:
        pytest.skip(f"'{TEST_PCB_NAME}' not found under tests/fixtures")
    return TEST_PCB


@pytest.fixture(scope="session")
def test_gerber_dir(test_pcb_path):
    if TEST_PCB_DIR is None:
        pytest.skip("no copper Gerbers found next to the test board")
    return TEST_PCB_DIR


@pytest.fixture(scope="session")
def test_board(test_pcb_path):
    from pnpslice import load_board
    return load_board(test_pcb_path)


def make_board(body: str, version: int = 20260206) -> str:
    """Wrap footprints/graphics in a minimal .kicad_pcb."""
    return f"""(kicad_pcb (version {version}) (generator "pcbnew") (generator_version "10.0")
  (general (thickness 1.6))
  {body}
)"""


RECT_OUTLINE = """
  (gr_line (start 10 10) (end 60 10) (layer "Edge.Cuts"))
  (gr_line (start 60 10) (end 60 50) (layer "Edge.Cuts"))
  (gr_line (start 10 50) (end 60 50) (layer "Edge.Cuts"))
  (gr_line (start 10 50) (end 10 10) (layer "Edge.Cuts"))
"""