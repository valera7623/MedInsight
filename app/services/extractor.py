import logging
import re
from functools import lru_cache
from typing import Any

from app.config import settings
from app.services.parser import _normalize_extracted_text, _structure_discharge_text
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
    "гемоглобин", "пролактин", "альбумин", "глобулин", "фибриноген",
    "тромбин", "креатинин", "холестерин", "билирубин",
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

# Anamnesis vitae sections — stored separately, not as primary diagnoses.
ANAMNESIS_VITAE_PATTERNS = [
    re.compile(r"перенес[её]нные\s+заболевания[:\s]+([^\n]+)", re.IGNORECASE),
    re.compile(r"перенес[её]нные\s+гинекологические\s+заболевания[:\s]+([^\n]+)", re.IGNORECASE),
    re.compile(r"гистологическое\s+описание[^:]*:\s*([^\n]+)", re.IGNORECASE),
]

OPERATIONS_SECTION = re.compile(
    r"перенес[её]нные\s+операци[ий][:\s]*\n?(.*?)"
    r"(?=\n\s*(?:Данные\s+обследования|Инфекци|Клинический\s+анализ|"
    r"Общий\s+анализ|Биохимическ|Коагулограмм|Гормональн|ПЦР|УЗИ|ЭКГ|Диагноз\s*:|$))",
    re.IGNORECASE | re.DOTALL,
)

OPERATION_PROCEDURE_PATTERN = re.compile(
    r"лапароскоп|гистероскоп|биопс|гиперотом|эктом|пункци|кесарев|"
    r"лапаротом|кольпоскоп|ампутац|удалени|вскрыти",
    re.IGNORECASE,
)

LAB_SECTION_START = re.compile(
    r"^(?:"
    r"клинический\s+анализ\s+крови|"
    r"общий\s+анализ\s+мочи|"
    r"биохимическ\w+\s+анализ\s+крови|"
    r"коагулограмм\w*|"
    r"гормональн\w+\s+обследован\w*|"
    r"пцр\s+анализ|"
    r"исследование\s+сыворотки\s+крови|"
    r"мазок\s+на\s+флору|"
    r"мазок\s+на\s+онкоцитолог\w*|"
    r"инфекци[яи]"
    r")",
    re.IGNORECASE,
)

LAB_SECTION_STOP = re.compile(
    r"^(?:УЗИ|ЭКГ|ФЛГ|Консультация|Диагноз\s*:|Перенесенные|"
    r"мазок\s+на\s+(?!флору)|клинический\s+анализ|общий\s+анализ|"
    r"биохимическ|коагулограмм|гормональн|пцр\s+анализ|исследование\s+сыворотки)",
    re.IGNORECASE,
)

LAB_HEADER_ROW = re.compile(
    r"^(?:показатель|гормоны|инфекци[яи]|инфекции|результат|"
    r"и\s*ф\s*а|рпга|реакция\s+микрометод)\b",
    re.IGNORECASE,
)

ULTRASOUND_CONCLUSION = re.compile(
    r"УЗИ.{0,800}?Заключение:\s*([^\n]+)",
    re.IGNORECASE | re.DOTALL,
)

NUMERIC_RANGE = re.compile(
    r"(\d+(?:[,.]\d+)?)\s*[-–]\s*(\d+(?:[,.]\d+)?)",
)

LAB_SECTION_LABELS = {
    "клинический анализ крови": "ОАК",
    "общий анализ мочи": "ОАМ",
    "биохимический анализ крови": "биохимия",
    "коагулограмма": "коагулограмма",
    "гормональное обследование": "гормоны",
    "пцр анализ": "ПЦР",
    "исследование сыворотки крови": "ИФА",
    "мазок на флору": "мазок",
    "мазок на онкоцитологию": "онкоцитология",
    "инфекция": "инфекции",
}

