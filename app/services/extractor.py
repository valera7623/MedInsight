import logging
import re
from functools import lru_cache
from typing import Any

from app.config import settings
from app.utils.tracing import trace_span

logger = logging.getLogger(__name__)

try:
    import spacy

    SPACY_AVAILABLE = True
except ImportError:
    spacy = None  # type: ignore[assignment]
    SPACY_AVAILABLE = False
    logger.info("spaCy not installed — using regex-only entity extraction")

ICD10_PATTERN = re.compile(r"\b([A-Z]\d{2}(?:\.\d{1,2})?)\b", re.IGNORECASE)

DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b"),
    re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"),
    re.compile(
        r"\b(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|"
        r"июля|августа|сентября|октября|ноября|декабря)\s+\d{4})\b",
        re.IGNORECASE,
    ),
]

MEDICATION_SUFFIX_PATTERN = re.compile(
    r"\b([А-ЯA-Z][а-яa-z]{3,}(?:ин|ол|ам|ид|ил|ан|ат|азол|празол|статин|циллин))\b",
    re.UNICODE,
)

# Words that match medication-like suffixes but are not drugs.
MEDICATION_STOPWORDS = frozenset({
    "рекомендован", "телефон", "гормон", "орган", "регион", "протокол",
    "горизонт", "положен", "направлен", "описан", "заключен",
})

KNOWN_MEDICATIONS = {
    "амоксициллин", "парацетамол", "ибупрофен", "аспирин", "метформин",
    "эналаприл", "лозартан", "омепразол", "аторвастатин", "амлодипин",
}

RU_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

# Clinical sections whose comma-separated values are treated as diagnoses.
ANAMNESIS_SECTION_PATTERNS = [
    re.compile(r"перенес[её]нные\s+заболевания[:\s]+([^.\n]+)", re.IGNORECASE),
    re.compile(r"перенес[её]нные\s+гинекологические\s+заболевания[:\s]+([^.\n]+)", re.IGNORECASE),
    re.compile(r"гистологическое\s+описание[^:]*:\s*([^.\n]+)", re.IGNORECASE),
]

DIAGNOSIS_LINE_PATTERN = re.compile(
    r"диагноз[:\s]+([^.\n]{3,200})",
    re.IGNORECASE,
)

DIAGNOSIS_NOISE = re.compile(
    r"^(?:нет|не\s+выявлен|без\s+особенност|эхопатолог|противопоказан|"
    r"заключение\s*:|основной\s*:|мкб|мкб\s*[-–]\s*10|"
    r"аллергологический|гемотрансфуз|наследственный|"
    r"умеренной\s+степени|слабой\s+степени|неактивный)\b",
    re.IGNORECASE,
)

# Phrases anywhere in the string that indicate conclusions, not diagnoses.
DIAGNOSIS_NOISE_ANYWHERE = re.compile(
    r"противопоказан|к\s+вынашиванию|к\s+оперативному\s+лечению|"
    r"эхопатолог|без\s+особенност|горизонтальное\s+положение|"
    r"ритм\s+синусовый|визуализация\s+протоков",
    re.IGNORECASE,
)

HISTOLOGY_GRADING = re.compile(
    r"степени\s+выраженности|неактивный|умеренной|слабой",
    re.IGNORECASE,
)

MERGED_ICD_PATTERN = re.compile(
    r"^([A-Z]\d{2}(?:\.\d{1,2})?)\s*\(([^)]+)\)\s*$",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def get_nlp() -> Any | None:
    if not SPACY_AVAILABLE:
        return None
    try:
        return spacy.load(settings.SPACY_MODEL)
    except OSError:
        logger.warning("spaCy model %s not found, using blank Russian pipeline", settings.SPACY_MODEL)
        return spacy.blank("ru")


def _normalize_date(raw: str) -> str | None:
    raw = raw.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]

    match = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"

    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"

    match = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", raw, re.IGNORECASE)
    if match:
        day, month_name, year = match.groups()
        month = RU_MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    return None


def _extract_dates_regex(text: str) -> list[str]:
    found: list[str] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            normalized = _normalize_date(match.group(1))
            if normalized:
                found.append(normalized)
    return found


def _extract_dates_spacy(text: str, nlp) -> list[str]:
    if nlp is None:
        return []
    dates: list[str] = []
    doc = nlp(text[:100000])
    for ent in doc.ents:
        if ent.label_ in ("DATE", "TIME"):
            normalized = _normalize_date(ent.text)
            if normalized:
                dates.append(normalized)
    return dates


