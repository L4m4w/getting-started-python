# Приёмка 18A/18B — готовность финальной bind-публикации

Дата: 2026-11-15. **18A/18B приняты координатором.**
Документированная приёмка для 18C предоставлена. Осталось отдельное
разрешение пользователя на конкретную публикацию и close.
Этапы 16/17 закрыты; этап 18 ещё не выполнен.

## Приёмка исполнителей

- [18A](18a-package-preflight.md): read-only локальная проверка source,
  mapping, пакета, manifest/JUnit/копий, backup и неизменности старых state.
  Принято; ready не является разрешением upload.
- [18B](18b-server-preflight.md): targeted read-only server preflight,
  per-case проверки и REST inventory с page metadata. Принято.
- [18C](18c-bound-publication.md): корректно остановился до write, поскольку
  не было этой приёмки и отдельного разрешения публикации. Предыдущий
  handoff остановки сохранить как исторический, не перезаписывать.

18B evidence `artifacts/testops-preflight/18b-20261115T122510Z/` проверен
координатором по case-inventory.json, case-checks.json, launch-search.json,
old-launch-57316.json. Снимок 12:28:36–41 UTC (15:28:36–41 Europe/Volgograd):

- REST testcase Page: 1 страница, totalElements=6, totalPages=1, last=true,
  полный набор ID 55373–55378, неожиданных пилотных ID нет;
- отдельные GET всех шести кейсов: HTTP 200, projectId=5444,
  returned IDs и точные scenario-префиксы совпадают;
- REST launches Page: 1 страница, totalElements=1, last=true,
  только старый launch 57316; нового execution/target name не найдено;
- старый launch 57316 closed/ready, statistic passed=6.

Полнота этого маленького снимка подтверждается REST page metadata,
а не bare array CLI. В testcase list projectId не возвращался в элементах:
принадлежность шести ID подтверждена per-case GET. Серверной snapshot
isolation нет; 18C повторяет preflight непосредственно перед записью.
Это измерения 18B; собственных сетевых вызовов координатор не выполнял.

## Собственная локальная проверка координатора

`_validate_upload_package` — OK. State байт-идентичен backup 18A и wave 15:
schema 2, bind, pending, attempts=0, launch=null, history=[], upload.log нет.
Шесть назначенных ID совпадают с согласованным mapping. Старый uploaded
state run-5tsmzg1d не изменён. Ни state, ни пакет не пересобирались/не сохранялись.

Проверка завершилась exit 0. Evidence:
`artifacts/testops-preflight/coordinator-18-20261115T123308Z/review.json`.
`git diff --check` и локальные Markdown-ссылки — OK. Unit/collection,
SUT/API/UI/Docker/Gradle, commit/push/PR координатором не выполнялись.
Агенты не запускались.

## Входы публикации и открытая контрольная точка

| Поле | Принятое значение |
| --- | --- |
| execution | `run-ni_5bvnc` |
| endpoint / project | `https://allure.qa.guru` / `5444` |
| mode / results | bind / шесть passed |
| package SHA-256 | `1e1f643257c2289be3add60c47ab10e749b289e3d0f8920d3acf060f488d05a7` |
| state SHA-256 | `1b3a7762d83a6abffb337e8a55d351db3372af6f47f0e8aee77847d99e6ae1d2` |
| launch name | `CAT-UPD-VAL run-ni_5bvnc final17-20261115` |

Bindings уже согласованы и повторного решения не требуют:
001→55376, 002→55374, 003→55375, 004→55377, 005→55373, 006→55378.

Предлагается разрешить **одну** штатную первую публикацию этого пакета,
создание одного нового launch внутри CLI upload и close только
записанного нового launch при необходимости:

```sh
sh tools/run-testops.sh upload --execution run-ni_5bvnc --execute --launch-name 'CAT-UPD-VAL run-ni_5bvnc final17-20261115'
allurectl --endpoint https://allure.qa.guru -o json launch close <recorded-launch-id>
```

Старый launch 57316 не использовать и не менять. Новый upload не покрыт
разрешением 16C. Данное решение координатора **не предоставляет**
разрешение на внешнюю запись от имени пользователя.

После отдельного разрешения 18C продолжает то же поручение целиком:
свежий preflight/integrity → один upload → close при необходимости →
read-only ожидание/REST verify до confirmed/uploaded → сравнение inventory
кейсов → проверка локальной блокировки повторной отправки и terminal verify.
Новых согласований тех же входов/bindings не требуется.
Unknown/nonzero/timeout не разрешают автоматический retry/adoption/recovery.

Новый итоговый handoff — `docs/qa-workflow/handoffs/18c-bound-publication-live.md`,
новый уникальный evidence `artifacts/testops-live/18c-<UTC>/`.
Остальные ограничения исходного [задания 18](../agent-tasks/18-bound-publication.md)
и промпта 18C сохраняются. При новых конфликтах/расхождении SHA —
диагностика и точный блокер; при прежних входах не запрашивать приёмку снова.
