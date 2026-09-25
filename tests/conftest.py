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


@pytest.fixture
def detail_12col_padded_path(fixtures_dir):
    """12-col header with trailing spaces + trailing comma (2020Q3-2022Q3 files)."""
    return fixtures_dir / "detail_12col_padded_header.csv"


@pytest.fixture
def detail_18col_padded_path(fixtures_dir):
    """18-col header with trailing spaces + trailing comma (2023Q3, 2025Q3 files)."""
    return fixtures_dir / "detail_18col_padded_header.csv"


@pytest.fixture
def detail_edge_cases_path(fixtures_dir):
    """UTF-8 file exercising quoted commas, whitespace, empty and bad fields."""
    return fixtures_dir / "detail_edge_cases_utf8.csv"


@pytest.fixture
def detail_cp1252_path(fixtures_dir):
    """cp1252-encoded file like the 2016-2019 downloads (accented vendors)."""
    return fixtures_dir / "detail_cp1252.csv"
