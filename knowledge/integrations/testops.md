# Allure TestOps: план, привязка и загрузка результатов

Целевой проект: `https://allure.qa.guru/project/5444` (значения по умолчанию:
`ALLURE_ENDPOINT`/`--endpoint`, `ALLURE_PROJECT_ID`/`--project-id`).
Точка входа — `sh tools/run-testops.sh <action> ...` → `tools/testops.py`.
Внешние вызовы выполняет установленный `allurectl` (проверено на 2.24.0;
поиск: `--allurectl` → env `ALLURECTL` → PATH → `~/.local/bin/allurectl`).
CLI загружает корневой `.env` через python-dotenv без переопределения
экспортированных значений. Секрет — `ALLURE_TOKEN` из окружения процесса; он не печатается, не
передаётся аргументом и не сохраняется в state/evidence/документах.

## Модель идентичности: шесть кейсов из двух функций

allure-pytest 2.16 считает `testCaseId = md5(fullName)`, а `fullName`
намеренно не зависит от параметров: у шести параметров пилота только две
сигнатуры. TestOps связывает результат с кейсом по label `ALLURE_ID` либо
по полной сигнатуре; сырой пакет имеет только два testCaseId. Фактическое создание кейсов
и серверная дедупликация пока живым upload не проверены. Поэтому загружается **копия** результатов
(`upload-results/` внутри каталога состояния), где каждому результату
присваивается сценарная сигнатура: `name` с префиксом `CAT-UPD-VAL-00X:`,
`fullName` с суффиксом `[CAT-UPD-VAL-00X]`, пересчитанные `testCaseId`/
`historyId`, а в режиме `bind` — label `ALLURE_ID` с ID существующего кейса.
Исходные `allure-results` прогона не изменяются.

Соответствие результат → сценарий выводится из `fullName` и значения
параметра `name` (`ast.literal_eval` repr-строки) по константам
`test_data.consts.category_update`. Незнакомые результаты помечаются
`unmapped` и блокируют сборку пакета — случайного объединения нет.

## Офлайн-поток

```sh
sh tools/run-testops.sh plan --results artifacts/harness/run-XXXX/allure-results
sh tools/run-testops.sh status --execution run-XXXX
sh tools/run-testops.sh assign --execution run-XXXX CAT-UPD-VAL-001=12345 ...
sh tools/run-testops.sh package --execution run-XXXX --mode bind
sh tools/run-testops.sh package --execution run-XXXX --mode isolate
```

`plan` обновляет `artifacts/testops/<execution>/state.json` (schema 2):
идентичность результатов (sha256, число файлов), сценарии и привязки,
пакет, launch, состояние upload. Повторный `plan` сохраняет привязки и
прогресс, сущностей не создаёт. `package` пишет только локальную копию:
`bind` требует всех шести ID (нет — 69), `isolate` строит пакет без ID
для первичного авто-создания кейсов при разрешённой загрузке.

## Внешние операции (только по явному поручению)

```sh
sh tools/run-testops.sh resolve --execution run-XXXX --online
sh tools/run-testops.sh verify --execution run-XXXX --online --transport allurectl
sh tools/run-testops.sh verify --execution run-XXXX --online --transport rest
sh tools/run-testops.sh upload --execution run-XXXX --execute [--retry] [--launch-name N]
```

`resolve --online` выполняет read-only `allurectl test-case list -o json
-q 'name ~= "CAT-UPD-VAL"'`: одно совпадение по сценарному префиксу —
привязка; ноль — `unresolved`; два и более — `ambiguous` без выбора;
пустой результат разрешай через `assign`. `verify --online` — read-only
`launch get` и доступные дополнительные read-only проверки; без доказательства
полного набора результат остаётся неопределённым. `upload --execute` создаёт launch
(`launch create`), затем `upload --launch-id`; лог — `upload.log` в
каталоге состояния. Ни одна из команд не выполняет запись без `--execute`
и не обращается к сети без `--online`; обе требуют `ALLURE_TOKEN` (иначе 69).

## Целостность и повторы

- `plan` строго разбирает result JSON: повреждение, отсутствие UUID и
  дубли UUID блокируют операцию. Незнакомый сценарий отмечается unmapped.
- `package` сверяет input digest с планом, соответствие всех результатов
  mapping, attachments (в том числе fixture/step), затем собирает пакет
  через временный каталог. Сохраняются input/mapping/package SHA-256.
