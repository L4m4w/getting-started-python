# Интеграция 12/13 и подготовка read-only проверки TestOps

Дата: 2026-11-14. 12/13 приняты как offline-компоненты и интегрированы
координатором. Подагенты координатором не запускались.
TestOps, Docker, Gradle, API/UI, commit/push и PR не выполнялись.

## Работа исполнителей

- 12: строгий scan, UUID/mapping/attachments, атомарная сборка,
  input/assignments/package identity и интерфейсы проверок.
- 13: schema 2 состояния, sent/unknown, сохранение фаз до внешних вызовов,
  ExecutionLock и lifecycle upload/verify с инъекцией транспорта.
- Их исходные handoffs сохранены без переписывания. Решения и уточнения
  координатора ниже имеют приоритет для текущей интеграции.

## Собственная работа координатора

- tools/testops.py переведён на строгую сборку 12 и lifecycle 13.
  Все команды используют общую execution lock; вложенный lifecycle
  получает nullcontext, поскольку CLI уже держит блокировку от load
  через проверки пакета/внешний вызов до save.
- record_package сохраняет input_sha256 и assignments_sha256.
  Перед upload сверяются input, план, mapping/bindings и package digest.
  Старый пакет без identity требует пересборки; после начала попытки
  пересборка запрещена. Подмена входа после попытки блокируется.
- Корневой .env загружается python-dotenv без переопределения exported env.
  Проверка доступности ALLURE_TOKEN дала true; значение не печаталось.
  Это не проверка прав/валидности токена на сервере.
- Ошибки integrity/state/lock дают CLI exit 69 вместо тихого сброса.
- Log внешних операций содержит только UTC/operation/exit/error,
  без сырых ответов или credentials.
- К acquire/reclaim lock добавлен POSIX flock-gate: два конкурента
  не могут одновременно удалить stale lock и захватить разные mutex.
- Ненулевой create exit трактуется unknown, а не доказанный отказ:
  launch мог быть создан до ошибки клиента.
- Нулевая статистика launch не разрешает retry: обработка может отставать.
- Schema 1 failed всегда мигрирует в unknown, даже без launch ID:
  старая реализация не доказывала отсутствие внешних записей.
  Миграция existing artifacts не выполнялась.
- Обновлены старые тесты неверного uploaded/empty-retry поведения,
  добавлены 8 CLI-проверок .env precedence/missing, изменения source и
  bindings, повреждённого state и lock во время внешнего вызова.
- Runbook, каталог компонентов и ссылка ci-github обновлены.

## Проверки

Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2.
Локальный run-tests skill применён координатором.

- Первый интеграционный unit-run: 142 passed / 4 failed,
  `artifacts/harness/run-rjmk37rr/`: четыре прежних теста требовали
  ошибочного uploaded или разрешения retry по нулевой статистике.
- Финальный `sh tools/run-tests.sh group unit`: exit 0,
  **154 passed**, 0 failed/errors/skipped.
  Evidence: `artifacts/harness/run-d6omsnyv/`.
- `sh tools/compile-tests.sh`: exit 0, **169 collected**, без API/UI execution.
- `git diff --check`: exit 0.
- Все 15 файлов api-contract-v1 совпадают с SHA-256 из manifest
  `run-5tsmzg1d`; API-контракт не менялся.
- `.env` доступен CLI; токен не записывался в evidence.

## Оставшиеся ограничения

Это offline-приёмка, не серверная проверка.
Автоматический uploaded через текущий allurectl-транспорт недостижим:
нет проверенного per-result probe. Exit 0 upload означает sent.
Verify без полного доказательства оставляет inconclusive/partial/unknown;
существование launch не подтверждает загрузку. Операторские recovery API
не выставлены как команды для обхода проверки; их применение — отдельная
осознанная операция со сверкой и аудитом.

Серверная схема JSON/пагинация поиска и фактическая модель кейсов при upload
не проверены. Заявления 11 о гарантированных шести кейсах трактуются как
цель локальной модели сигнатур, а не уже полученный серверный результат.
Привязки по реальным TestOps ID ещё отсутствуют.

## Следующее готовое поручение — 14

Read-only проверка проекта 5444: использовать токен из корневого .env
без вывода; проверить аутентификацию/доступ, установленный allurectl и
реальные форматы ответов project/test-case/launch. Сверить официальную
Swagger инстанса для будущего per-result probe и пагинации. В отдельный
handoff сохранить только безопасные metadata, команды, exit codes и
план точной серверной проверки. Не создавать кейсы/launches, не загружать
результаты, не менять исторические evidence и текущие execution state.
Разработку REST-probe и внешнюю синхронизацию назначить отдельно по итогам.

Общий MVP остаётся незавершённым; внешних публикаций нет.
