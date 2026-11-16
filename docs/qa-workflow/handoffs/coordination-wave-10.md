# Подготовка поручения 16: первая публикация TestOps

Дата: 2026-11-15. Статус подготовки: **ready**.
Исполнитель 16 не запущен; разрешения на внешнюю запись нет.

## Собственная работа координатора

Прочитаны AGENTS.md, workflow README/индекс заданий, MVP, wave 7–9,
runbook TestOps и текущие CLI/state/verification. В каталоге workflow
до этой подготовки не было задания или handoff 16; поиск имён в artifacts
также не обнаружил отдельного evidence задачи 16.

Подготовлено [поручение 16](../agent-tasks/16-testops-first-publication.md).
Оно разделяет подготовку конкретного пакета и отдельно разрешаемую
публикацию/close одного launch; согласование найденных bindings — отдельная
контрольная точка. Пользователь запускает исполнителя самостоятельно.

## Локальные наблюдения, не серверная проверка

- В `artifacts/testops/` найдены два state: fix `run-5tsmzg1d` и baseline
  `run-vzsatlfk`. Оба schema 1, pending, attempts=0, launch=null, project 5444,
  endpoint `https://allure.qa.guru`. Состояния прочитаны без записи/миграции.
- Для кандидата выбран fix `run-5tsmzg1d`. Шесть исходных result JSON имеют
  status=passed. Его manifest SHA-256:
  `343f317e43ece1a5b72ff1cc688dfe4dc77057e9badfe12296aa981d0cfb2702`.
- Повторно вычислены SHA всех 15 текущих файлов api-contract-v1:
  расхождений с manifest кандидата нет. Это не повтор API execution.
- Старый isolate-пакет кандидата не содержит input_sha256 и
  assignments_sha256. `_validate_upload_package` его заблокирует.
  Исполнителю поручены backup, штатное обновление plan/schema и пересборка
  до первой попытки. Координатор пакет/state не менял.
- CLI не предоставляет close/recovery команд. Исполнитель должен до записи
  проверить поддерживаемый синтаксис инструмента и безопасный порядок close.
- В isolate согласованные ID можно назначить после отправки без изменения
  package assignments digest: `_assignments` использует None для case ID.
  Это наблюдение кода, не доказанный живой workflow.

Сетевых вызовов, upload/close, API/UI, Docker/Gradle, подагентов,
commit/push/PR координатор не выполнял. Права записи и состояние проекта
сейчас не проверялись. Исторические evidence/handoffs сохранены.

## Проверки документации

Локальные проверки чтения state/result/manifest и SHA завершились exit 0.
Ссылки нового поручения/отчёта проверены; `git diff --check` — exit 0.
Unit и collection не повторялись: реализация не изменялась. Числа
233 unit / 248 collected остаются результатами wave 9, не этой подготовки.

Первая TestOps-публикация, live положительный REST verify и полный MVP
по-прежнему не выполнены.
