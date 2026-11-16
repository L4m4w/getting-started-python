# Приёмка публикации 16C и согласование bindings

Дата: 2026-11-15. Публикация и close приняты. До завершения этапа 16
остаются штатные assign и REST verify; текущий persisted status — sent.

## Результат исполнителя

[16C live](16c-testops-publication-live.md) создал launch **57316**,
отправил согласованный isolate-пакет и закрыл launch. Шесть кейсов
созданы сервером. Первая отправка — exit 0/sent, оба REST verify —
exit 75/inconclusive из-за несогласованных bindings. Исполнитель корректно
остановился перед assign. Evidence:
`artifacts/testops-live/16c-publication-20261115T114539Z/`.

Launch: [57316](https://allure.qa.guru/launch/57316), project 5444,
`CAT-UPD-VAL run-5tsmzg1d pilot16-20261115`.
Execution `run-5tsmzg1d`, attempts=1, mode isolate,
package SHA-256
`a6f1cdddabfa460897b28fb8bd22cbe46bc0e6687489e61f86cbbfaf5e6e87ec`.

Исполнитель проверил повтор upload: exit 69 до транспорта, attempts,
state/log SHA и серверный набор неизменны по его отчёту. Координатор
этот вызов не повторял. Уточнение отчёта: create, upload и close — три
операции записи; две верхнеуровневые команды. Фраза «write-вызовов ровно
два» не означает только два HTTP write-запроса. Число HTTP-запросов
внутри upload не измерялось. Текущий upload.log содержит также read_snapshot,
поэтому он не ограничивается двумя строками create/upload.

## Собственная проверка координатора

Прочитаны handoff, mapping-candidates, state, upload.log, журнал close
и ожидания. Текущий пакет повторно проверен `_validate_upload_package`.
UUID кандидатов совпали с state; шесть разных case IDs совпали с
последним сохранённым confirmation. Исходники, mapping и пакет целостны.

Выполнен **собственный read-only RestProbe snapshot** записанного launch
2026-11-15 11:50:06 UTC (14:50:06 Europe/Volgograd):

- outcome complete; project/launch совпадают, closed=true, ready=true;
- pagination complete, 1 страница, 6 результатов, matched 6/6;
- statistic passed=6, missing=[], foreign=0;
- problems/anomalies/incomplete пусты;
- реальные case IDs совпали с кандидатами исполнителя.

Без bindings evaluate_snapshot дал inconclusive; с согласуемыми ниже
bindings **только в памяти** — confirmed. State на диске не изменялся,
SHA `8ec2b687ce47cfad0cd60520f2b4468c44ce7377e6cc4dd096ec2eb0207ecc2e`.
Это не перевод persisted state в uploaded.

Evidence координатора:
`artifacts/testops-live/coordinator-16-review-20261115T115006Z/`
(`snapshot.json`, `review.json`). Snapshot — нормализованный allowlist
RestProbe без credentials, параметров, тел тестов и вложений.

Первая сетевая попытка из sandbox дала token_exchange transport error;
повтор с разрешённым сетевым доступом прочитал snapshot. В первой
координаторской проверке допущена ошибка сигнатуры evaluate_snapshot;
исправленный вызов завершился exit 0. Исходники/state не изменялись,
ошибка не затронула отправку. Внешних write-вызовов координатор не делал.

## Решение о bindings

Как координатор **согласовываю** следующие шесть пар для локального assign
в execution `run-5tsmzg1d` и последующего REST verify launch 57316:

| Scenario | TestOps ID |
| --- | --- |
| CAT-UPD-VAL-001 | 55376 |
| CAT-UPD-VAL-002 | 55374 |
| CAT-UPD-VAL-003 | 55375 |
| CAT-UPD-VAL-004 | 55377 |
| CAT-UPD-VAL-005 | 55373 |
| CAT-UPD-VAL-006 | 55378 |

Основание: текущий полный серверный набор, точные scenario-префиксы,
статусы, project/launch и отсутствие аномалий; кандидаты совпадают
с ранее полученными исполнителем per-case проверками. Исходные
поручения разрешают согласование bindings пользователем **или координатором**.
Дополнительного согласования пользователя для этих пар не требуется.

Исполнителю передаётся [завершение 16C](../agent-tasks/16c-testops-finalize.md).
Не пересобирать/не отправлять пакет, не создавать/не закрывать launch
повторно, не менять API-код и исторические evidence. Свежий verify после
assign должен подтвердить uploaded штатным lifecycle, без ручного status.

Координатор агентов не запускал. `git diff --check` и локальные ссылки — OK.
Unit/collection не повторялись, код не менялся. Финальный execution
с закреплёнными ID, Git/PR, оркестратор и полный MVP остаются отдельно.
