# Резервное копирование

## Зачем

MedInsight хранит БД, зашифрованные документы и DICOM. Регулярный бэкап защищает от потери данных при сбое диска или ошибке обновления.

## Что входит в бэкап

| Компонент | Путь |
|-----------|------|
| SQLite БД | `medinsight.db` |
| Документы | `storage/documents/` |
| DICOM | `storage/dicom/` |
| Ключи age | из `.env` (отдельно!) |

## Автоматический бэкап (Celery Beat)

При `BACKUP_ENABLED=true` задача `backup_task` запускается по расписанию `BACKUP_SCHEDULE_CRON`.

Архивы сохраняются в `backups/` с шифрованием age.

## Ручной бэкап

```bash
cd ~/medinsight
docker compose -f docker-compose.prod.yml exec app \
  python -c "from app.tasks.backup_task import run_backup; run_backup()"
```

Или через скрипт (если есть):

```bash
./scripts/backup.sh
```

## Восстановление

1. Остановите сервисы:

```bash
docker compose -f docker-compose.prod.yml down
```

2. Расшифруйте и распакуйте архив:

```bash
age -d -i age-key.txt backups/medinsight-YYYYMMDD.tar.gz.age | tar xzf -
```

3. Восстановите `.env` и ключи age.
4. Запустите:

```bash
./deploy.sh production
```

## Хранение ключей

!!! danger "Критично"
    Без **AGE_SECRET_KEY** зашифрованные файлы **невосстановимы**. Храните ключи отдельно от бэкапов (менеджер секретов, офлайн-копия).

## Ротация

Старые архивы удаляются автоматически через `BACKUP_RETENTION_DAYS` (по умолчанию 30 дней).

## Рекомендации

- Копируйте `backups/` на внешнее хранилище (S3, другой сервер).
- Тестируйте восстановление раз в квартал.
- Не используйте `docker system prune --volumes` на проде — см. `scripts/docker_cleanup.sh`.
