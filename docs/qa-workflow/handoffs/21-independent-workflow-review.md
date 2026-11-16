# 21 — сводное независимое ревью QA workflow

Дата: 2026-11-15. Координатор: **needs_corrections**.
21A/21B/21C завершены и приняты как результаты независимого ревью.
Готовность реализации к следующему Git/PR этапу не принята: нужны
исправления 21R и их общая проверка. Историческая приёмка 20/20R2 как
минимальной offline-реализации из wave 22 сохраняется с новыми findings.
Полный MVP не завершён.

## Входы и версия

- [21A](21a-state-and-evidence-review.md): schema/envelopes/contracts.
- [21B](21b-effects-and-recovery-review.md): effects/recovery.
- [21C](21c-cli-and-repeat-review.md): CLI/index/locks/fake repeat.
- [Wave 23](coordination-wave-23.md): разделение ответственности.
- Exact accepted inputs: `artifacts/workflow-implementation/coordinator-20r2-review-20261115/reviewed-inputs.sha256.json`.

Новых общих решений после wave 23 до этой проверки не найдено; три
handoff уже были готовы. HEAD обоих репозиториев остались прежними:
QA `c84483bf6647678d4052eb377e04a682cdaddd74`, приложение
`36674280b6878540a9e88f40aaeedf5dfdd2e6ce`. Оба checkout dirty;
эти commit SHA не включают пилотные изменения.

## Измерения ревьюеров и координатора

Координатор независимо пересчитал сохранённый JUnit: 21A — 70 passed,
21B — 57 passed, 21C — 14+3+4 = 21 passed; всего 148, без
failures/errors/skips. Это прогоны ревьюеров, не новый pytest координатора.
Полный unit/collection повторно не выполнялся.

Собственный evidence координатора:
`artifacts/workflow-review/coordinator-21-review-20261115/`.
Команда: `.venv/bin/python artifacts/workflow-review/coordinator-21-review-20261115/review.py`
— exit 0. `verification-summary.json` содержит команды/коды и сверки.

- 13/13 accepted SHA, 19/19 protected SHA и 15/15 API source SHA совпали
  до/после. 7556 исходных файлов отчётов/evidence ревьюеров с расширениями
  py/json/xml/txt совпали до/после. Это контроль выбранного набора, не
  утверждение о fingerprint всех файлов репозиториев.
- Семь scripts ревьюеров повторены в новом evidence. A/B — побайтные
  копии; в двух C scripts заменён только `EV` на каталог копии.
  Оригиналы на месте не запускались. Каждый script exit 0; этот exit
  означает завершение пробы, а не отсутствие findings.
- A: schema — 9 записей (3 type crashes, baseline re-import defect;
  p6 — контроль с несогласованной phase, не самостоятельный finding),
  forged published — 3 записи (q2/q3 воспроизведены), accept/import —
  8 записей (lookalike/bool воспроизведены), real evidence — 11/11 OK.
- B: 13 записей — 6 OK, 2 DEFECT, 5 MINOR. MINOR P7/P7b объединены
  в один finding F5; итог — шесть групп F1–F6, а не семь независимых
  дефектов. Ключевой факт: created + zero search дал два create,
  remote numbers 100/101; stale inherited intent после old adoption
  продолжил блокировать новую линию.
- C: full-chain simulation — 31/31, concurrency/recovery — 24/24.
  Repeat dispatch: runner 8→8 / 6→6, create 1→1 на каждый PR / 0→0.
  Published здесь только fake simulation. Рабочий workflow initialized.
- Real head/base compatibility: 6 head results, problems=[]; baseline
  без provenance отклонён по двум файлам 17A, с принятой записью — [].
  Пять tree digest harness head/base, TestOps head/base и workflow
  совпали до/после (см. `probe_real_evidence_results.json`). Негативные
  копии также имели mismatch имени каталога; целевые source/scenario
  ошибки подтверждены отдельными сообщениями, а не одним blocked outcome.
- `sh tools/versions.sh` — exit 0, Python 3.13.15, pins совпали;
  diff --check обоих репозиториев — exit 0.

Production CLI subprocess smoke 21C принят по сохранённым командам и
логам: init/status/doctor/resume/repeated init/check, exits 0/2/69.
Координатор его заново не запускал. 75/77/127/130 и настоящая
многопроцессная гонка отдельно subprocess-пробами не подтверждены.

## Объединённые findings и решения

Ниже 12 групп без дублей. Точные file:line/trigger/repro сохраняются
в исходных handoff; пути воспроизведения координатора приведены выше.