def _normalize_diagnosis_phrase(phrase: str) -> str | None:
    phrase = re.sub(r"\s+", " ", phrase.strip(" \t-–—:;"))
    if len(phrase) < 3 or len(phrase) > 80:
        return None
    if re.fullmatch(r"[A-ZА-Я]\.?", phrase, re.IGNORECASE):
        return None
    if re.search(r"\bосновной\b", phrase, re.IGNORECASE):
        return None
    if re.search(r"\bзаключение\b", phrase, re.IGNORECASE):
        return None
    if DIAGNOSIS_NOISE.search(phrase):
        return None
    if DIAGNOSIS_NOISE_ANYWHERE.search(phrase):
        return None
    if re.search(r"\bнет\s*$", phrase, re.IGNORECASE):
        return None
    if ICD10_PATTERN.fullmatch(phrase):
        return None
    if phrase.lower() in {"основной", "заключение", "описание"}:
        return None
    # Long free-text sentences are usually conclusions, not coded diagnoses.
    if len(phrase.split()) > 6:
        return None
    return phrase


def _split_diagnosis_clauses(section: str) -> list[str]:
    clauses: list[str] = []
    for i, part in enumerate(re.split(r"[,;]", section)):
        normalized = _normalize_diagnosis_phrase(part)
        if not normalized:
            continue
        if i > 0 and HISTOLOGY_GRADING.search(normalized):
            continue
        clauses.append(normalized)
    return clauses


def _parse_merged_icd_label(label: str) -> tuple[str, list[str]] | None:
    match = MERGED_ICD_PATTERN.match(label.strip())
    if not match:
        return None
    code = match.group(1).upper()
    descriptors = [part.strip() for part in re.split(r"[,;]", match.group(2)) if part.strip()]
    return code, descriptors


def _format_icd_diagnosis(code: str, descriptors: list[str]) -> str:
    code = code.upper()
    if descriptors:
        return f"{code} ({', '.join(descriptors)})"
    return code


def _is_icd_descriptor(text: str) -> bool:
    """Short qualifiers that belong to the same coded diagnosis line (not anamnesis)."""
    lowered = text.casefold().strip()
    if re.search(r"\bбесплодие\b", lowered):
        return True
    return lowered in {
        "мужской фактор",
        "женский фактор",
        "тазовый фактор",
        "смешанный фактор",
        "нерасшифрованный фактор",
    }


def _extract_coded_diagnosis_line(line: str) -> list[str]:
    """Merge ICD-10 code with descriptors from the same diagnosis line."""
    if not ICD10_PATTERN.search(line):
        return []
    codes = [code.upper() for code in ICD10_PATTERN.findall(line)]
    if not codes:
        return []
    text_part = ICD10_PATTERN.sub("", line)
    descriptors = _split_diagnosis_clauses(text_part)
    return [_format_icd_diagnosis(codes[0], descriptors)]


def _extract_textual_diagnoses(text: str) -> list[str]:
    found: list[str] = []

    for pattern in ANAMNESIS_SECTION_PATTERNS:
        for match in pattern.finditer(text):
            found.extend(_split_diagnosis_clauses(match.group(1)))

    for match in DIAGNOSIS_LINE_PATTERN.finditer(text):
        found.extend(_extract_coded_diagnosis_line(match.group(1)))

    return found


def _extract_diagnoses(text: str) -> list[str]:
    raw: list[str] = list(_extract_textual_diagnoses(text))

    nlp = get_nlp()
    if nlp is not None:
        doc = nlp(text[:100000])
        for ent in doc.ents:
            if ent.label_ == "DISEASE" or "диагн" in ent.text.lower():
                normalized = _normalize_diagnosis_phrase(ent.text.strip())
                if normalized:
                    raw.append(normalized)

    covered_codes: set[str] = set()
    for item in raw:
        parsed = _parse_merged_icd_label(item)
        if parsed:
            covered_codes.add(parsed[0])
        elif ICD10_PATTERN.fullmatch(item):
            covered_codes.add(item.upper())

    for match in ICD10_PATTERN.finditer(text):
        code = match.group(1).upper()
        if code not in covered_codes:
            raw.append(code)
            covered_codes.add(code)

    return sorted(consolidate_diagnosis_labels(raw), key=str.casefold)


