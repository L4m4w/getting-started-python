# Проверка 20R: исходные пробы проходят, приёмка остаётся открытой

Дата: 2026-11-15. **20/20R пока не приняты; независимая задача 21 не выдана.**
Это coordination wave 21 (номер отчёта), не выполнение задачи 21.
Следующее поручение — [20R2](../agent-tasks/20r2-evidence-and-pr-identity.md).

Прочитаны [handoff 20R](20r-orchestrator-corrections.md),
[дизайн 20R](../design/20r-orchestrator-corrections.md), изменённые
adapters/orchestrator/CLI/helpers и новые regression tests.
Исторические отчёты/пробы не изменялись.

## Что подтвердил координатор

Evidence: `artifacts/workflow-implementation/coordinator-20r-review-20261115/`.

- Собственный targeted pytest `tests/unit/test_workflow_20r.py -q`:
  **32 passed**, exit 0, `targeted.xml` (3.67 s).
- Оригинальные пять проб предыдущей приёмки повторены из новой копии
  с изменением только пути вывода результата: **exit 0, 5/5 старых
  violation_reproduced=false**, `original-five-probe-results.json`.
  Исправления F1/F4/F5 и узких отрицательных случаев F2/F3 подтверждены.
- 346 passed — измерение исполнителя; координатор независимо перечитал
  manifest/JUnit run-vu1p3zav: 346 testcase, failures/errors/skips=0,
  manifest exit 0. Полный unit/collection заново не повторялся.
- Все семь защищённых SHA из evidence исполнителя совпали с текущими
  файлами. Рабочий workflow index/state, accepted TestOps states/log и
  manifest run-ni_5bvnc не менялись.
- `reviewed-inputs.sha256.json` фиксирует точные исходники/документы
  этой проверки; `verification-summary.json` — сводку.

## Оставшиеся воспроизведения

Новые независимые пробы: `probe.py` и `probe-results.json` в том же
evidence. Exit 1 означает обнаруженные нарушения. Четыре fake-проекта
создаются в TemporaryDirectory, реальный execution только читается.

### R1 — P1: неверная проверка полноты evidence (продолжение F2)

`_source_identity_problems` проверяет только перечисленные manifest
файлы, но не обязательный состав контракта. `_composition_problems`
отбрасывает только «чужие» имена, не проверяя биекцию/полноту/дубли/
статусы и обязательность raw Allure. Проба: source_identity содержит
только docs/unit-requirement.md, без тестового исходника; JUnit содержит
три повтора UNIT-VAL-001 вместо трёх разных сценариев; Allure result
файлов нет. Head импортируется, после base **phase=executed**.

Отдельный положительный compatibility check обнаружил обратный дефект:
`_composition_problems` на сохранённом **run-ni_5bvnc** считает raw
Allure результаты foreign, поскольку их `name` — русские display titles
без CAT-UPD-VAL ID. У принятого пилота mapping устанавливается по
fullName/параметрам/ALLURE_ID, а не по display name. Историческое
принятие execution сохраняется; это дефект нового валидатора.

Нужна проверка точного versioned source scope и наборов сценариев
по настоящему контракту результатов, включая допустимый отдельный
baseline subset. Подмена имени в test fixtures на scenario ID скрыла
несовместимость с реальными данными.

### R2 — P1: patch digest всё ещё выдаётся за Git head (продолжение F3)

`_pr_head_sha` возвращает app patch SHA-256 в поле head_sha; для dirty
QA возвращает commit, предшествующий незакоммиченным изменениям.
Новый тест `test_spec_records_head_sha` прямо закрепил patch→head.
Проба: app_head.kind=patch, Git commit с fix отсутствует, fake transport
эхом возвращает patch digest; **PR status=verified**. Patch/source
digest не является immutable Git commit, даже при совпадении строк.

Сейчас допустим только локальный черновик spec. Для verified нужны
настоящий commit identity и проверяемая эквивалентность его source tree
принятому составу. Будущий commit не превращает старый прогон в новый.

### R3 — P1: provenance является произвольным waiver (продолжение F2)

`import_execution` допускает provenance для любого варианта;
`_source_identity_problems` принимает source_identity_missing=true.
Проба: **head** manifest с чужим tests commit и без source_identity,
provenance всего `{tests_commit: <foreign>, source_identity_missing: true}`
без digest решения/manifest/evidence — **imported, bound_revision=1**.
Это не ранее принятое историческое исключение; значения совпали только
потому, что caller сам задал ожидаемые значения по отклонённому manifest.

### R4 — P2: prepare не возобновляется с сохранённой границы

`prepare_testops` всегда исполняет цикл plan/assign/package. Проба:
успешный prepare → тот же prepare: **снова три dispatch**, включая
package. Отсутствие новых внешних writes этим повтором не означает
выполнение заявленного skip completed steps. В новых тестах проверен
sent→verify, но нет заявленных crash-after-plan/assign/package cases.
Нужны durable checkpoints с проверкой текущих source/mapping/package
SHA и regression на каждую границу. Guards existing TestOps не ослаблять.

## Решение

Старые пять конкретных воспроизведений устранены, но требования точной
identity и проверяемой идемпотентности пока не закрыты. Выполнить 20R2
с regression на эти четыре группы; F1/F4/F5 не переделывать без причины.
Состав результата/MVP не расширяется; новых разрешений на live операции нет.
Исполнителя запускает пользователь, координатор агентов не запускал.

API/UI/SUT, Docker/Gradle, сеть, CI, TestOps-публикации и commit/push/PR
координатором не выполнялись. Новые/обновлённые документы проверены:
локальные ссылки и diff --check обоих репозиториев — OK. Полный MVP
остаётся незавершённым.
