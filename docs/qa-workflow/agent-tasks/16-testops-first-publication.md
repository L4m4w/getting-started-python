# 16 — первая ограниченная публикация TestOps и live REST verification

Подготовлено координатором: 2026-11-15. Это поручение, не отчёт о выполнении.
Исполнитель пользователем ещё не запущен. Передача этого файла исполнителю
сама по себе **не разрешает внешнюю запись**: сначала выполни фазу A.
Фаза B требует отдельного явного поручения пользователя на публикацию
конкретного пакета и закрытие одного launch.

Ты — исполнитель 16. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Не запускай других агентов. Сохраняй все незакоммиченные изменения;
не переключай и не сбрасывай общий checkout. Commit/push/PR не разрешены.

## Входы и область записи

Прочитай `AGENTS.md`, `docs/qa-workflow/README.md`,
`docs/qa-workflow/agent-tasks/README.md`, `docs/plans/qa-workflow-mvp.md`,
`docs/qa-workflow/handoffs/coordination-wave-{7,8,9,10}.md`,
handoffs 10, 14A/14B, 15A/15B и `knowledge/integrations/testops.md`.
Сверяй текущий код, а не только прежние рекомендации handoffs.

Выделенная запись:

- `docs/qa-workflow/handoffs/16-testops-first-publication.md` — новый отчёт;
- новый уникальный каталог `artifacts/testops-live/16-<UTC>/` — безопасное evidence;
- `artifacts/testops/run-5tsmzg1d/` — рабочее состояние и производный пакет
  после сохранения исходной копии в новом evidence.

README, планы, общий каталог компонентов и исторические handoffs интегрирует
координатор. Исторические `artifacts/harness/`, `artifacts/integration/`,
`artifacts/java/`, `artifacts/testops-readonly/` не изменяй.
Не меняй приложение, API-тесты и их контракт. Не запускай API/UI, Docker,
Gradle или новый фактический execution ради TestOps.
Если нужен ремонт CLI/probe, опиши конкретный блокер и предложи отдельную
задачу; не обходи integrity-проверки в ходе первой публикации.

## Фаза A — подготовка конкретного пакета, без внешней записи

1. Сначала проверь, не появился ли отчёт 16, новый launch или следы попытки
   публикации. Не повторяй чужую/прерванную работу вслепую.
   Сними безопасный inventory **всех** локальных TestOps state: execution,
   endpoint/project, launch ID, upload status/attempts, package digest.
   Состояния не удаляй, не обнуляй. Существующий живой lock не снимай.

2. Целевой endpoint — `https://allure.qa.guru/`, project **5444**,
   `ai_project_Larkin_EA`. Загружай `.env` через
   `tools.testops.load_environment()`; exported env имеет приоритет.
   Проверь эффективные endpoint/project без вывода секретов; несовпадение
   с заданием блокирует запись. Токен/JWT не печатай, не копируй, не передавай
   argv и не сохраняй. Не используй shell tracing и сырой сетевой debug log.
   Повтори только целевые read-only проверки project, пилотных кейсов и
   launches проекта 5444; не перечисляй чужие проекты.
   Старые пустые ответы 14 не доказывают текущее отсутствие сущностей.

3. Выбранный координатором кандидат — fix execution `run-5tsmzg1d`,
   source `artifacts/harness/run-5tsmzg1d/allure-results/`:
   CAT-UPD-VAL-001–006, ровно шесть `passed`, без иных результатов.
   Это повторный API-прогон 10, не результаты 07 и не baseline
   `run-vzsatlfk`. Выбор другого execution требует отдельного решения.
   Перепроверь manifest/JUnit, source digest, mapping UUID → scenario,
   attachments и все 15 SHA api-contract-v1. Проверь связь с base+patch
   по manifest и evidence `artifacts/integration/catupdval-rerun/`.
   Тесты заново не выполняй. SHA manifest при подготовке координатором:
   `343f317e43ece1a5b72ff1cc688dfe4dc77057e9badfe12296aa981d0cfb2702`.

