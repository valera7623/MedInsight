"""SMART on FHIR OAuth2 client for external EHR integration."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SmartOnFhirClient:
    """OAuth2 client for SMART on FHIR EHR systems (EPIC, Cerner, etc.)."""

    def __init__(
        self,
        *,
        authorization_url: str | None = None,
        token_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        scopes: str | None = None,
        fhir_base_url: str | None = None,
    ) -> None:
        self.authorization_url = authorization_url or settings.SMART_AUTHORIZATION_URL
        self.token_url = token_url or settings.SMART_TOKEN_URL
        self.client_id = client_id or settings.SMART_CLIENT_ID
        self.client_secret = client_secret or settings.SMART_CLIENT_SECRET
        self.scopes = scopes or settings.SMART_SCOPES
        self.fhir_base_url = (fhir_base_url or settings.FHIR_BASE_URL).rstrip("/")
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token
        if not self.client_id or not self.token_url:
            raise ValueError("SMART client credentials not configured")
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "scope": self.scopes,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self.token_url, data=data)
            resp.raise_for_status()
            payload = resp.json()
        self._access_token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Accept": "application/fhir+json",
        }

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.fhir_base_url}/{path.lstrip('/')}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def fetch_patient(self, patient_id: str) -> dict[str, Any]:
        return self._get(f"Patient/{patient_id}")

    def fetch_observation(self, patient_id: str) -> list[dict[str, Any]]:
        bundle = self._get(f"Observation?patient={patient_id}")
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource")]

    def fetch_encounter(self, patient_id: str) -> list[dict[str, Any]]:
        bundle = self._get(f"Encounter?patient={patient_id}")
        return [e["resource"] for e in bundle.get("entry", []) if e.get("resource")]

    def push_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        rtype = resource.get("resourceType")
        rid = resource.get("id")
        path = f"{rtype}/{rid}" if rid else rtype
        url = f"{self.fhir_base_url}/{path}"
        headers = {**self._headers(), "Content-Type": "application/fhir+json"}
        method = "PUT" if rid else "POST"
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, headers=headers, json=resource)
            resp.raise_for_status()
            return resp.json() if resp.content else {"status": "ok"}
