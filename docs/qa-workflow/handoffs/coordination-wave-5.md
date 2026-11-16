# Приёмка 10: новый API baseline/fix evidence

Дата: 2026-11-14. Проверка выполнена координатором самостоятельно,
без запуска подагентов, Docker, Gradle или новых тестовых прогонов.

## Решение

10 принят. F-1/F-2 ревью 08 закрыты для новых execution
`run-vzsatlfk` и `run-5tsmzg1d`. Исторические evidence 05/07 не изменены;
новые измерения не восстанавливают отсутствовавшие исторические доказательства.

## Проверенные материалы

- `artifacts/harness/run-vzsatlfk/`: JUnit — 4 tests, 4 assertion failures
  (HTTP 200 вместо 400), 0 errors/skipped; manifest exit/result согласован
  с отчётом 10. Allure содержит сохранённые невалидные имена после GET.
- `artifacts/harness/run-5tsmzg1d/`: JUnit — 6 tests, 6 passed,
  0 errors/skipped; четыре HTTP 400 с неизменным snapshot, два HTTP 200
  с именами длиной 2/50 и сохранёнными остальными полями.
- Обе schema 2: api-contract-v1, 15 файлов, missing/changed_during_run
  пусты, recheck завершён. SHA-256 всех 30 source copies проверены;
  все 15 хешей контракта совпадают между прогонами.
- `environment.container_check` обоих manifest: performed/running/matches
  true. Полные gateway image IDs совпадают с build/image evidence и
  pre/post binding; container ID не менялся внутри каждого execution.
  Base patch metadata — null; fix patch SHA-256 совпадает с сохранённым patch.
- `artifacts/integration/catupdval-rerun/`: source identity, отдельный
  base worktree на SHA 36674280b6878540a9e88f40aaeedf5dfdd2e6ce,
  build commands/logs с exit 0 и image IDs. Product patch — только @Valid.
- Все 10 Allure cleanup attachments: deleted=true; дополнительные SQL
  выборки показывают 0 категорий пользователей пилота, exit 0.
- `post-down.txt`: down exit 0, UTC timestamp, фильтрованные выборки
  контейнеров и сетей catupdval пусты, оба exit 0.

Проверки JSON/XML, SHA-256 и чтение evidence завершились exit 0.
Это аудит сохранённых материалов, а не собственное наблюдение живого Docker.

## Уточнения к handoff 10

В integration-каталоге фактически 18 файлов, а не указанные 16.
Фраза «различие base↔fix по всем шести сценариям» шире выполненного scope:
сравнение base/fix доказано для четырёх негативных случаев;
два позитивных выполнены только на fix. Это не блокирует приёмку задания 10.

## Следующие поручения

- Независимому ревьюеру (11, если будет назначен): проверить новые evidence
  и координационное решение; без изменений кода и запуска стенда.
- Исполнителю TestOps-интеграции: подготовить стабильный scenario → TestOps
  mapping и идемпотентную загрузку в проект 5444. Создание/изменение кейсов
  и upload требуют отдельного поручения; токен не включать в документы.
- Отдельные оставшиеся части MVP: Git/PR с фиксированными версиями,
  минимальный оркестратор со состояниями/возобновлением, проверка повторной
  обработки без дублей и итоговая оценка MVP.

TestOps upload, commit/push и PR координатор не выполнял.
Полный MVP не завершён. Другие агенты не запускались.