def _title_medication(name: str) -> str:
    return name[0].upper() + name[1:]


def _is_valid_medication(name: str) -> bool:
    return name.lower() not in MEDICATION_STOPWORDS


def _extract_medications(text: str) -> list[str]:
    found: set[str] = set()
    lower_text = text.lower()

    for med in KNOWN_MEDICATIONS:
        if med in lower_text:
            found.add(_title_medication(med))

    for match in MEDICATION_SUFFIX_PATTERN.finditer(text):
        word = match.group(1)
        if len(word) >= 5 and _is_valid_medication(word):
            found.add(_title_medication(word.lower()))

    med_section = re.search(
        r"(?:назнач(?:ен|ено|ения)|лекарств(?:а|о)|препарат(?:ы)?)[:\s]+([^\n]{5,200})",
        text,
        re.IGNORECASE,
    )
    if med_section:
        for match in MEDICATION_SUFFIX_PATTERN.finditer(med_section.group(1)):
            word = match.group(1)
            if _is_valid_medication(word):
                found.add(_title_medication(word.lower()))

    nlp = get_nlp()
    if nlp is not None:
        doc = nlp(text[:100000])
        for ent in doc.ents:
            if ent.label_ in ("PRODUCT", "ORG") and any(
                suffix in ent.text.lower() for suffix in ("ин", "ол", "ам", "статин", "циллин")
            ):
                if _is_valid_medication(ent.text):
                    found.add(ent.text.strip())

    return sorted(found, key=str.lower)


def is_valid_diagnosis_label(label: str) -> bool:
    """Whether a stored diagnosis string should appear in analytics/UI."""
    label = (label or "").strip()
    if not label:
        return False
    parsed = _parse_merged_icd_label(label)
    if parsed:
        code, descriptors = parsed
        if not ICD10_PATTERN.fullmatch(code):
            return False
        return all(_is_icd_descriptor(part) or _normalize_diagnosis_phrase(part) for part in descriptors)
    if ICD10_PATTERN.fullmatch(label):
        return True
    if _is_icd_descriptor(label):
        return True
    return _normalize_diagnosis_phrase(label) is not None


def filter_diagnosis_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        if not is_valid_diagnosis_label(label):
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        parsed = _parse_merged_icd_label(label)
        if parsed:
            result.append(_format_icd_diagnosis(parsed[0], parsed[1]))
        elif ICD10_PATTERN.fullmatch(label):
            result.append(label.upper())
        else:
            result.append(label)
    return result


def consolidate_diagnosis_labels(labels: list[str]) -> list[str]:
    """Merge bare ICD codes with descriptor phrases into 'CODE (description)' form."""
    validated = filter_diagnosis_labels(labels)
    bare_icd: list[str] = []
    merged: list[str] = []
    descriptors: list[str] = []
    standalone: list[str] = []

    for label in validated:
        parsed = _parse_merged_icd_label(label)
        if parsed:
            merged.append(_format_icd_diagnosis(parsed[0], parsed[1]))
            continue
        if ICD10_PATTERN.fullmatch(label):
            bare_icd.append(label.upper())
        elif _is_icd_descriptor(label):
            descriptors.append(label)
        else:
            standalone.append(label)

    result: list[str] = list(standalone)
    merged_codes = {parsed[0] for parsed in (_parse_merged_icd_label(item) for item in merged) if parsed}

    if len(bare_icd) == 1:
        code = bare_icd[0]
        if code not in merged_codes:
            result.append(_format_icd_diagnosis(code, descriptors))
    else:
        result.extend(code for code in bare_icd if code not in merged_codes)
        if not bare_icd and descriptors:
            result.extend(descriptors)

    result.extend(merged)

    seen: set[str] = set()
    unique: list[str] = []
    for item in result:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


@trace_span("extractor_agent", {"agent": "extractor"})
def extract_entities(text: str) -> dict:
    nlp = get_nlp()
    dates = _extract_dates_regex(text)
    dates.extend(_extract_dates_spacy(text, nlp))
    unique_dates = sorted(set(dates))

    result = {
        "diagnoses": _extract_diagnoses(text),
        "medications": _extract_medications(text),
        "dates": unique_dates,
        "full_text": text,
    }
    logger.info(
        "Extracted %d diagnoses, %d medications, %d dates",
        len(result["diagnoses"]),
        len(result["medications"]),
        len(result["dates"]),
    )
    return result
