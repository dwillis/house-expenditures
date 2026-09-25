"""Repair CSV rows whose fields contain unquoted commas.

The House detail files occasionally contain an unquoted comma inside a text
field (all known cases: a Citibank p-card vendor name), which shifts every
later column. A row with exactly one value more than the header schema means
one field was split in two; re-merging the right pair restores the row.

The merge point is found by trying every adjacent pair and keeping candidates
whose typed columns all validate. A repair is accepted only when exactly one
candidate survives — with two plausible readings the row is left unrepaired
for the caller to skip, so a wrong-but-plausible merge can never corrupt data
silently.
"""

from collections.abc import Callable

Validator = Callable[[str], bool]
ValidatorMap = dict[str, Validator]


def repair_row(
    raw: list[str],
    columns: list[str],
    validators: ValidatorMap,
) -> dict[str, str] | None:
    """Return a dict mapping `columns` to repaired values, or None.

    `raw` holds the row's positional values and `columns` the header schema;
    a repair is attempted only when `raw` has exactly one value more than the
    schema. `validators` maps a column name to a predicate applied to its
    candidate value; columns absent from the map are treated as free text.
    """
    n = len(columns)
    if len(raw) != n + 1:
        return None

    repaired: dict[str, str] | None = None
    for k in range(n):
        merged = raw[:k] + [raw[k] + "," + raw[k + 1]] + raw[k + 2:]
        if all(
            validators.get(col, _free_text)(value)
            for col, value in zip(columns, merged)
        ):
            if repaired is not None:
                return None  # two plausible merge points — refuse to choose
            repaired = dict(zip(columns, merged))

    return repaired


def _free_text(value: str) -> bool:
    return True