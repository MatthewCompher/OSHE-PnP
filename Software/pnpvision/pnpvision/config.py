import tomllib
from pathlib import Path

def load(path="config.toml"):
    p = Path(path)
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    cfg["_root"] = p.resolve().parent
    return cfg

def rel(cfg, path):
    """Resolve a config-relative path."""
    return str(Path(cfg["_root"]) / path)