DIAGNOSIS_LINE_PATTERN = re.compile(
    r"(?:основной\s+)?диагноз(?:\s+по\s+мкб[-\s–]*10)?[:\s]+([^\n]{3,250})",
    re.IGNORECASE,
)

DIAGNOSIS_SECTION_STOP = re.compile(
    r"\.\s+(?:Рекоменд\w*|Назнач\w*|Телефон|Лечение|План\s+лечения|Консультация)\b",
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
    phrase = phrase.rstrip(".")
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


def _trim_diagnosis_section(section: str) -> str:
    """Keep ICD dots (N97.0) but stop before recommendations on the same line."""
    section = section.strip()
    match = DIAGNOSIS_SECTION_STOP.search(section)
    if match:
        section = section[: match.start()].strip()
    return section.rstrip(". ")


def _split_diagnosis_clauses(section: str) -> list[str]:
    clauses: list[str] = []
    for i, part in enumerate(re.split(r"[,;]", section)):
        part = _trim_diagnosis_section(part.strip())
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


def _is_icd_subsumed_by_specific_code(code: str, existing: set[str]) -> bool:
    """Drop bare N97 when N97.0 is already present."""
    upper = code.upper()
    return any(other.startswith(f"{upper}.") for other in existing)


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
    """Merge ICD-10 code with descriptors, or capture free-text diagnosis lines."""
    line = line.strip()
    if ICD10_PATTERN.search(line):
        codes = [code.upper() for code in ICD10_PATTERN.findall(line)]
        text_part = ICD10_PATTERN.sub("", line)
        descriptors = _split_diagnosis_clauses(text_part)
        return [_format_icd_diagnosis(codes[0], descriptors)]

    for part in re.split(r"[,;]", line):
        if _is_icd_descriptor(part):
            continue
        normalized = _normalize_diagnosis_phrase(part)
        if normalized:
            return [normalized]
    return []


def _extract_anamnesis_vitae(text: str) -> list[str]:
    """Past medical history (anamnesis vitae) — not the primary coded diagnosis."""
    found: list[str] = []
    for pattern in ANAMNESIS_VITAE_PATTERNS:
        for match in pattern.finditer(text):
            found.extend(_split_diagnosis_clauses(match.group(1)))
    seen: set[str] = set()
    unique: list[str] = []
    for item in found:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return sorted(unique, key=str.casefold)


def _extract_textual_diagnoses(text: str) -> list[str]:
    """Primary diagnosis from coded 'Диагноз:' lines only."""
    found: list[str] = []
    for match in DIAGNOSIS_LINE_PATTERN.finditer(text):
        section = _trim_diagnosis_section(match.group(1))
        found.extend(_extract_coded_diagnosis_line(section))
    return found


def _extract_diagnoses(text: str) -> list[str]:
    raw: list[str] = list(_extract_textual_diagnoses(text))
    covered_codes: set[str] = set()
    for item in raw:
        parsed = _parse_merged_icd_label(item)
        if parsed:
            covered_codes.add(parsed[0])
        elif ICD10_PATTERN.fullmatch(item):
            covered_codes.add(item.upper())

    for match in ICD10_PATTERN.finditer(text):
        code = match.group(1).upper()
        if code in covered_codes or _is_icd_subsumed_by_specific_code(code, covered_codes):
            continue
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
    if nlp is not None and med_section:
        doc = nlp(med_section.group(1)[:100000])
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
    return False


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

    for label in validated:
        parsed = _parse_merged_icd_label(label)
        if parsed:
            merged.append(_format_icd_diagnosis(parsed[0], parsed[1]))
            continue
        if ICD10_PATTERN.fullmatch(label):
            bare_icd.append(label.upper())
        elif _is_icd_descriptor(label):
            descriptors.append(label)

    result: list[str] = []
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


def diagnoses_from_parsed_data(parsed_data: dict | None) -> list[str]:
    """Diagnoses for analytics: stored labels, or re-extract from full_text when empty."""
    if not parsed_data:
        return []
    stored = consolidate_diagnosis_labels(parsed_data.get("diagnoses") or [])
    if stored:
        return stored
    full_text = parsed_data.get("full_text") or ""
    if full_text:
        return _extract_diagnoses(full_text)
    return []


def medications_from_parsed_data(parsed_data: dict | None) -> list[str]:
    """Medications for analytics, excluding lab analyte false positives."""
    if not parsed_data:
        return []
    lab_keys = {str(key).casefold() for key in (parsed_data.get("lab_results") or {})}
    meds: list[str] = []
    seen: set[str] = set()
    for med in parsed_data.get("medications") or []:
        key = str(med).casefold()
        if key in lab_keys or key in MEDICATION_STOPWORDS or key in seen:
            continue
        seen.add(key)
        meds.append(med)
    if meds:
        return meds
    full_text = parsed_data.get("full_text") or ""
    if full_text:
        return _extract_medications(full_text)
    return []


def _normalize_lab_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().casefold())


