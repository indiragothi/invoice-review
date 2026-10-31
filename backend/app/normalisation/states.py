"""GST state codes. VERIFY this table against the official GST state code list before relying
on it (see docs/policy-rules.md). Used for place of supply and the intra / inter-state split."""

import re

STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

_ALIASES: dict[str, str] = {
    "J&K": "01",
    "Orissa": "21",
    "Pondicherry": "34",
    "Uttaranchal": "05",
    "NCT of Delhi": "07",
    "New Delhi": "07",
    "Daman and Diu": "26",
    "Dadra and Nagar Haveli": "26",
}


def _clean(text: str) -> str:
    spaced = text.casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", spaced).split())


# Longest name first, so "dadra and nagar haveli and daman and diu" wins over "daman and diu".
_NAMES: list[tuple[str, str]] = sorted(
    [(_clean(name), code) for code, name in STATE_CODES.items()]
    + [(_clean(alias), code) for alias, code in _ALIASES.items()],
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def state_code_from_text(text: str | None) -> str | None:
    """`"Karnataka"` -> `"29"`; `"Madhya Pradesh (23)"` -> `"23"`; `"29-Karnataka"` -> `"29"`.

    If a printed code and a printed name disagree, return None: the reviewer decides.
    """
    if not text:
        return None
    cleaned = _clean(text)
    by_name = next(
        (code for name, code in _NAMES if re.search(rf"\b{re.escape(name)}\b", cleaned)), None
    )
    codes = [c for c in re.findall(r"\b(\d{2})\b", text) if c in STATE_CODES]
    by_code = codes[0] if codes else None
    if by_name and by_code and by_name != by_code:
        return None
    return by_code or by_name


def state_code_from_gstin(gstin: str | None) -> str | None:
    """First two characters of a GSTIN, if they are a known state code."""
    if gstin and gstin[:2] in STATE_CODES:
        return gstin[:2]
    return None
