# 16B — read-only preflight TestOps и контракт публикации

Ты — исполнитель 16B. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Работай самостоятельно, других агентов не запускай.

Прочитай `AGENTS.md`, `knowledge/integrations/testops.md`, handoffs
`14a-testops-access-cases.md`, `14b-testops-results-contract.md`,
`coordination-wave-8.md`, `coordination-wave-9.md`,
`coordination-wave-10.md` в `docs/qa-workflow/handoffs/`,
`docs/qa-workflow/agent-tasks/16-testops-first-publication.md` и текущие
`tools/testops.py`, `infrastructure/reporting/testops/{client,lifecycle,rest}.py`.
Общее задание 16 используй как контекст: выполняй только часть этого промпта.

Разрешены целевые read-only обращения к `https://allure.qa.guru/`,
проект **5444**, имя `ai_project_Larkin_EA`, изучение официальной
документации и локальные version/help. Внешняя запись не разрешена.

Разрешённая локальная запись:

- новый уникальный `artifacts/testops-preflight/16b-<UTC>/`;
- `docs/qa-workflow/handoffs/16b-testops-live-preflight.md`.

Не меняй и не блокируй `artifacts/testops/`: там параллельно работает 16A.
Не вызывай CLI plan/status/package/resolve/verify: они используют общий
state/lock, resolve также сохраняет bindings. Для сетевых чтений используй
существующие read-only client/probe через отдельный сценарий в своём evidence,
без сохранения общего execution state. Не меняй код/README/общие документы.

Порядок работы:

1. Загрузи `.env` через `tools.testops.load_environment()` без вывода токена.
   Exported env имеет приоритет: проверь эффективные endpoint/project,
   несовпадение с заданием сообщи как блокер. Не выводи/не копируй токен/JWT,
   не передавай argv, не сохраняй headers и сырые ответы, не включай debug
   или shell tracing. Token exchange допустим для read-only доступа.
2. Повтори целевой project get, поиск CAT-UPD-VAL-001–006 и launches
   только проекта 5444. Проверь полноту выдачи/пагинацию и точную границу ID.
   Не перечисляй чужие проекты. Старые пустые ответы 14 не считай актуальными.
   При непустой выдаче сохраняй только сведения о пилоте и полноте поиска.
3. Дай по каждому сценарию verdict: отсутствует / один кандидат /
   неоднозначность / недостаточно данных. Найденные case IDs остаются
   кандидатами; bindings не назначай. Частичный набор, следы предыдущей
   публикации или неполный поиск требуют решения координатора.
4. Проверь установленный allurectl: version, SHA бинаря, help для
   launch create, upload и launch close. Сопоставь фактические аргументы
   с client.py. Подтверди, как upload использует существующий launch ID,
   может ли автоматически закрыть launch, когда допустим close и как
   read-only проверить его исход. Не выполняй write-команды даже ради пробы.
   Если синтаксиса/help недостаточно, изучи официальную документацию или
   Swagger целевого инстанса. Не выдумывай команды/REST write endpoint.
5. Составь точный план одной публикации через штатный lifecycle:
   CLI upload создаёт launch сам, отдельный create перед ним не нужен;
   один пакет, шесть результатов, один launch. Укажи подтверждённую команду
   close, порядок ожидания обработки и live REST verify. Неподтверждённые
   права записи и семантику сервера явно оставь непроверенными.
6. Составь recovery-матрицу: create без записанного ID, upload timeout/nonzero,
   sent с задержкой обработки, empty closed/ready, неизвестный close.
   Для каждого случая укажи read-only диагностику и условие остановки.
   Unknown/in_progress/sent/uploaded блокируют resend; empty не разрешает
   retry. Adoption/recovery API не применяй; отдельный execution для обхода
   state не предлагай. Только доказанный failed до записи допускает
   рассмотрение retry в отдельном поручении.

Результат: handoff ready / blocked / needs_decision, UTC, версии,
безопасные команды/exit/HTTP codes, формат и полнота выдачи, кандидаты ID,
рекомендация isolate/bind, точный upload/close/recovery план и ограничения.
Не обещай шесть серверных кейсов по offline-пакету. Сохраняй только
allowlist metadata, без чужих сущностей и пользовательских данных.

Запрещены create/upload/close/watch, любые изменения кейсов/launches,
общего state, API/UI, Docker/Gradle, commit/push/PR, переключение/reset
checkout. Все чужие изменения сохраняй. Выполни `git diff --check`;
unit/collection не повторяй без изменения реализации.
Передай результат координатору; сам к публикации не переходи.