def _parse_numeric(value: str) -> float | None:
    cleaned = value.replace(",", ".").strip()
    match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _is_abnormal_lab_value(name: str, value: str, reference: str) -> bool:
    value_lower = value.casefold()
    if "не обнаруж" in value_lower:
        return False
    if re.search(r"\bотр\.?\b", value_lower):
        return False
    if "эхопатологии не выявлено" in value_lower:
        return False
    if "без особенност" in value_lower:
        return False

    if "полож" in value_lower or "обнаруж" in value_lower:
        if "авидность" in value_lower:
            return False
        return True

    numeric = _parse_numeric(value)
    if numeric is None or not reference:
        return False

    range_match = NUMERIC_RANGE.search(reference.replace(",", "."))
    if not range_match:
        upper = re.search(r"[<≤]\s*(\d+(?:\.\d+)?)", reference.replace(",", "."))
        if upper and numeric > float(upper.group(1)):
            return True
        return False

    low = float(range_match.group(1))
    high = float(range_match.group(2))
    return numeric < low or numeric > high


def _parse_lab_row(line: str) -> tuple[str, str, str] | None:
    line = line.strip()
    if not line or LAB_HEADER_ROW.match(line):
        return None

    line = re.sub(r"^[•\u2022\s]+", "", line)
    if "\t" in line:
        parts = [part.strip() for part in line.split("\t") if part.strip()]
    else:
        parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]

    if len(parts) < 2:
        return None

    name, value = parts[0], parts[1]
    reference = parts[2] if len(parts) > 2 else ""
    if len(name) < 2 or len(value) < 1:
        return None
    if name.casefold() in {"v", "c", "ig m", "igg"}:
        return None
    return name, value, reference


def _lab_section_label(header_line: str) -> str:
    lowered = header_line.casefold()
    for prefix, label in LAB_SECTION_LABELS.items():
        if prefix in lowered:
            return label
    return "лаборатория"


def _extract_lab_results(text: str) -> dict[str, dict[str, Any]]:
    labs: dict[str, dict[str, Any]] = {}
    current_section = ""
    in_lab_block = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if LAB_SECTION_START.match(line):
            current_section = _lab_section_label(line)
            in_lab_block = True
            if "общий анализ мочи" in line.casefold():
                continue
            continue

        if in_lab_block and LAB_SECTION_STOP.match(line):
            in_lab_block = False
            current_section = ""

        if not in_lab_block:
            continue

        if current_section == "ОАМ" and not LAB_HEADER_ROW.match(line) and "\t" not in line:
            key = _normalize_lab_key("общий анализ мочи")
            labs[key] = {
                "value": line,
                "reference": "",
                "section": current_section,
                "abnormal": _is_abnormal_lab_value("общий анализ мочи", line, ""),
            }
            in_lab_block = False
            current_section = ""
            continue

        parsed = _parse_lab_row(line)
        if not parsed:
            continue

        name, value, reference = parsed
        key = _normalize_lab_key(name)
        labs[key] = {
            "value": value,
            "reference": reference,
            "section": current_section,
            "abnormal": _is_abnormal_lab_value(name, value, reference),
        }

    return labs


