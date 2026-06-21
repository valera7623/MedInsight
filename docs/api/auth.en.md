# API — Authentication

Prefix: `/api/auth`

## POST /api/auth/register

Register a user.

**Body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email | string | yes | Email |
| password | string | yes | Password |
| full_name | string | yes | Full name |
| role | string | yes | admin, doctor, nurse, … |
| subdomain | string | yes | Clinic |
| department_id | int | for nurse/head | Department ID |

**Example:**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@clinic.ru",
    "password": "SecurePass123",
    "full_name": "Ivan Ivanov",
    "role": "doctor",
    "subdomain": "demo",
    "department_id": 1
  }'
```

**Response 201:**

```json
{
  "id": 5,
  "email": "doctor@clinic.ru",
  "full_name": "Ivan Ivanov",
  "role": "doctor"
}
```

## POST /api/auth/login

**Body:** `email`, `password`, `subdomain`

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"doctor@clinic.ru","password":"SecurePass123","subdomain":"demo"}'
```

**Response 200:**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

## GET /api/auth/me

Current user. Requires Bearer token.

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/auth/me
```

**Response:**

```json
{
  "id": 5,
  "email": "doctor@clinic.ru",
  "full_name": "Ivan Ivanov",
  "role": "doctor",
  "department_id": 1,
  "department_name": "Therapy"
}
```

## GET /api/auth/departments

Public list of clinic departments.

```
GET /api/auth/departments?subdomain=demo
```

## Errors

| Code | Cause |
|------|-------|
| 400 | Email already taken, invalid role |
| 401 | Wrong password |
| 404 | Subdomain not found |
