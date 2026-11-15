# 16C — последовательная публикация и live verification

Ты — исполнитель 16C. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Не запускай других агентов. Эта задача выполняется после приёмки 16A/16B,
последовательно, с единственным владельцем execution state.

Прочитай `AGENTS.md`, `knowledge/integrations/testops.md`,
`docs/qa-workflow/agent-tasks/16-testops-first-publication.md`,
handoffs `coordination-wave-9.md`, `coordination-wave-10.md`,
`16a-testops-package.md`, `16b-testops-live-preflight.md` в
`docs/qa-workflow/handoffs/` и решение координатора по этим двум отчётам.

До внешней записи должны быть явно согласованы:

- execution `run-5tsmzg1d`, mode и точный package SHA-256;
- endpoint `https://allure.qa.guru/`, project 5444;
- один launch name, шесть CAT-UPD-VAL-001–006, точные upload/close команды;
- отдельное разрешение пользователя на эту публикацию и close.

**Этот промпт разрешения на публикацию не предоставляет.** Если конкретные
входы/разрешение отсутствуют, заверши безопасной проверкой готовности и
handoff needs_decision; upload/create/close не выполняй.

Твоя область записи после передачи владения координатором:

- `artifacts/testops/run-5tsmzg1d/`;
- новый `artifacts/testops-live/16c-<UTC>/`;
- `docs/qa-workflow/handoffs/16c-testops-publication.md`.

Отчёты/evidence 16A/16B, исторические API/Java артефакты, исходные результаты,
README/код/планы не меняй. Не переключай/reset checkout; сохраняй чужие
изменения. API/UI, Docker/Gradle, commit/push/PR запрещены.

После разрешения выполни фазу B общего задания 16 с такими уточнениями:

1. Повторно проверь целевой проект, текущий state и исходники/пакет/SHA.
   16A/16B должны закончить работу. Если координатор выбрал bind вместо
   isolate, пакет должен быть подготовлен и отдельно согласован **до**
   попытки. Не отправляй старый isolate-кандидат после смены решения.
2. Одна штатная CLI upload-попытка, без retry и отдельного launch create.
   Exit 0 означает sent. Сохрани записанный launch ID и SHA отправки.
   При unknown/timeout/nonzero не повторяй запись и не меняй state вручную.
3. Проверь project записанного launch. Выполни только согласованный close
   при необходимости, с журналом попытки до вызова. Неизвестный исход
   close требует read-only сверки, не слепого повтора.
4. Ограниченное ожидание обработки (до 10 минут, интервал 15 секунд),
   затем штатный `verify --online --transport rest`. Полная пагинация,
   ровно шесть passed, правильные launch/project, closed/ready,
   отсутствие hidden/retries/дублей обязательны. При неполноте/ином
   live-контракте сохрани inconclusive; не исправляй поля догадками.
5. Для isolate сохрани реальные candidates ID и доказательства связи
   каждого scenario/result/case с проектом 5444. Остановись перед assign
   до явного согласования bindings пользователем или координатором.
   После согласования штатный assign и повторный REST verify;
   отправленный пакет не пересобирай. Кандидаты не равны bindings.
6. Uploaded требует полного серверного подтверждения набора, статусов
   и согласованных ID. Empty closed/ready не разрешает resend.
   Recovery/adoption и ручное подтверждение самостоятельно не применяй.
7. После устойчивого sent/uploaded и проверки decide_upload повтори
   тот же вызов upload без retry: ожидается локальный exit 69 до транспорта.
   Сверь неизменность attempts, launch, SHA, upload log и серверного набора.
   Не проверяй это на pending/failed/активном in_progress. Повторный verify
   терминального uploaded может вернуть сохранённое подтверждение:
   не выдавай его за новый HTTP snapshot.

Токен из корневого .env через штатный loader, exported env в приоритете.
Никаких token/JWT/headers/сырых ответов в выводе и evidence. Только целевые
allowlist metadata, UTC, безопасные argv/codes, IDs/статусы/счётчики/SHA.
Если нужны изменения общего кода, остановись с конкретным блокером.

В handoff: ready / blocked / needs_decision; scope и источник разрешения,
execution/package identity, реальные команды/codes, launch URL,
таблица кандидатов/согласованных ID с источником решения, REST checks/verdict,
доказательство блокировки повторного upload, ограничения и следующий шаг.
Выполни `git diff --check`. Отделяй свои измерения от входных отчётов.
Первый upload не завершает полный MVP: финальный execution с ID, Git/PR,
оркестратор/возобновление и сквозная идемпотентность остаются отдельно.
