"""Injection pre-filter (U6.4): flag instruction-like text anywhere in a claim.

Docs 03, 05 and 10: notes and attachment text are data, never instructions,
and "attachment instructions cannot change a rule outcome". That property
comes from the architecture, not from this filter: rules never read free text,
and model output is validated and kept out of the scored results. This filter
is the layer in front of the model. A flagged claim:

  - still runs all 15 rules and keeps every result. Its expected results are
    ordinary (CG-116C84D4774D carries the pack's injection sentence and its
    R012 is FAIL), and evaluate.py rejects a run that drops a claim;
  - is kept away from the AI explainer, which falls back to the deterministic
    explanation (Screening.ai_allowed);
  - is shown to a reviewer, through the injection_flag event.

Docs 03 and 10 use "quarantine" for ingestion errors: a claim that is not
read at all. A flagged claim is read, so it is never called quarantined here.

Every string in the claim is scanned, not only notes and attachment text,
because any string can reach the model as evidence (service_code, modifier and
IDs are free strings too). Each string is scanned as written, then decoded
(HTML entities, tags and comments, percent-encoding, literal \\u/\\x escapes,
base64, hex, ROT13, reversed) and normalized (NFKC, combining marks and
zero-width characters removed, Latin lookalikes from Cyrillic and Greek mapped
to Latin). A squashed form with every separator removed and leetspeak mapped
catches split words ("ign ore", "i.g.n.o.r.e", "1gn0re"). All strings are
also joined, which catches an instruction split across fields.

A report never quotes the input: a hit names a JSON pointer, a pattern
family and the decoding layer that revealed it.

Known limits: the patterns are English with a few French forms. An
instruction written in other words, in another language, or spread across
enough harmless-looking fields will pass. That is why the model's output is
validated separately and can never change a result.
"""
import base64
import binascii
import codecs
import html
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import unquote

SCANNER_VERSION = "1.0.0"

# Cyrillic and Greek letters that look like Latin ones, after casefold().
_LOOKALIKES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ї": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "ɡ": "g", "ո": "n", "ı": "i", "ɩ": "i",
    "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v", "ο": "o",
    "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ω": "w",
})
_LEET = str.maketrans("0134578@$!|", "oieastbasil")

_F = r"(?:[a-z0-9]+ ){0,3}"  # up to three filler words
_WORD_PATTERNS = {
    "override": [
        rf"\b(?:ignore|disregard|forget|override|bypass|skip|ignorez|ignorer|oubliez|oublier)\b {_F}"
        r"(?:instructions?|rules?|rulebook|prompts?|guidelines?|polic(?:y|ies)|checks?|context|"
        r"directives?|regles|consignes)\b",
        r"\b(?:ignore|disregard|forget)\b (?:all|previous|prior|above|earlier|everything|preceding)\b",
    ],
    "role_play": [
        r"\b(?:you are now|act as|pretend (?:to be|you are)|from now on|new instructions?|"
        r"updated instructions?|do this instead|instead do)\b",
    ],
    "secret_request": [
        rf"\b(?:reveal|print|show|leak|output|send|give|disclose|tell|share|display|dump|expose)\b {_F}"
        r"(?:secrets?|api keys?|apikey|passwords?|tokens?|credentials?|system prompt|hidden prompt|"
        r"env(?:ironment)? variables?)\b",
    ],
    "decision_forcing": [
        rf"\b(?:mark|label|treat|approve|accept|clear|approuvez|approuver|validez|valider)\b {_F}"
        r"(?:claims?|everything|payment|demande|dossier)\b",
        rf"\b(?:say|respond|answer|declare|pretend)\b {_F}"
        rf"(?:checks?|rules?|everything|claims?)\b {_F}(?:passed|pass|approved|valid|ok|clean|acceptable)\b",
    ],
    "output_tampering": [
        rf"\b(?:replace|change|rewrite|alter|modify|overwrite|swap)\b {_F}"
        r"(?:rule ids?|status(?:es)?|severity|results?|evidence|confidence|findings?|verdicts?)\b",
    ],
    "tool_or_exfiltration": [
        rf"\b(?:call|fetch|visit|open|post|send|transmit|upload|forward|curl|wget|browse|exfiltrate)\b {_F}"
        r"(?:urls?|endpoints?|web|websites?|webhooks?|servers?|links?|email addresses?)\b",
    ],
    "false_authority": [
        r"\b(?:payer|insurer|administrator|admin|mentor|developer|supervisor|management)\b "
        r"(?:says|said|states|confirms|confirmed|authorizes|authorized|allows|has approved)\b",
        r"\bautomatically (?:acceptable|approved|accepted|covered|valid|authorized)\b",
        r"\balways (?:acceptable|approved|accepted|authorized)\b",
    ],
}
_TEXT_PATTERNS = {
    # On the normalized text, where punctuation survives.
    "role_marker": [
        r"(?:^|\s)(?:system|assistant|developer)\s*:",
        r"<\|im_start\|>|\[/?inst\]|<<sys>>|###\s*(?:system|instruction)",
    ],
    "tool_or_exfiltration": [r"https?://|\bwww\."],
}
# Matched against the squashed form: separators removed, leetspeak mapped.
_SQUASHED = {
    "override": ("ignoreprevious", "ignoreallprevious", "ignoreallrules", "ignoretherule",
                 "disregardprevious", "disregardall", "forgetprevious", "forgetallprevious"),
    "secret_request": ("systemprompt", "revealallsecret", "revealthesecret", "revealsecret",
                       "revealtheapikey", "apikey"),
    "decision_forcing": ("markeveryclaimapproved", "markallclaimsapproved", "approvetheclaim",
                         "approvethisclaim", "sayallcheckspassed"),
    "role_play": ("youarenow", "newinstruction"),
}

