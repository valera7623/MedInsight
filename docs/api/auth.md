# API — Аутентификация

Префикс: `/api/auth`

## POST /api/auth/register

Регистрация пользователя (self-service). Роли `admin` и `head_of_department` **не** доступны
через публичную регистрацию — их создаёт администратор.

**Доступные роли:** `doctor`, `nurse`, `researcher`, `viewer`

**Тело (JSON):**

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| email | string | да | Email |
| password | string | да | Пароль (политика: min 12 символов в production) |
| full_name | string | да | ФИО |
| role | string | да | Одна из ролей выше |
| subdomain | string | да | Клиника |
| department_id | int | для nurse | ID отделения |

**Пример:**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@clinic.ru",
    "password": "SecurePass123!",
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

**Тело:** `email`, `password`, `subdomain`, опционально `totp_code`

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"doctor@clinic.ru","password":"SecurePass123!","subdomain":"demo"}'
```

**Ответ 200 (успех):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "...",
  "token_type": "bearer",
  "tenant_id": 1,
  "role": "doctor",
  "demo_mode": false,
  "totp_required": false
}
```

**Ответ 200 (нужен код 2FA):** если у пользователя включён TOTP и `MFA_ENFORCED=true`:

```json
{
  "access_token": "",
  "refresh_token": null,
  "totp_required": true,
  "role": "admin"
}
```

Повторите запрос с `totp_code` (6 цифр из приложения-аутентификатора или резервный код).

**Super admin:** выбирается по email независимо от subdomain; subdomain всё равно передаётся в форме.

## POST /api/auth/refresh

Обновление access token по refresh token (cookie или тело запроса).

## POST /api/auth/request-reset

Запрос письма для сброса пароля. Rate limit: 3/час.

## POST /api/auth/reset-password

Установка нового пароля по токену из письма.

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

## 2FA (TOTP)

Эндпоинты `/api/totp/*` (требуют JWT):

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/totp/setup` | QR-код и секрет для приложения |
| POST | `/api/totp/verify` | Подтверждение и включение 2FA |
| POST | `/api/totp/disable` | Отключение (с кодом) |
| GET | `/api/totp/status` | `{ "enabled": true/false }` |

Политика 2FA задаётся `MFA_ENFORCED` и `MFA_REQUIRED_ROLES` (см. [environment-variables.md](../deployment/environment-variables.md)).

## Ошибки

| Код | Причина |
|-----|---------|
| 400 | Email уже занят, неверная роль, слабый пароль |
| 401 | Неверный email/пароль или код 2FA |
| 403 | Аккаунт заблокирован; email не подтверждён; 2FA обязательна для роли |
| 404 | Subdomain не найден |
| 429 | Rate limit или блокировка после неудачных попыток (`Account locked. Retry after …s`) |

Типичные сообщения `detail`:

- `Invalid email or password`
- `2FA is required for your role. Enable TOTP in account settings.`
- `Account locked. Retry after 900s.`
- `Invalid 2FA code`

Автогенерированная OpenAPI-справка: [auth.en.md](auth.en.md)