- До upload CLI под общей execution-блокировкой повторно сверяет source,
  mapping/bindings и пакет. Старый пакет без этих метаданных требует
  пересборки. После начала внешних попыток пересборка запрещена.
- Все команды CLI используют одну ExecutionLock на execution; upload
  держит её от загрузки state до последнего сохранения. POSIX flock-gate
  сериализует захват и очистку lock мёртвого процесса. Файл gate остаётся
  на диске; его наличие не означает занятую блокировку.
- `pending` → `in_progress` сохраняется до внешнего вызова.
  Exit 0 upload даёт `sent`, а не `uploaded`: обработка ещё не доказана.
- `sent`, `unknown`, `in_progress`, `uploaded` блокируют повторную отправку.
  Timeout, прерывание, нечитаемый ответ create и ненулевой exit create/upload
  дают unknown: внешняя запись могла состояться.
- `failed` оставлен для доказанного сбоя запуска процесса до записи.
  Только он допускает --retry; записанный launch при этом используется снова.
- `verify` проверяет launch ID, проект, статистику и per-result bindings.
  Одного существования launch недостаточно. Нулевая статистика может быть
  задержкой обработки: статус не становится retry-safe failed.
- Транспорт allurectl 2.24.0 (по умолчанию) не имеет per-result чтения:
  verify остаётся inconclusive без полной проверки bindings.
- Явный `verify --online --transport rest` использует RestProbe и
  perform_snapshot_verify: token exchange, launch/progress/statistic,
  строгие страницы results и повторное чтение launch. REST verify
  не требует установленного allurectl; upload по-прежнему использует его.
- Перед обоими verify CLI сверяет source/mapping/package и SHA пакета
  записанной отправки; нужен записанный launch, --launch-id его не заменяет.
- REST confirmed требует closed=true, ready=true, полной пагинации,
  точного набора/статусов/project/launch/case bindings, без hidden/retries
  и дублей. Isolate выдаёт кандидатов ID, но до согласования bindings
  не подтверждает uploaded. Empty/partial/contradiction не разрешают resend.
- Эти проверки покрыты offline; непустой live launch ещё не проверен.
  API-схемы основаны на сохранённом OpenAPI 527u01, а не на положительном
  upload. Если сервер иначе опускает/формирует поля, verify остаётся
  inconclusive до отдельной диагностики.
- Ручное подтверждение возможно через state API только после отдельной
  UI-сверки всех результатов и привязок. CLI не предоставляет команды,
  которая объявляет такую сверку выполненной без доказательств.
- Повреждённый state блокирует операцию без перезаписи. Schema 1
  мигрирует в памяти: failed → unknown (даже без launch), unknown и
  in_progress сохраняются, uploaded остаётся терминальным с пометкой
  migrated — это не новое серверное подтверждение. На диск миграция
  записывается при следующем успешном save; массовой миграции не было.
- После попытки нельзя подменить исходный execution другими результатами.
  Новый фактический прогон — новый execution ID. Сбой TestOps тесты не запускает.

Восстановление после неизвестного исхода — отдельное поручение с проверкой
launch через read-only API/UI. `resolve_in_progress`, `adopt_launch` и
`mark_upload_confirmed` в state.py — низкоуровневые операции, не команды
для обхода блокировок. Существующие состояния не сбрасывать/не удалять.

Коды CLI: 0 — локальная операция успешна либо batch отправлен (sent),
2 — argparse, 69 — блокировка/противоречие, 75 — неопределённый результат
или неполная проверка, 127 — процесс не запустился, 130 — прерывание.
Лог upload содержит только UTC/операцию/exit/error; сырые ответы инструмента
не записываются. Exit 0 upload не доказывает обработку на сервере.

## Ограничения

- `isolate` создаёт автоматические кейсы с сигнатурами пакета; устойчивая
  связь закрепляется `ALLURE_ID` после разрешения ID.
- `ALLURE_ID` обязан существовать заранее: несуществующий ID делает
  результат «осиротевшим» (по документации TestOps), поэтому `bind` без
  подтверждённых ID заблокирован.
- Разбор вывода `allurectl` защитный (`-o json`, обёртки `content`/`items`);
  формат проверен только на 2.24.0 без живого запроса.
- Запись `testCaseId` кейса при загрузке — семантика TestOps; при смене
  сигнатуры возможны новые кейсы, поэтому долгосрочная привязка — через
  `ALLURE_ID` в коде тестов (patch proposal в handoff 11).
