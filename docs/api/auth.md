# API — Аутентификация

Префикс: `/api/auth`

## POST /api/auth/register

Регистрация пользователя.

**Тело (JSON):**

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| email | string | да | Email |
| password | string | да | Пароль |
| full_name | string | да | ФИО |
| role | string | да | admin, doctor, nurse, … |
| subdomain | string | да | Клиника |
| department_id | int | для nurse/head | ID отделения |

**Пример:**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@clinic.ru",
    "password": "SecurePass123",
    "full_name": "Иванов Иван",
    "role": "doctor",
    "subdomain": "demo",
    "department_id": 1
  }'
```

**Ответ 201:**

```json
{
  "id": 5,
  "email": "doctor@clinic.ru",
  "full_name": "Иванов Иван",
  "role": "doctor"
}
```

## POST /api/auth/login

**Тело:** `email`, `password`, `subdomain`

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"doctor@clinic.ru","password":"SecurePass123","subdomain":"demo"}'
```

**Ответ 200:**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

## GET /api/auth/me

Текущий пользователь. Требует Bearer token.

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/auth/me
```

**Ответ:**

```json
{
  "id": 5,
  "email": "doctor@clinic.ru",
  "full_name": "Иванов Иван",
  "role": "doctor",
  "department_id": 1,
  "department_name": "Терапия"
}
```

## GET /api/auth/departments

Публичный список отделений клиники.

```
GET /api/auth/departments?subdomain=demo
```

## Ошибки

| Код | Причина |
|-----|---------|
| 400 | Email уже занят, неверная роль |
| 401 | Неверный пароль |
| 404 | Subdomain не найден |