# One alternation per family: a family matches when any of its patterns does.
_COMPILED = {
    kind: {family: re.compile("|".join(f"(?:{p})" for p in patterns)) for family, patterns in table.items()}
    for kind, table in (("words", _WORD_PATTERNS), ("text", _TEXT_PATTERNS))
}

_BASE64 = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2}){12,}")
_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})")
_TAGS = re.compile(r"<!--|-->|<[^<>]{0,200}>")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_MAX_DEPTH = 2
# Enough of each side of a field boundary to hold any squashed phrase.
_SPAN = max(len(ph) for phs in _SQUASHED.values() for ph in phs) - 1


@dataclass(frozen=True)
class Hit:
    path: str    # JSON pointer of the string, or "(joined)" for text split across fields
    family: str  # which kind of instruction
    layer: str   # how it was revealed: "text", or a decoding chain such as "base64>html"


@dataclass(frozen=True)
class Screening:
    claim_id: object
    hits: tuple

    @property
    def flagged(self):
        return bool(self.hits)

    @property
    def ai_allowed(self):
        """False when the claim's text must not reach the model."""
        return not self.hits

    def as_event(self):
        return {
            "event": "injection_flag",
            "claim_id": self.claim_id,
            "scanner_version": SCANNER_VERSION,
            "hits": [{"path": h.path, "family": h.family, "layer": h.layer} for h in self.hits],
        }


def _normalize(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(" " if unicodedata.category(ch) == "Cc" else ch
                for ch in s if unicodedata.category(ch) not in ("Mn", "Cf"))
    return unicodedata.normalize("NFKC", s).casefold().translate(_LOOKALIKES)


def _words(norm):
    return " ".join(re.findall(r"[a-z0-9]+", norm))


def _squashed(norm):
    return re.sub(r"[^a-z]", "", norm.translate(_LEET))


def _printable(text):
    return bool(text) and sum(ch.isprintable() or ch.isspace() for ch in text) / len(text) >= 0.9


def _decoded(text):
    """(layer, text) for each decoding that changes the text."""
    if "&" in text or "<" in text:
        yield "html", _TAGS.sub(" ", html.unescape(text))
    if "%" in text:
        yield "percent", unquote(text)
    if "\\" in text:
        yield "escape", _ESCAPE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)), text)
    for m in _BASE64.finditer(text):
        chunk = m.group(0)
        try:
            raw = base64.b64decode(chunk + "=" * (-len(chunk) % 4),
                                   altchars=b"-_" if ("-" in chunk or "_" in chunk) else None)
            out = raw.decode("utf-8")
        except (binascii.Error, ValueError):
            continue
        if _printable(out):
            yield "base64", out
    for m in _HEX.finditer(text):
        try:
            out = bytes.fromhex(m.group(0)).decode("utf-8")
        except ValueError:
            continue
        if _printable(out):
            yield "hex", out


def _views(text, layer="text", depth=0):
    yield layer, text
    if depth == 0:
        yield "rot13", codecs.encode(text, "rot13")
        yield "reversed", text[::-1]
    if depth < _MAX_DEPTH:
        for name, out in _decoded(text):
            if out != text:
                yield from _views(out, name if layer == "text" else f"{layer}>{name}", depth + 1)


def _families(text):
    """Pattern families found in one view of a string."""
    norm = _normalize(text)
    words, squashed = _words(norm), _squashed(norm)
    found = []
    for family, pattern in _COMPILED["words"].items():
        if pattern.search(words):
            found.append(family)
    for family, pattern in _COMPILED["text"].items():
        if family not in found and pattern.search(norm):
            found.append(family)
    for family, phrases in _SQUASHED.items():
        if family not in found and any(ph in squashed for ph in phrases):
            found.append(family)
    return found


def _strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{path}/{str(k).replace('~', '~0').replace('/', '~1')}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}/{i}")


def _across(ends, starts):
    """True when one field ends with the first part and a different field
    starts with the rest."""
    return bool(ends) and bool(starts) and (len(ends) > 1 or len(starts) > 1 or ends != starts)


def screen(claim):
    """Scan every string in claim. Never modifies claim."""
    hits, seen = [], set()
    strings = list(_strings(claim))
    for path, text in strings:
        for layer, view in _views(text):
            for family in _families(view):
                if (path, family) not in seen:
                    seen.add((path, family))
                    hits.append(Hit(path, family, layer))
    # Split across fields. The squashed forms are joined in claim order, and a
    # phrase may also start at the end of any field and finish at the start of
    # any other, in either order (notes come last in the envelope, so a phrase
    # from notes into an attachment is out of claim order). Every field's
    # suffixes and prefixes up to _SPAN are indexed once, so this stays linear
    # in the number of fields instead of pairing each field with every other.
    squashed = [_squashed(_normalize(text)) for _, text in strings]
    joined = "".join(squashed)
    ends, starts = defaultdict(set), defaultdict(set)
    for i, s in enumerate(squashed):
        for k in range(1, min(len(s), _SPAN) + 1):
            ends[s[-k:]].add(i)
            starts[s[:k]].add(i)
    for family, phrases in _SQUASHED.items():
        if not any(h.family == family for h in hits) and any(
                ph in joined or any(_across(ends.get(ph[:k]), starts.get(ph[k:])) for k in range(1, len(ph)))
                for ph in phrases):
            hits.append(Hit("(joined)", family, "joined"))
    cid = claim.get("claim_id") if isinstance(claim, dict) else None
    return Screening(cid if isinstance(cid, str) and _SAFE_ID.fullmatch(cid) else None, tuple(hits))
