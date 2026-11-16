# 20R2 — точная identity evidence/PR и checkpoints TestOps

Ты — исполнитель 20R2 QA workflow Niffler. Других агентов не запускай.
Рабочая папка: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3` — read-only.

Прочитай AGENTS.md, задание 20/20R, wave 19–20,
**docs/qa-workflow/handoffs/coordination-wave-21.md целиком**, handoff/design
20R, knowledge каталог/runbook и существующий TestOps results mapper.
Пробы координатора и новые результаты:
`artifacts/workflow-implementation/coordinator-20r-review-20261115/`.
Это номер coordination wave, не разрешение начать независимую задачу 21.

Оригинальные F1/F4/F5 и пять старых проб подтверждены исправленными.
Не переделывай их без причины. Закрой R1–R4 из wave 21:

1. **R1 — полный source и scenario contract.** Проверяй обязательный
   versioned allowlist, уникальность/точные paths и digests всех sources,
   копии и завершённость recheck. Отдельный manifest с одним посторонним
   файлом не доказывает запуск accepted implementation. Положительные
   fixtures обязаны содержать настоящий согласованный source scope,
   а не адаптировать validator к урезанным fixtures.
   JUnit/raw Allure должны точно соответствовать требуемому набору
   сценариев, числу результатов, UUID, статусам и bindings по варианту
   head/base; missing/duplicate/foreign/mismatch блокируют gate.
   Baseline пилота — четыре ожидаемых негативных failures, head — шесть
   passed. Не требуй шесть passed у baseline.
   Для real raw Allure используй fullName+parameters и существующий
   сценарный mapper; display name не содержит scenario ID. Переиспользуй
   строгие TestOps results/integrity helpers вместо нового substring
   mapper. Не меняй тестовые Allure titles или исторические JSON ради
   совместимости. Точный mapping для синтетических fixtures задавай
   явным тестовым контрактом; live пилотная семантика не подменяется fake.
2. **R2 — Git head отдельно от patch/source digest.** Удали fallback
   patch SHA→PR head и dirty tests commit→PR head. Не добавляй требование
   к транспорту «эхом вернуть patch digest»: это не Git commit.
   До известного immutable commit с проверенным tree/scope PR spec —
   только draft/pending, create/verified/published блокируются. Override
   --head-sha не является доказательством сам по себе: проверь тип Git
   объекта и соответствие согласованным файлам/составу через read-only
   adapter, либо оставь pending, если это пока невозможно.
   Для положительного fake PR test используй отдельный commit-head/clean
   fixture с независимо заданной identity/tree, не строку patch digest.
   Исторический execution сохраняет прежнюю base+patch provenance.
   Не выполняй commit/push/PR ради получения head.
3. **R3 — provenance не отключает validation.** Запрети универсальный
   waiver для head и произвольное source_identity_missing=true. Для
   исторического baseline разрешён только versioned explicit acceptance
   record, привязанный к точным execution/manifest/evidence/source digest,
   конкретному решению ревью и допустимому scope equivalence.
   Payload, переписанный с отклонённого manifest, не является таким
   решением. При отсутствии доказуемого принятого источника — blocked;
   baseline не перезапускай, старые evidence не исправляй. Не обязательно
   строить систему криптографической авторизации: нужна проверяемая
   связь с принятой provenance, а не булев обход проверок. Не выдумывай
   coordinator acceptance или новые исторические hashes.
4. **R4 — local TestOps checkpoints.** Реальный skip сохранённых plan/
   assign/package boundaries: повтор готового prepare — no-op без
   dispatch; после сбоя повторяет только невыполненный/неподтверждённый
   шаг. Checkpoints привязаны к exact execution/source/mapping/package
   digests и перепроверяются. Потерянный workflow save после успешного
   delegated шага восстанавливается чтением execution state/integrity,
   а не слепым повтором package. Смена inputs инвалидирует только
   разрешённую локальную pending подготовку; attempted/uploaded остаются
   immutable. Порядок locks и guards существующих CLI сохраняется.

## Приёмочные проверки

- Все оригинальные пять проб и F1/F4/F5 regression остаются зелёными.
- Неполный source scope, три повтора одного сценария вместо полного
  набора, отсутствующий Allure, duplicate UUID/scenario, несовпавшие
  JUnit/Allure statuses и ложные bindings — blocked, phase не executed.
- Положительная read-only compatibility probe для настоящего
  run-ni_5bvnc: mapping всех шести raw результатов без dependence на
  display name; ни state, ни manifest/JSON/копии не меняются. Не нужно
  импортировать execution в рабочий workflow. Если полный исторический
  импорт невозможно доказать — точный blocker, не ослабление правил.
- App kind=patch и dirty QA head — pending/blocked даже при эхо patch
  digest транспортом; missing/unverifiable/wrong commit tree — blocked.
  Положительный fake case — настоящий по модели immutable commit/tree.
- Для head с чужим tests commit/source identity один --provenance не
  разрешает импорт. Baseline acceptance record неверного run/digest/
  scope/неполный/изменённый блокируется. Нет принятого record — blocked.
- Crash после plan, assign, package, включая успех subprocess до save;
  повтор prepare полностью готового execution: dispatch counters не
  растут. Sent→verify resume по-прежнему не отправляет upload.

Не меняй старые probes; свои копии/новые regression fixtures сохраняй
отдельно. При изменении неправильных тестовых ожиданий явно объясни,
какой контракт они нарушали (в частности patch→immutable head).

## Scope и результат

Область кода/тестов/каталога/runbook — как у 20R. Исторические handoff/
design/evidence 19/20/20R и рабочий artifacts/workflow/ не редактировать.
Новые документы:
- `docs/qa-workflow/design/20r2-evidence-and-pr-identity.md`;
- `docs/qa-workflow/handoffs/20r2-evidence-and-pr-identity.md`;
- новый уникальный `artifacts/workflow-implementation/20r2-<UTC>/`.

Все regression state — temp dirs/отдельный store. Никаких API/UI/SUT,
Docker/Gradle, сети, CI, реальных TestOps writes, commit/push/PR или
новых агентов. Сохрани все незакоммиченные изменения. Секреты не читать/
копировать; исторические raw JSON при подготовке fixture санитизировать
с сохранением формы fullName/parameters/name/labels и без credentials.

Через локальный run-tests skill выполни targeted regressions, затем
compile/collection и unit group; сохрани commands/exit codes/counts и
evidence. До/после проверь защищённые SHA и source contract приложения/
API, git diff --check и Markdown-ссылки. Общие workflow README/индекс/
план MVP интегрирует координатор.

Handoff: ready/blocked/needs_decision, SHA входов, по R1–R4 исправление/
regression/evidence и ограничения. Не объявляй 20/MVP принятыми и не
начинай задачу 21. Приёмку выполняет координатор после отчёта.