| Finding | Приоритет координатора | Решение / владелец |
| --- | --- | --- |
| 21B F1: created PR + zero search повторяет create (`orchestrator.py:2262–2357`) | P1, блокирует live PR | 21R-B: известный номер — targeted get/exact verification, отсутствие доказательства никогда не разрешает повтор |
| 21A F2: отсутствующий tests PR/required=false допускает published (`state.py:300–413`) | P1 для заявленного published-инварианта | 21R-A: обе роли и TestOps обязательны, required строго true; проверять до implied_phase |
| 21B F2: inherited intent остаётся unknown после разрешения старой линии (`orchestrator.py:2369–2380`) | P2 | 21R-B: проверяемая сверка parent intent, без удаления истории и обхода remote deduplication |
| 21A F1: типы expected_executions/strength/junit_summary вызывают crash (`state.py:340–370,514`) | P2 | 21R-A: явная type/domain validation и clean 69 |
| 21A F3: baseline re-import после T8 — ложный no-op (`orchestrator.py:1116–1119`) | P2 | 21R-B: полный повторный evidence check и безопасная привязка base к текущей ревизии при эквивалентности; head не переиспользовать |
| 21A F4: lookalike node IDs принимаются (`orchestrator.py:591–596`) | P2 | 21R-B: boundary-token matching, отрицательная и положительная регрессии |
| 21A F5: true принимается как TestOps ID (`envelopes.py:180`) | P2 | 21R-A: bool запрещён, положительные int допустимы |
| 21B F3: reconcile без spec даёт KeyError (`orchestrator.py:1891–1894`) | P2 | 21R-B: controlled blocked/kept, без dispatch |
| 21B F4: search exception выходит наружу (`orchestrator.py:1892,2309`) | P2 | 21R-B: controlled indeterminate/blocked, intent не retry-safe |
| 21B F5: corrupt TestOps state падает в verify/reconcile/observe | P2 | 21R-B: единый controlled 69, чужой state неизменен; не терять доказанные решения reconciliation |
| 21B F6: base observation заменяет head publication (`orchestrator.py:1224–1239`) | P2 | 21R-B: наблюдение base не меняет head publication, включая verified/published fixture |
| 21C F1: multi-store требует недокументированный --workflow-id | P3 | 21R-C: точные примеры global flag перед subcommand, включая supersede |

Уточнения рекомендаций ревьюеров:

1. 404/None/error targeted get после уже успешного create не является
   достаточным разрешением нового create: никаких автоматических retry.
   Exact ref можно принять; иначе сохранять номер/intent и блокировку.
2. Refresh inherited snapshot не должен автоматически разрешать новый
   PR при уже существующем старом remote effect. Проверяются parent
   identity/intent/spec/result; конфликт — blocked, точный PR — adoption
   только после действующих commit/tree/exact-spec проверок.
3. Base rebind допустим только после полного актуального source/scenario/
   provenance/environment check. Нельзя просто убрать bound_revision
   из gate и нельзя расширять исторический accepted registry.
4. P3 B create@rev2 блокировался уже фазой initialized. Это не доказательство
   guards после полного восстановления новой ревизии до executed;
   21R-B добавляет регрессию именно на этом достижимом пути.
5. Schema checks защищают от повреждения локального state, а не
   аутентифицируют автора произвольного согласованного state. Контрольная
   q1 с полностью сфабрикованными данными не доказывает live-публикацию.

## Приёмка и следующая очередь

Независимое ревью выполнено; реализацию нельзя продвигать к live PR до
21R. [21R-A](../agent-tasks/21r-a-state-and-envelopes.md),
[21R-B](../agent-tasks/21r-b-orchestration-and-recovery.md),
[21R-C](../agent-tasks/21r-c-runbook-and-catalogue.md) могут выполняться
параллельно в непересекающихся write scopes. Запускает пользователь.
Общие индексы/планы и финальная приёмка остаются координатору.
После всех результатов: own targeted/integration checks на объединённой
версии, SHA/evidence сверки и отдельное решение; затем актуализация 19A.

API/TestOps 00–18, launch 57317, bindings и state/log остаются принятыми.
Исторические ограничения 07, 10/17 и close-аудита wave 17 сохраняются.
Новых сети/SUT/API/UI, Docker/Gradle/CI, TestOps/PR writes, Git
commit/push/checkout/reset не было. Секреты не читались/не копировались,
рабочий workflow и accepted execution state не изменялись.
Immutable Git heads, реальные draft PR, live идемпотентность и итоговая
оценка ручных доработок/затрат остаются открытыми критериями MVP.
