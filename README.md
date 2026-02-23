# Docker

```bash
docker compose build --no-cache
```

Запуск по розкладу (cron у контейнері):

```bash
docker compose up -d scheduler
```

## Коли йде обробка

- `scheduler` запускає задачу щодня о `01:10` (`Europe/Kyiv`)
- обробляються дані за попередню добу

## Що саме обробляється

- 2 компанії: `Ace`, `Unit`
- 2 типи документів:
  - `рішен`
  - `викон лист|докум`

Результат записується в:
- `dbo.docs_decision_ace`
- `dbo.docs_decision_unit`

SQL view (`automatic_data_of_*`) підтягують ці дані автоматично