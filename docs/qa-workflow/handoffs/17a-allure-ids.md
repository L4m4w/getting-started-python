# Передача результата: закрепление ALLURE_ID в API-тестах CAT-UPD-VAL

Агент: `17A`. Дата: 2026-11-15. Статус: `ready`.

Каждый из шести параметризованных сценариев CAT-UPD-VAL теперь при выполнении
получает ровно один собственный label `ALLURE_ID` с согласованным TestOps ID
(wave 12/13, проект 5444, подтверждено сервером). Изменена только маркировка:
значения параметров, node IDs, assertions, fixtures, cleanup и HTTP-поведение
не тронуты. API/SUT-прогон, bind-пакет и публикация — следующие части поручения
17 (17B/17C), здесь не выполнялись.

## Согласованные пары (источник: wave 12/13, testops-mapping.md)

| Scenario | TestOps ID |
| --- | --- |
| CAT-UPD-VAL-001 | 55376 |
| CAT-UPD-VAL-002 | 55374 |
| CAT-UPD-VAL-003 | 55375 |
| CAT-UPD-VAL-004 | 55377 |
| CAT-UPD-VAL-005 | 55373 |
| CAT-UPD-VAL-006 | 55378 |

## Реализация

- `test_data/consts/category_update.py`: новый `TESTOPS_ALLURE_IDS`
  (scenario ID → case ID, строки) и производный `TESTOPS_ALLURE_ID_BY_NAME`
  (значение параметра `name` → `ALLURE_ID`). Сценарий определяется значением
  `name` — то же правило, что у `_match_scenario`/`_scenario_index` в
  `infrastructure/reporting/testops/results.py` и `tools/testops.py`;
  расхождение разметки и маппинга пакета исключено по построению.
- `tests/api/test_category_update.py`: первым шагом каждого теста
  `with allure.step("Привязать сценарий к кейсу TestOps")` вызывается
  `allure.dynamic.label("ALLURE_ID", TESTOPS_ALLURE_ID_BY_NAME[name])`.
  Runtime-разметка оформлена шагом по AGENTS.md. Незнакомое значение `name`
  даёт `KeyError` — метка не теряется молча.
- `allure.dynamic.label` пишет в текущий test result label
  `{"name": "ALLURE_ID", "value": "..."}` — то же имя, что использует
  `rewrite_result` (`ALLURE_ID_LABEL`) при bind-упаковке. Один статический
  `@allure.id` на функцию не применялся (недопустим для параметризации).
- `knowledge/components/consts.md`: запись API-пилота дополнена новыми
  константами и примером использования.

## Проверки (все локальные, без SUT/сети/TestOps/Docker/Gradle)

| Команда | Exit | Итог |
| --- | --- | --- |
| `sh tools/compile-tests.sh` | 0 | 248 tests collected |
| `pytest tests/api/test_category_update.py --collect-only -q` | 0 | 6 node IDs прежние: `...[CAT-UPD-VAL-001]`–`[006]` |
| `sh tools/run-tests.sh list` | 0 | те же шесть node IDs в общем списке |
| `pytest <probe> --alluredir <evidence>` | 0 | 6 passed |
| `check_probe_labels.py <probe-allure-results>` | 0 | 6/6 сценариев, ровно один верный ALLURE_ID у каждого |
| `sh tools/run-tests.sh group unit` | 0 | 233 passed, 0 failed (`artifacts/harness/run-f6rmfrdj/`) |
| `git diff --check` | 0 | чисто |

Проверка сериализации: временный пробник
`artifacts/final-execution/17a-20261115T120520Z/probe_testops_allure_ids.py`
переиспользует механизм разметки (те же константы, тот же вызов
`allure.dynamic.label` внутри `allure.step`) и параметризован теми же
`INVALID/VALID_NAMES`/`IDS`, но не требует API-фикстур и не обращается к SUT.
В его свежих `*-result.json` проверено: у каждого результата ровно один label
`ALLURE_ID`, значения — 55376/55374/55375/55377/55373/55378 по сценариям,
лишних/чужих результатов нет (`probe-verification.txt`). Это проверка
механизма маркировки, а не выполнение API-тестов: реальные PATCH/GET,
fixtures и cleanup не запускались и проверяются финальным execution в 17B/C.

## Изменённые файлы и их SHA-256

| Файл | До | После |
| --- | --- | --- |
| `tests/api/test_category_update.py` | `455ee750…` | `ebd9deaa…` |
| `test_data/consts/category_update.py` | `dc8b900d…` | `c66a9a9f…` |
| `knowledge/components/consts.md` | `bce99012…` | `a1f203a3…` |

Полные SHA-256: `before.sha256`/`after.sha256` в evidence-каталоге; точные
diff — `diff-*.patch` (оба python-файла untracked, поэтому diff снят копиями
до/после). Оба файла пилота входят в `api-contract-v1` — их новые хеши
ожидаемо отличаются от исторического контракта прогона `run-5tsmzg1d`;
версия контракта не менялась.

## Evidence

`artifacts/final-execution/17a-20261115T120520Z/` (gitignored):
`before/` (копии до правки), `before.sha256`, `after.sha256`,
`diff-test_category_update.patch`, `diff-category_update.patch`,
`diff-consts-md.patch`, `probe_testops_allure_ids.py`,
`check_probe_labels.py`, `probe-allure-results/`, `probe-verification.txt`.
Дополнительно unit-прогон: `artifacts/harness/run-f6rmfrdj/`.

## Не выполнялось / ограничения

- Реальный API-прогон с новой разметкой, environment/source identity,
  cleanup и post-down evidence — задание 17B/C; здесь нет.
- plan/assign/package нового execution и любые операции TestOps не
  выполнялись; исторические результаты и state `run-5tsmzg1d` не трогались.
- Пробник подтверждает сериализацию метки механизмом; появление `ALLURE_ID`
  в исходных result JSON финального прогона 17B проверяет отдельно
  (ручной дописки ID в result JSON нет и не будет — метки ставит тест).
- `tools/testops.py`, `results.py`, fixtures, conftest, harness не менялись;
  при bind-упаковке `rewrite_result` перезапишет label тем же согласованным
  ID — конфликта нет.
