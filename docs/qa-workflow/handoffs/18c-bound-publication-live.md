# 18C: публикация финального bind execution run-ni_5bvnc

Агент: `18C`. Дата: 2026-11-15. Статус: **ready** — публикация
подтверждена свежим REST snapshot и сохранена как `uploaded`.

Основание: приёмка 18A/18B в
[coordination-wave-16.md](coordination-wave-16.md) и отдельное
разрешение пользователя в текущей сессии на **одну** публикацию
execution `run-ni_5bvnc` (package SHA `1e1f6432…`, новый launch
`CAT-UPD-VAL run-ni_5bvnc final17-20261115`) и close только
записанного нового launch. Прежний handoff остановки
[18c-bound-publication.md](18c-bound-publication.md) сохранён без
изменений. Повторного согласования входов/bindings не требовалось.

## Итог

| Поле | Значение |
| --- | --- |
| execution | `run-ni_5bvnc` |
| endpoint / project | `https://allure.qa.guru` / `5444` (`ai_project_Larkin_EA`) |
| mode / results | bind / 6 passed |
| package SHA-256 | `1e1f643257c2289be3add60c47ab10e749b289e3d0f8920d3acf060f488d05a7` |
| launch | **57317** — https://allure.qa.guru/launch/57317 |
| launch name | `CAT-UPD-VAL run-ni_5bvnc final17-20261115` |
| upload | `sent` → REST confirmed → persisted **`uploaded`**, attempts=1 |
| bindings | 001→55376, 002→55374, 003→55375, 004→55377, 005→55373, 006→55378 — подтверждены сервером |

## Шаг 1 — свежий preflight (read-only)

- Локально: state.json sha256 `1b3a7762…` = записи wave 15/16;
  `_validate_upload_package` PASS (source/mapping/package digests);
  `decide_upload` → allowed; upload `pending`, attempts=0.
- Серверный probe (копия read-only probe 18B), окно
  12:36:00–12:36:06Z → `PREFLIGHT_OK`: проект 5444 OK; REST testcase
  page-walk полный (1 страница, totalElements=6, last=true) — только
  ожидаемые шесть ID; все per-case GET совпали; launches page-walk
  полный — только старый launch 57316; совпадающего имени launch нет.
- Backup: `state-before-upload.json`, `originals.sha256`,
  `package-files.sha256` (40 файлов).

## Шаг 2 — единственный upload

```sh
sh tools/run-testops.sh upload --execution run-ni_5bvnc --execute --launch-name 'CAT-UPD-VAL run-ni_5bvnc final17-20261115'
```

- 12:36:18.329–12:36:23.488Z, exit 0 → `sent`, launch 57317.
- upload.log: `launch_create exit=0`, `upload exit=0`.
- Пакет не пересобирался; `upload.package_sha256` = согласованный SHA.

## Шаг 3 — проверка launch и один close

- Read-only `GET /api/launch/57317`: HTTP 200, projectId=5444, имя
  согласованное, `closed=false` → выполнен один согласованный close.
- Первая попытка `allurectl launch close` из shell завершилась exit 1
  **client-side** (`provide token`): `ALLURE_TOKEN` не был в env
  shell; серверной записи не было. Тот же согласованный close повторён
  через `client.run` (токен из `.env`, наследование env) → exit 0,
  «Tests results have been processed. Launch can be closed.»
- Read-only перечитывание: `closed=true`, `ready=true`,
  statistic `{passed: 6}`. Обработка завершилась до ожидания —
  10-минутный цикл не потребовался.

## Шаг 4/5 — REST verify → uploaded

```sh
sh tools/run-testops.sh verify --execution run-ni_5bvnc --online --transport rest
```

- 12:37:02Z, exit 0, `verdict=confirmed launch=57317`.
- Confirmation checks: launch_id_match, project_match, closed, ready,
  pagination complete (1 страница), rows_count=6, все шесть сценариев
  matched, missing=[], foreign=0, stats {passed:6} consistent,
  problems/anomalies/incomplete пусты, case bindings точные.
