"""Parse radiology findings, impressions and recommendations from DICOM text."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import DicomStudy

FINDING_PATTERNS = re.compile(
    r"\b(normal|abnormal|mass|fracture|effusion|nodule|lymph|hemorrhage|"
    r"инфильтрат|опухол|перелом|выпот|узел|лимфо|кровоизлиян|норма|патолог)",
    re.IGNORECASE,
)
LOCALIZATION_PATTERNS = re.compile(
    r"\b(right|left|bilateral|upper|lower|mediastin|ventricle|"
    r"прав\w*|лев\w*|двусторон|верхн\w*|нижн\w*|средостен\w*|желудоч\w*|L\d[-–]L\d)",
    re.IGNORECASE,
)
IMPRESSION_MARKERS = re.compile(
    r"(impression|conclusion|заключение|вывод|итог)\s*[:\-]?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
RECOMMENDATION_MARKERS = re.compile(
    r"(recommend|рекоменд)\w*\s*[:\-]?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
SENTENCE_SPLIT = re.compile(r"[.\n;]+")


class DicomRadiologyParser:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _study(self, study_uid: str) -> DicomStudy | None:
        return self.db.query(DicomStudy).filter(DicomStudy.study_uid == study_uid).first()

    def _text_sources(self, study_uid: str, sr_text: str = "") -> str:
        study = self._study(study_uid)
        parts: list[str] = []
        if study:
            if study.study_description:
                parts.append(study.study_description)
            if study.radiology_impression:
                parts.append(study.radiology_impression)
        if sr_text:
            parts.append(sr_text)
        return "\n".join(parts)

    def extract_findings(self, dicom_study_uid: str, *, sr_text: str = "") -> list[str]:
        text = self._text_sources(dicom_study_uid, sr_text)
        findings: list[str] = []
        for sentence in SENTENCE_SPLIT.split(text):
            s = sentence.strip()
            if len(s) < 8:
                continue
            if FINDING_PATTERNS.search(s) or LOCALIZATION_PATTERNS.search(s):
                findings.append(s)
        if not findings and text.strip():
            findings.append(text.strip()[:500])
        return list(dict.fromkeys(findings))[:20]

    def extract_impression(self, dicom_study_uid: str, *, sr_text: str = "") -> str:
        study = self._study(dicom_study_uid)
        if study and study.radiology_impression:
            return study.radiology_impression

        text = self._text_sources(dicom_study_uid, sr_text)
        match = IMPRESSION_MARKERS.search(text)
        if match:
            return match.group(2).strip()[:2000]

        sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
        if sentences:
            return sentences[-1][:2000]
        return ""

    def extract_recommendations(self, dicom_study_uid: str, *, sr_text: str = "") -> list[str]:
        text = self._text_sources(dicom_study_uid, sr_text)
        recs: list[str] = []
        for match in RECOMMENDATION_MARKERS.finditer(text):
            block = match.group(2).strip()
            for line in SENTENCE_SPLIT.split(block):
                line = line.strip()
                if len(line) > 10:
                    recs.append(line)
        return list(dict.fromkeys(recs))[:10]

    def parse_radiology_report(self, dicom_study_uid: str, *, sr_text: str = "") -> dict[str, Any]:
        findings = self.extract_findings(dicom_study_uid, sr_text=sr_text)
        impression = self.extract_impression(dicom_study_uid, sr_text=sr_text)
        recommendations = self.extract_recommendations(dicom_study_uid, sr_text=sr_text)

        keywords: list[str] = []
        text_lower = self._text_sources(dicom_study_uid, sr_text).lower()
        for kw in ("normal", "abnormal", "mass", "fracture", "effusion", "nodule"):
            if kw in text_lower:
                keywords.append(kw)

        localizations: list[str] = []
        for match in LOCALIZATION_PATTERNS.finditer(self._text_sources(dicom_study_uid, sr_text)):
            localizations.append(match.group(0))

        return {
            "findings": findings,
            "impression": impression,
            "recommendations": recommendations,
            "keywords": list(dict.fromkeys(keywords)),
            "localizations": list(dict.fromkeys(localizations))[:15],
        }
