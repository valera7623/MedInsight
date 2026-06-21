# Глоссарий

| Термин | Определение |
|--------|-------------|
| **MedInsight** | Платформа клинической аналитики |
| **Tenant** | Клиника/организация в системе multi-tenant |
| **Subdomain** | Уникальный идентификатор клиники при входе |
| **RBAC** | Role-Based Access Control — доступ по ролям |
| **JWT** | JSON Web Token — токен авторизации API |
| **Celery** | Очередь фоновых задач (парсинг, DICOM, прогнозы) |
| **Redis** | In-memory store — брокер Celery и кэш |
| **age** | Современное шифрование файлов ( замена PGP ) |
| **DICOM** | Digital Imaging and Communications in Medicine — стандарт мед. изображений |
| **Modality** | Тип DICOM-исследования: CT, MR, US, XR… |
| **Study / Series / Frame** | Иерархия DICOM: исследование → серия → кадр |
| **ProxyAPI** | Прокси к OpenAI API (РФ) |
| **GPT** | Generative Pre-trained Transformer — языковая модель для прогнозов |
| **Readmission** | Повторная госпитализация |
| **Complication risk** | Риск осложнений |
| **Parsed data** | Извлечённые из документа диагнозы и лекарства |
| **Webhook** | HTTP-callback при событиях системы |
| **WebSocket** | Двусторонний канал для real-time уведомлений |
| **Freemium / Pro / Enterprise** | Тарифные планы |
| **Self-healing** | Автовосстановление при сбоях Redis/Celery |
| **Audit log** | Журнал действий пользователей |
| **Anonymization** | Обезличивание ПДн для роли researcher |
| **OpenAPI** | Спецификация REST API (Swagger) |
| **MkDocs** | Генератор статического сайта документации |
| **VPS** | Virtual Private Server — виртуальный сервер |
| **CI/CD** | Continuous Integration / Deployment |
| **OTEL** | OpenTelemetry — распределённый трейсинг |
| **FHIR** | Fast Healthcare Interoperability Resources (стандарт обмена) |
| **ICD-10** | Международная классификация болезней |
| **W/L (Window/Level)** | Яркость и контраст DICOM-изображения |
| **SPA** | Single Page Application |
| **ORM** | Object-Relational Mapping (SQLAlchemy) |

## Сокращения ролей

| Код | Русское название |
|-----|------------------|
| `admin` | Администратор |
| `head_of_department` | Зав. отделением |
| `doctor` | Врач |
| `nurse` | Медсестра |
| `researcher` | Исследователь |
| `viewer` | Наблюдатель |
| `superadmin` | Суперадмин платформы |