- Persisted state: `uploaded`, attempts=1; state sha `7bec44e1…`.

## Шаг 6 — инвентарь после публикации

- REST testcase page-walk: totalElements=6, last=true — **новых
  пилотных кейсов нет**; набор ID = ровно {55373..55378}.
- Launches page: totalElements=2 — новый 57317 и старый 57316
  (closed/ready, passed:6, имя и проект прежние).
- Старые execution не изменены: `run-5tsmzg1d` state `6da44722…`,
  upload.log `2218988…`; `run-vzsatlfk` state `001c99ba…` — совпадают
  с backup до публикации.

## Шаг 7 — локальная блокировка повторной отправки

- `decide_upload` → `allowed=False`: «upload already confirmed for
  this execution; it is never re-sent».
- Повтор той же upload-команды: **exit 69 до транспорта**
  (`BLOCKED: upload already confirmed`). После вызова state sha
  `7bec44e1…` и upload.log sha `0f40d658…` неизменны; attempts=1,
  launch, package SHA прежние.

## Шаг 8 — повторный verify (терминальное подтверждение)

- `verify --online --transport rest` → exit 0, `verdict=confirmed`,
  «upload already confirmed; terminal state». Новый HTTP snapshot не
  выполнялся: upload.log не получил записей (sha `0f40d658…` до и
  после), `read_snapshot` остался единственным от 12:37:04Z.

## Команды и exit codes

| Шаг | Команда | Exit |
| --- | --- | --- |
| integrity | `_validate_upload_package`, `decide_upload` | PASS / allowed |
| server preflight | `.venv/bin/python artifacts/testops-live/18c-20261115T123552Z/probe.py` | 0 `PREFLIGHT_OK` |
| upload | `sh tools/run-testops.sh upload --execution run-ni_5bvnc --execute --launch-name 'CAT-UPD-VAL run-ni_5bvnc final17-20261115'` | 0, sent, launch 57317 |
| launch check | `GET /api/launch/57317` (read-only) | 200 |
| close (shell) | `allurectl -o json launch close 57317` | 1, client-side, без записи |
| close (агreed) | `client.run launch close 57317` | 0 |
| verify | `sh tools/run-testops.sh verify --execution run-ni_5bvnc --online --transport rest` | 0, confirmed |
| post-inventory | REST testcase/launch page walk | 200, полный |
| блокировка | повторная upload-команда | 69 до транспорта |
| терминальный verify | повторная verify-команда | 0, stored confirmation |
| гигиена | `git diff --check` | 0 |

## Evidence

`artifacts/testops-live/18c-20261115T123552Z/` (gitignored):

- `state-before-upload.json`, `state-after-upload.json`,
  `state-after-verify.json`, `originals.sha256`, `state-final.sha256`,
  `package-files.sha256` — backup и digest-дорожка state/пакета.
- `probe.py`, `summary.json`, `project.json`, `allurectl.json`,
  `case-inventory.json`, `case-checks.json`, `launch-search.json`,
  `old-launch-57316.json` — свежий server preflight (allowlist only).
- `local-integrity.txt`, `upload-attempt1.log`,
  `close-attempt1.journal`, `launch-57317-check.json`,
  `launch-57317-closed.json`, `post-publish-inventory.json`,
  `upload-log-final.txt` — журнал попыток и read-only снимки.

## Ограничения

- Права записи токена подтверждены фактом create/upload/close этого
  launch; иных scope токен не проверялся.
- Полнота инвентаря доказана REST page metadata (`last=true`,
  `totalElements`), не длиной bare array CLI.
- Подтверждён публикацией именно этот execution; полный MVP
  (Git/PR, оркестратор, идемпотентность) остаётся оценкой координатора.
- Секреты/JWT/headers в evidence не сохранялись; upload.log — только
  операция/exit/UTC.
