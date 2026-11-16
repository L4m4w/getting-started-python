# Приёмка и интеграция 15A/15B: REST verification

Дата: 2026-11-14. 15A/15B приняты как offline-реализация, объединены
координатором в текущем checkout. Координатор подагентов не запускал;
сетевых вызовов, внешних записей TestOps, Docker/Gradle/API/UI,
commit/push/PR не выполнял. Все существующие изменения сохранены.

## Работа исполнителей

- 15A: RestProbe с инъецируемым HTTP, token exchange, launch/progress/
  statistic, строгий Page walk результатов, allowlist и launch drift check.
- 15B: evaluate_snapshot и perform_snapshot_verify; сверка launch/project,
  статусов/статистики, сценариев/case bindings, аномалий hidden/retries;
  orchestration под ExecutionLock.
- Исходные handoffs сохранены; уточнения координатора ниже заменяют
  расходящиеся рекомендации handoff 15B (особенно empty → failed).

## Собственная интеграция координатора

- CLI verify получил явный `--transport rest|allurectl` (default allurectl).
  REST работает через RestProbe + perform_snapshot_verify, не требует
  allurectl. Upload остаётся через AllurectlTransport.
- Перед verify обоих транспортов сверяются source/plan/mapping/package,
  а SHA пакета должен совпасть с записанным upload.package_sha256.
  Требуется записанный launch; переданный --launch-id его не подменяет.
- CLI сохраняет одну execution lock на проверку целиком; nested verifier
  получает nullcontext. Сырые snapshot/HTTP/token в log не записываются.
- Empty даже при closed/ready не переводится в retry-safe failed.
  В REST verification он даёт unknown и блокирует resend. Это сохраняет
  решение wave 8: отсутствие строк сейчас не доказывает отсутствия
  принятого batch. Exit CLI для empty остаётся 75, а не 0.
- Ужесточён normalized snapshot contract: отсутствующие ready/stats/reason
  и nullable-поля строки дают inconclusive вместо KeyError/обхода;
  total=None/pages=0 не доказывают полноту.
- Если recorded launch отсутствует, явный ID не позволяет подтвердить
  чужую сущность без отдельного adoption; probe не вызывается.
- Исправлена граница scenario ID в resolve: 001 не связывается с 0010.
- Добавлены 11 coordinator regression случаев: nullable/missing contract,
  неполнота page count, отсутствие recorded launch, полный CLI → RestProbe
  → verification с fake HTTP, испорченный пакет до HTTP, SID lookalike.
- Обновлены runbook и каталог компонентов/констант.

## Собственные проверки

Локальный run-tests skill применён. Python 3.13.15, pytest 9.1.1,
allure-pytest 2.16.2.

- После первоначального объединения: 222 passed, exit 0,
  `artifacts/harness/run-jp8_5txn/`.
- Финальный `sh tools/run-tests.sh group unit`: exit 0,
  **233 passed**, 0 failed/errors/skipped;
  `artifacts/harness/run-n3e7v_ij/`.
- `sh tools/compile-tests.sh`: exit 0, **248 collected** (не API/UI execution).
- `git diff --check`: exit 0.
- SHA-256 всех 15 файлов api-contract-v1 совпадают с manifest run-5tsmzg1d.

Промежуточные ошибки REST unit, записанные 15B во время параллельной работы
15A, в финальном текущем дереве не воспроизводятся; финальный набор зелёный.

## Ограничения и следующая передача

Непустой launch/statistic/progress/results и реальное сопоставление case IDs
пока не проверены live. OpenAPI и fake HTTP не заменяют это измерение.
Остаются ограничения probe: нет серверной snapshot isolation; drift-check
сверяет launch metadata, не все изменения результатов с неизменным total;
ready/hidden semantics ещё требуют наблюдения на первом живом пилоте.
Строго отсутствующие поля приводят к inconclusive, их нельзя угадывать.

Готовое следующее поручение — 16: подготовить и выполнить только при
отдельном явном разрешении первую ограниченную публикацию пилота в
TestOps 5444: согласованный execution/package, один launch, шесть кейсов,
зафиксированные реальные IDs, поддерживаемое закрытие/ожидание обработки,
REST verify и проверка повторного вызова без повторного upload.
Не публиковать baseline автоматически. Исторические API evidence не менять;
перепакованный upload — отдельный производный артефакт с identity.
До live-публикации сверить доступный синтаксис upload/close и порядок
восстановления после unknown. Само это поручение на публикацию здесь
не выдаётся и не выполнялось.

После первичной связи кейсов нужен финальный execution с закреплёнными IDs
для полного MVP-потока. Также остаются Git/PR, оркестратор/возобновление,
сквозная идемпотентность и итоговая оценка MVP. Полный MVP не завершён.