def _normalize_operation_line(line: str) -> str | None:
    line = re.sub(r"\s+", " ", line.strip(" \t-–—"))
    if len(line) < 5:
        return None
    if re.fullmatch(r"[\(\)№\s\d./-]+", line):
        return None
    if re.search(r"гистологическое\s+описание", line, re.IGNORECASE):
        return None
    if re.search(r"^(?:аспират\s+из\s+полости|маточные\s+трубы\s+проходимы)\b", line, re.IGNORECASE):
        return None
    if not OPERATION_PROCEDURE_PATTERN.search(line):
        return None

    first_sentence = re.split(r"\.\s+(?=[А-ЯA-Z])", line, maxsplit=1)[0].strip()
    if len(first_sentence) >= 5:
        return first_sentence if first_sentence.endswith(".") else first_sentence
    return line


def _extract_operations(text: str) -> list[str]:
    prepared = _structure_discharge_text(_normalize_extracted_text(text))
    prepared = re.sub(
        r"(перенес[её]нные\s+операци[ий]:)\s+",
        r"\1\n",
        prepared,
        count=1,
        flags=re.IGNORECASE,
    )
    match = OPERATIONS_SECTION.search(prepared)
    if not match:
        return []

    operations: list[str] = []
    seen: set[str] = set()
    for line in match.group(1).splitlines():
        normalized = _normalize_operation_line(line)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        operations.append(normalized)
    return operations


def _extract_imaging_conclusions(text: str) -> list[str]:
    conclusions: list[str] = []
    seen: set[str] = set()

    for match in ULTRASOUND_CONCLUSION.finditer(text):
        conclusion = re.sub(r"\s+", " ", match.group(1).strip(" ."))
        if len(conclusion) < 4:
            continue
        key = conclusion.casefold()
        if key in seen:
            continue
        seen.add(key)
        conclusions.append(conclusion)

    cytology = re.search(
        r"мазок\s+на\s+онкоцитолог\w*[^.\n]*[–-]\s*([^.\n]+)",
        text,
        re.IGNORECASE,
    )
    if cytology:
        note = re.sub(r"\s+", " ", cytology.group(1).strip())
        if note and note.casefold() not in seen:
            conclusions.append(f"Онкоцитология: {note}")
    return conclusions


def labs_dict_to_list(labs: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if not labs:
        return []
    if isinstance(labs, list):
        return [item for item in labs if isinstance(item, dict)]
    return [
        {"name": name, **(value if isinstance(value, dict) else {"value": value})}
        for name, value in labs.items()
    ]


@trace_span("extractor_agent", {"agent": "extractor"})
def extract_entities(text: str) -> dict:
    nlp = get_nlp()
    dates = _extract_dates_regex(text)
    dates.extend(_extract_dates_spacy(text, nlp))
    unique_dates = sorted(set(dates))

    result = {
        "diagnoses": _extract_diagnoses(text),
        "anamnesis": _extract_anamnesis_vitae(text),
        "operations": _extract_operations(text),
        "lab_results": _extract_lab_results(text),
        "imaging_conclusions": _extract_imaging_conclusions(text),
        "medications": _extract_medications(text),
        "dates": unique_dates,
        "full_text": text,
    }
    abnormal_labs = sum(1 for item in result["lab_results"].values() if item.get("abnormal"))
    logger.info(
        "Extracted %d diagnoses, %d anamnesis, %d operations, %d labs (%d abnormal), "
        "%d imaging conclusions, %d medications, %d dates",
        len(result["diagnoses"]),
        len(result["anamnesis"]),
        len(result["operations"]),
        len(result["lab_results"]),
        abnormal_labs,
        len(result["imaging_conclusions"]),
        len(result["medications"]),
        len(result["dates"]),
    )
    return result
