"""Flight number parsing and callsign matching.

Users type IATA flight numbers (UA888, CA981, 3U8735); OpenSky reports ICAO
callsigns (UAL888, CCA981, CSC8735). This module bridges the two.
"""
import re
from dataclasses import dataclass
from typing import Optional

# IATA -> ICAO for common airlines. Extend freely; unknown prefixes fall back
# to suffix matching and listing every candidate callsign.
IATA_TO_ICAO = {
    # China
    "CA": "CCA", "MU": "CES", "CZ": "CSN", "HU": "CHH", "ZH": "CSZ",
    "MF": "CXA", "3U": "CSC", "FM": "CSH", "HO": "DKH", "KN": "CUA",
    "9C": "CQH", "SC": "CDG", "GS": "GCR", "JD": "CBJ", "EU": "UEA",
    "GJ": "CDC", "DR": "RLH", "QW": "QDA", "PN": "CHB", "TV": "TBA",
    "8L": "LKE", "NS": "HBH", "RY": "CJX", "FU": "FZA", "GY": "CGH",
    "BK": "OKA", "AQ": "JXX", "UQ": "CUH", "Y8": "YZR", "O3": "CSS",
    # North America
    "UA": "UAL", "AA": "AAL", "DL": "DAL", "WN": "SWA", "B6": "JBU",
    "AS": "ASA", "NK": "NKS", "F9": "FFT", "AC": "ACA", "WS": "WJA",
    "AM": "AMX", "AV": "AVA", "CM": "CMP", "AR": "ARG",
    # Europe
    "BA": "BAW", "LH": "DLH", "AF": "AFR", "KL": "KLM", "LX": "SWR",
    "OS": "AUA", "SK": "SAS", "AY": "FIN", "IB": "IBE", "AZ": "ITY",
    "TP": "TAP", "EI": "EIN", "VS": "VIR", "SN": "BEL", "LO": "LOT",
    "RO": "ROT", "OU": "CTN", "A3": "AEE", "BT": "BTI", "U2": "EZY",
    "FR": "RYR", "W6": "WZZ", "VY": "VLG", "EW": "EWG", "PC": "PGT",
    "TK": "THY", "SU": "AFL", "UX": "AEA",
    # Asia / Oceania
    "NH": "ANA", "JL": "JAL", "KE": "KAL", "OZ": "AAR", "CX": "CPA",
    "KZ": "NCA", "PO": "PAC", "CK": "CKK",
    "SQ": "SIA", "TG": "THA", "QF": "QFA", "NZ": "ANZ", "VN": "HVN",
    "GA": "GIA", "MH": "MAS", "PR": "PAL", "CI": "CAL", "BR": "EVA",
    "AI": "AIC", "6E": "IGO", "UK": "VTI", "SL": "TLM", "FD": "AIQ",
    "AK": "AXM", "TR": "TGW", "5J": "CEB", "JQ": "JST", "VA": "VOZ",
    # Middle East / Africa
    "EK": "UAE", "QR": "QTR", "EY": "ETD", "GF": "GFA", "WY": "OMA",
    "SV": "SVA", "MS": "MSR", "ET": "ETH", "SA": "SAA", "KQ": "KQA",
    "AT": "RAM", "RJ": "RJA", "ME": "MEA", "LY": "ELY",
}

# Non-greedy prefix so "UA888" splits as UA/888, not UA8/88. Airline prefixes
# are 2-3 letters (IATA or ICAO) or digit+letter / letter+digit IATA codes
# like 3U / G5; a prefix ending in a digit (UA8) is never valid.
_IDENT_RE = re.compile(r"^([A-Z0-9]{2,3}?)([0-9]{1,4}[A-Z]?)$")
_PREFIX_RE = re.compile(r"^([A-Z]{2,3}|[0-9][A-Z]|[A-Z][0-9])$")


@dataclass(frozen=True)
class ParsedIdent:
    raw: str          # as typed, normalized upper
    prefix: str       # airline prefix as typed (IATA or ICAO)
    digits: str       # flight number part, e.g. "888" or "8735A"
    icao: Optional[str]  # ICAO airline code if known, else None

    @property
    def display(self):
        return f"{self.prefix}{self.digits}"


def parse(text):
    """Parse 'ua 888' / 'UA-888' / 'UAL888' into a ParsedIdent."""
    norm = re.sub(r"\s+", "", text.upper())
    m = _IDENT_RE.match(norm)
    if not m or not _PREFIX_RE.match(m.group(1)):
        raise ValueError(
            f"cannot parse flight number: {text!r} (expected e.g. UA888, CA981)"
        )
    prefix, digits = m.groups()
    if prefix in IATA_TO_ICAO:
        return ParsedIdent(norm, prefix, digits, IATA_TO_ICAO[prefix])
    if len(prefix) == 3 and prefix.isalpha():
        # already an ICAO callsign prefix, e.g. UAL888
        return ParsedIdent(norm, prefix, digits, prefix)
    return ParsedIdent(norm, prefix, digits, None)


def callsign_digits(callsign):
    """Strip an OpenSky callsign into (prefix, digits) or None."""
    cs = callsign.strip().upper()
    m = re.match(r"^([A-Z]{2,3})([0-9]{1,4}[A-Z]?)$", cs)
    return m.groups() if m else None


def matches(ident, callsign):
    """True if an OpenSky callsign could be this flight number."""
    parts = callsign_digits(callsign)
    if not parts:
        return False
    prefix, digits = parts
    if digits != ident.digits:
        return False
    if ident.icao:
        return prefix == ident.icao
    # unknown airline prefix: any 2-3 letter prefix with the right digits
    return True