4. На 2026-11-15 локальный state кандидата: schema 1, pending,
   attempts=0, launch=null; старый isolate-пакет не имеет
   input_sha256/assignments_sha256. Это наблюдение перепроверь.
   Если появились attempts/launch/sent/unknown/in_progress/uploaded,
   останови пересборку и перейди к read-only диагностике.
   Перед локальными изменениями сохрани копию state и старого пакета с SHA
   в новом evidence. Через штатный CLI обнови plan/schema 2; новый execution
   ID для обхода старого state создавать нельзя.

   ```sh
   sh tools/run-testops.sh status --execution run-5tsmzg1d
   sh tools/run-testops.sh plan --execution run-5tsmzg1d --results artifacts/harness/run-5tsmzg1d/allure-results --endpoint https://allure.qa.guru --project-id 5444
   ```

5. Если полного набора существующих кейсов по-прежнему нет и нет
   противоречивых/частичных совпадений, подготовь `--mode isolate`.
   Если найдено ровно шесть однозначных кейсов, сохрани кандидатов и
   предложи согласованный bind-вариант; не назначай неоднозначные ID.
   Смешанный набор или сомнительная полнота поиска — needs_decision,
   а не разрешение автоматически создать ещё шесть кейсов.

   Для согласованного isolate-варианта локальная команда:

   ```sh
   sh tools/run-testops.sh package --execution run-5tsmzg1d --mode isolate
   ```

   Зафиксируй mode, input/assignments/package SHA-256, число файлов,
   шесть сценариев/статусов и identity исходного execution. Проверь пакет
   штатными integrity-функциями без сети. После начала внешней попытки
   пакет замораживается; исторические Allure JSON не меняются.

6. **До создания launch** уточни поддерживаемый синтаксис установленного
   allurectl: version, `launch create --help`, `upload --help`,
   `launch close --help`. Сопоставь с client.py. Выясни, что upload с
   явным launch ID не создаст второй launch, как подтверждается завершение
   отправки, требуется ли явный close, как проверить close после сбоя.
   Для отсутствующей команды используй только подтверждённый контракт
   официальной документации/Swagger целевого инстанса; не угадывай REST
   write endpoint. На этой фазе команды create/upload/close не исполняй.
   Сохрани точные безопасные argv и порядок восстановления после unknown.
   Самостоятельный `allurectl upload` в обход lifecycle не допускается.

7. Заверши фазу A отчётом **needs_decision**: предложи пользователю один
   execution/package SHA, один уникальный launch name с execution ID,
   шесть сценариев, mode, точную команду upload и подтверждённую команду
   close, лимит ожидания, план ID/bindings и восстановления. Укажи, что
   права записи ещё не доказаны и внешних записей не выполнялось.
   Фазу B не начинай без отдельного явного поручения. Перед записью после
   паузы повторно сверь state/digests и целевой проект.

## Фаза B — только после отдельного разрешения публикации

Лимит: один новый launch в 5444, одна попытка upload одного согласованного
пакета с шестью результатами. При isolate ожидается не более шести новых
пилотных кейсов. Никаких baseline, watch, bulk import, удаления,
переоткрытия/перепривязки чужих сущностей или второго launch.

1. Под штатной execution lock выполни согласованную команду один раз:

   ```sh
   sh tools/run-testops.sh upload --execution run-5tsmzg1d --execute --launch-name '<согласованное уникальное имя>'
   ```

   Не добавляй `--retry`. Запиши время, exit, upload status, launch ID/URL,
   package SHA записанной отправки. Exit 0 означает **sent**.
   Не запускай отдельный launch create перед CLI: он создаёт launch сам.
   После timeout/nonzero/unknown/in_progress не вызывай upload снова.

2. Если ID известен, read-only проверь принадлежность launch проекту 5444.
   После подтверждённого окончания отправки выполни только согласованный
   close этого launch, если он требуется и ещё не закрыт. Запиши факт
   попытки close до вызова и итог после; при неизвестном результате
   перечитай состояние сервера до любых дальнейших write-действий.
   Отсутствие проверенного способа close — блокер, не повод импровизировать.

3. Выполняй ограниченное read-only ожидание обработки, например не более
   10 минут с интервалом 15 секунд (в инструментах ожидания, не в тестах).
   Записывай UTC и только разрешённые поля launch/progress/statistic/results.
   Используй строгую пагинацию RestProbe, подтверждённую сортировку,
   полноту страниц, повторное чтение metadata. Истечение лимита означает
   needs_decision с сохранённым state, без нового upload.

   ```sh
   sh tools/run-testops.sh verify --execution run-5tsmzg1d --online --transport rest
   ```

