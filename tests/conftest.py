from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def detail_12col_path(fixtures_dir):
    return fixtures_dir / "detail_12col_sample.csv"


@pytest.fixture
def detail_18col_path(fixtures_dir):
    return fixtures_dir / "detail_18col_sample.csv"


@pytest.fixture
def summary_path(fixtures_dir):
    return fixtures_dir / "summary_sample.csv"


@pytest.fixture
def legislators_path(fixtures_dir):
    return fixtures_dir / "legislators_sample.yaml"
