"""Vendor name canonicalization and institutional-vendor identification.

Vendor names in the raw data are fragmented: punctuation variants, entity
suffixes, typos, and card-gateway prefixes ("CITIBANK -...") all split what is
really one vendor into several. The `vendor_id` column helps, but with caveats:
- it is null on roughly half of rows,
- zero-padding is inconsistent across quarters ("0000033707" vs "33707"),
- ALL card-gateway sub-merchants share the gateway's vendor_id, so the id can
  only be used to merge names for non-gateway rows.
"""

import re

import pandas as pd

from anomaly.config import CARD_GATEWAY_PREFIXES, KNOWN_INSTITUTIONAL_VENDORS

# Trailing tokens that distinguish legal form, not identity.
ENTITY_SUFFIXES: frozenset[str] = frozenset({
    "INC", "INCORPORATED", "LLC", "LLP", "LP", "LTD", "PLLC", "PC",
    "CO", "CORP", "CORPORATION", "COMPANY",
})

_NON_ALNUM = re.compile(r"[^A-Z0-9& ]+")
_MULTI_SPACE = re.compile(r" +")


def clean_vendor_name(raw: str | None) -> tuple[str, bool]:
    """Return (canonical_name, is_gateway_submerchant) for a raw vendor name.

    Canonical form: uppercased, gateway prefix stripped, punctuation collapsed
    to spaces, trailing entity suffixes removed.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "", False
    name = str(raw).strip().upper()
    is_gateway = False
    for prefix in CARD_GATEWAY_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
            is_gateway = True
            break
    name = _NON_ALNUM.sub(" ", name)
    name = _MULTI_SPACE.sub(" ", name).strip()
    tokens = name.split(" ")
    while len(tokens) > 1 and tokens[-1] in ENTITY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens), is_gateway


def _normalize_vendor_id(vid: str | None) -> str | None:
    """Strip inconsistent zero-padding; return None for blank ids."""
    if vid is None or (isinstance(vid, float) and pd.isna(vid)):
        return None
    stripped = str(vid).strip().lstrip("0")
    return stripped or None


def add_canonical_vendor(df: pd.DataFrame) -> pd.DataFrame:
    """Add `canonical_vendor` and `is_gateway_submerchant` columns.

    Non-gateway rows sharing a vendor_id are merged to the modal cleaned name
    for that id (catches typos and punctuation variants). Gateway sub-merchants
    keep their own cleaned name — their vendor_id belongs to the gateway.
    """
    if df.empty or "vendor_name" not in df.columns:
        return df

    cleaned = df["vendor_name"].map(lambda v: clean_vendor_name(v))
    df["canonical_vendor"] = cleaned.map(lambda t: t[0]).astype("string")
    df["is_gateway_submerchant"] = cleaned.map(lambda t: t[1])

    if "vendor_id" in df.columns:
        norm_id = df["vendor_id"].map(_normalize_vendor_id)
        eligible = norm_id.notna() & ~df["is_gateway_submerchant"] & (df["canonical_vendor"] != "")
        sub = pd.DataFrame({
            "norm_id": norm_id[eligible],
            "name": df.loc[eligible, "canonical_vendor"],
        })
        if not sub.empty:
            # Modal cleaned name per id, by row count
            counts = sub.groupby(["norm_id", "name"]).size().reset_index(name="n")
            modal = counts.sort_values("n", ascending=False).drop_duplicates("norm_id")
            id_to_name = dict(zip(modal["norm_id"], modal["name"]))
            mapped = norm_id.map(id_to_name)
            use = eligible & mapped.notna()
            df.loc[use, "canonical_vendor"] = mapped[use].astype("string")

    return df


# Pre-cleaned forms of the seed institutional list, so matching aligns with
# canonical names (e.g. "AMAZON.COM" -> "AMAZON COM", "W.B. MASON" -> "W B MASON").
_SEED_INSTITUTIONAL: frozenset[str] = frozenset(
    clean_vendor_name(v)[0] for v in KNOWN_INSTITUTIONAL_VENDORS
)


def is_member_reimbursement(vendor: str | None) -> bool:
    """Vendors like "HON PETE SESSIONS" are expense reimbursements paid to the
    member — every office has its own, so they are rare-by-definition and
    routine rather than third-party self-dealing."""
    if not vendor:
        return False
    v = str(vendor)
    return v.startswith("HON ") or v.startswith("HONORABLE ")


def institutional_vendors(
    detail_df: pd.DataFrame, office_share_threshold: float = 0.25
) -> frozenset[str]:
    """Canonical vendors that are institutional: the seed list plus any vendor
    used by at least `office_share_threshold` of all offices in the data —
    ubiquity makes a vendor uninteresting regardless of whether we listed it."""
    seeds = set(_SEED_INSTITUTIONAL)
    if detail_df.empty or "canonical_vendor" not in detail_df.columns:
        return frozenset(seeds)

    n_offices = detail_df["bioguide_id"].nunique()
    if n_offices == 0:
        return frozenset(seeds)
    per_vendor = detail_df.groupby("canonical_vendor", observed=True)["bioguide_id"].nunique()
    ubiquitous = per_vendor[per_vendor >= office_share_threshold * n_offices].index
    seeds.update(str(v) for v in ubiquitous if v)
    return frozenset(seeds)