4. В isolate первый verify может дать inconclusive/exit 75 и
   `confirmation.checks.candidates`. Это реальные **кандидаты**, ещё не
   согласованные bindings. Сверь каждый ID с кейсом именно проекта 5444,
   точным scenario ID, результатом и полной выдачей; нужны шесть разных ID,
   без orphan/hidden/retries/лишних результатов. Сохрани новый
   `mapping-candidates.json` с ссылками и основаниями.
   Перед assign получи отдельное согласование этих bindings пользователем
   или координатором; до него остановись с needs_decision.
   Не закрепляй ID в API-коде в задаче 16.

5. После согласования назначь шесть пар через `assign`, сохрани новый
   `mapping-approved.json` с источником решения и повтори REST verify.
   В isolate `_assignments()` использует case_id=None: согласование ID
   меняет ожидания verifier, но не отправленный пакет и его digest.
   Не пересобирай пакет в bind после попытки. Если integrity проверка
   блокирует действие, сохрани проблему; обход запрещён.

6. **uploaded** допустим только при полном подтверждении launch/project,
   closed=true, ready=true, полной пагинации, ровно шести ожидаемых
   сценариев `passed` и согласованных case IDs, без аномалий/дублей.
   Непустые реальные ответы впервые проверяют контракт probe; при иных
   полях не подставляй значения по умолчанию и не объявляй успех.
   Empty даже closed/ready не разрешает resend. Сохраняй ограничения
   snapshot isolation, отмеченные wave 9.

7. Повторный вызов upload проверяй только после согласованной успешной
   отправки, когда state устойчиво sent/uploaded и decide_upload блокирует
   её повтор. Повтори ту же CLI-команду без retry: ожидается локальный
   exit 69 **до транспорта**. Сверь неизменность attempts, launch ID,
   upload log, package SHA и серверных результатов/пилотных кейсов.
   Не запускай этот эксперимент на pending/failed или активном in_progress.
   Отдельно повтори read-only verify: для терминального uploaded код может
   вернуть сохранённое подтверждение без нового HTTP; различай это в отчёте.

## Неизвестный исход и границы восстановления

Ненулевой exit create/upload мог произойти после внешней записи. Если ID
не записался, ищи launch read-only по проекту, уникальному имени и временному
окну с полной выдачей. Кандидат не становится автоматически adopted.
Если ID записан — проверяй только его. Сохрани состояние и историю.
Не меняй status на failed/pending, не удаляй lock/state, не создавай другой
execution и не отправляй пакет повторно. `--launch-id` у verify не заменяет
recorded launch. `adopt_launch`, `resolve_in_progress`, ручное confirmation
требуют отдельного поручения на восстановление с доказательствами;
самостоятельно их не применяй. Пустой launch не доказывает отсутствие batch.

## Evidence и отчёт

Сохраняй только целевые allowlist metadata: UTC, команды без секретов,
exit/HTTP codes, версии инструмента и кода, SHA входов/пакета/state,
launch/project IDs, scenario/result/case IDs, статусы, счётчики и причины
неполноты. Не сохраняй JWT/token, headers, сырые HTTP/tool responses,
чужие проекты/кейсы, credentials и пользовательские данные из attachments.
Производный пакет содержит исходные вложения: отдельно проверь их на секреты
перед отправкой; при находке остановись, исторические файлы не редактируй.

В handoff: ready / blocked / needs_decision; авторизация и её точный scope;
фазы, реально выполненные команды/коды; изменённые файлы; execution/package
identity; launch URL; таблица шести mappings и источник согласования;
REST verdict/checks; доказательство отсутствия повторного upload;
что осталось непроверенным. Отделяй свои измерения от прежних проверок
координатора. Если менялись только документы, unit/API/UI не запускай
ради отчёта. Выполни `git diff --check` и проверку созданных ссылок.

После 16 остаются финальный execution с закреплёнными ID, Git/PR,
оркестратор с возобновлением, сквозная идемпотентность и оценка MVP.
Успех первой публикации не означает завершение полного MVP.
