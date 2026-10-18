import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import train  # noqa: E402


@pytest.fixture(scope="session")
def trained(tmp_path_factory):
    """Offline training run (embedded fallbacks) into a temp dir."""
    out = tmp_path_factory.mktemp("artifacts")
    train.main(["--offline", "--no-plots", "--out-dir", str(out)])
    return out


@pytest.fixture(scope="session")
def sg_texts():
    return pd.read_csv(os.path.join(ROOT, "scam_sg.csv")).text.tolist()
