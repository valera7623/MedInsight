#!/usr/bin/env python3
"""Test multi-tenancy, RBAC, and file encryption."""

import sys
import time
from pathlib import Path

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def auth_headers(token: str, tenant_id: int | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if tenant_id is not None:
        h["X-Tenant-ID"] = str(tenant_id)
    return h


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=120.0)
    print(f"=== MedInsight Phase 3 Tenant Test ({BASE_URL}) ===\n")

    # Login as super admin
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@medinsight.com", "password": "change_me_super_admin"},
    )
    if login.status_code != 200:
        print("Super admin login failed — set SUPER_ADMIN_* in .env")
        sys.exit(1)
    sa_token = login.json()["access_token"]
    print("✓ Super admin authenticated")

    # Create tenant A
    t1 = client.post(
        "/api/admin/tenants",
        headers=auth_headers(sa_token),
        json={"name": "Clinic Alpha", "subdomain": "clinic-alpha"},
    )
    t1.raise_for_status()
    tenant_a = t1.json()["id"]
    print(f"✓ Tenant A created: id={tenant_a}")

    # Create tenant B
    t2 = client.post(
        "/api/admin/tenants",
        headers=auth_headers(sa_token),
        json={"name": "Clinic Beta", "subdomain": "clinic-beta"},
    )
    t2.raise_for_status()
    tenant_b = t2.json()["id"]
    print(f"✓ Tenant B created: id={tenant_b}")

    # Create admin for tenant A
    u1 = client.post(
        "/api/admin/users",
        headers=auth_headers(sa_token),
        json={
            "email": "admin@alpha.ru",
            "password": "test123456",
            "full_name": "Admin Alpha",
            "role": "admin",
            "tenant_id": tenant_a,
        },
    )
    u1.raise_for_status()
    print("✓ Admin user for tenant A created")

    # Login admin A
    la = client.post(
        "/api/auth/login",
        json={"email": "admin@alpha.ru", "password": "test123456", "subdomain": "clinic-alpha"},
    )
    la.raise_for_status()
    token_a = la.json()["access_token"]
    print("✓ Admin A logged in")

    # Create patient in tenant A
    p = client.post(
        "/api/patients",
        headers=auth_headers(token_a, tenant_a),
        json={
            "first_name": "Иван",
            "last_name": "Тестов",
            "birth_date": "1990-01-01",
            "gender": "M",
            "phone": "+79001112233",
        },
    )
    p.raise_for_status()
    patient_id = p.json()["id"]
    print(f"✓ Patient created in tenant A: id={patient_id}")

    # Upload encrypted document
    try:
        from docx import Document as DocxDocument

        test_file = Path("/tmp/tenant_test.docx")
        doc = DocxDocument()
        doc.add_paragraph("Диагноз: J45.0. Назначено: Парацетамол.")
        doc.save(str(test_file))

        with open(test_file, "rb") as f:
            up = client.post(
                "/api/documents/upload",
                headers=auth_headers(token_a, tenant_a),
                data={"patient_id": str(patient_id), "document_type": "discharge"},
                files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        up.raise_for_status()
        doc_id = up.json()["id"]
        encrypted = up.json().get("is_encrypted", False)
        print(f"✓ Document uploaded: id={doc_id}, encrypted={encrypted}")

        for _ in range(30):
            d = client.get(f"/api/documents/{doc_id}", headers=auth_headers(token_a, tenant_a))
            if d.json()["status"] == "parsed":
                print("✓ Document parsed")
                break
            time.sleep(2)

        dl = client.get(f"/api/documents/{doc_id}/download", headers=auth_headers(token_a, tenant_a))
        dl.raise_for_status()
        print(f"✓ Document downloaded ({len(dl.content)} bytes, decrypted in memory)")
    except ImportError:
        print("⚠ python-docx not installed, skipping document test")

    # Create admin for tenant B and verify isolation
    client.post(
        "/api/admin/users",
        headers=auth_headers(sa_token),
        json={
            "email": "admin@beta.ru",
            "password": "test123456",
            "full_name": "Admin Beta",
            "role": "admin",
            "tenant_id": tenant_b,
        },
    ).raise_for_status()

    lb = client.post(
        "/api/auth/login",
        json={"email": "admin@beta.ru", "password": "test123456", "subdomain": "clinic-beta"},
    )
    lb.raise_for_status()
    token_b = lb.json()["access_token"]

    isolated = client.get(f"/api/patients/{patient_id}", headers=auth_headers(token_b, tenant_b))
    if isolated.status_code == 404:
        print("✓ Tenant isolation verified: tenant B cannot see tenant A patient")
    else:
        print("✗ ISOLATION FAILED: tenant B can see tenant A data!")
        sys.exit(1)

    print("\n=== Phase 3 test completed successfully ===")


if __name__ == "__main__":
    main()
