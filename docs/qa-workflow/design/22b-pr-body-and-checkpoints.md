# 22B — durable PR body payload и checkpoint читаемого create number

Дата: 2026-11-16 (UTC). Исполнитель: 22B. Документ описывает решение в
назначенной области (`infrastructure/workflow/adapters.py`,
`infrastructure/workflow/orchestrator.py`); это не отчёт о приёмке и не
разрешение Git/PR-этапа. Общий контракт:
[22 — общий интерфейс](22-pr-transport-interface.md).

## Body: канонизация и точные bytes

`pr_prepare` читает `--body-path` файл как сырые bytes и декодирует
UTF-8 — **без trim и без преобразования переводов строк**. Невалидный
UTF-8 и отсутствующий файл — `WorkflowValidationError` на prepare, spec
не записывается.

Канон для **новых** spec:

| Вход | `body_text` | `body_sha256` |
| --- | --- | --- |
| absent (`body_path=None`) | `None` | `None` |
| пустой файл | `None` | `None` |
| непустой текст | текст verbatim | `sha256(utf8_bytes)` |

Digest считается по bytes **исходного файла** (они же bytes текста —
UTF-8 round-trip гарантирован decode'ом). CRLF и Unicode сохраняются
дословно; `PrSpec.body_text` — поле для transport 22A, который POST'ит
именно этот текст.

## Durable payload snapshot и привязка

Для непустого body prepare атомарно пишет snapshot
`payloads/pr-<role>-body-<sha16>.txt` **внутри workflow dir** (не в
`artifacts/` и не в рабочем checkout): temp-file + fsync + `os.replace`
(`_write_payload`). Запись идемпотентна — повторный prepare с тем же
digest перезаписывает теми же bytes.

В spec (и в frozen `intent.target.spec`) записывается цепочка:

- `body_source = {"path": <abs source>, "sha256": digest}` —
  идентичность файла на момент prepare;
- `body_snapshot = {"path": <rel в workflow dir>, "sha256": digest}`;
- `body_text`, `body_sha256` как выше.

Body — иммутабельный вход, привязанный к spec/intent. После prepare
оркестратор не перечитывает произвольный текущий файл ради body.

## Digest gates до dispatch

`pr_create` вызывает `_body_payload_problems(workflow_dir, spec)` —
**после** head-commit guard, re-prove `created` и lineage-reprove, но
**до** fresh `search` и любого POST. Проблемы переводят entry в
`blocked` (exit 69) без единого remote-вызова:

- `body_text` хешируется не в `body_sha256` (tampered spec);
- записан digest, но `body_text` пуст/отсутствует;
- snapshot не записан, путь выходит за workflow dir, файл потерян или
  его digest ≠ записанному;
- source-файл потерян или его digest ≠ записанному на prepare.

**Legacy spec** (без ключа `body_text`): digest=None — допустимо
отсутствие body; непустой digest без восстановимого текста — blocked,
body не угадывается и spec/intent не переписывается молча. Разблокировка
— только осознанный re-prepare по действующим guards.

Замечание по семантике `blocked`: идентичный re-prepare — честный
no-op по `spec_sha256` (payload при этом перезаписывается и потерянный
snapshot восстанавливается на диске), но `blocked` не снимается молча —
нужен re-prepare, дающий новый spec. Это сохраняет правило «blocked
требует явного разрешения» для всех причин блока, а не только для body.

## Checkpoint читаемого create number

`_dispatch_pr_create` после возврата transport'ом читаемого ref
(непустой `number`) делает две записи:

1. **save #1 — до verification GET**: `entry.status="created"`,
   `number`, `url`; intent → `completed` с evidence
   `{"outcome": "created", "number", "url", "verified": null}`.
   Граница crash: после POST с читаемым номером remote effect уже
   durable; потерянный save оставляет ранее записанный `dispatched`
   intent, который запрещает retry до reconcile.
2. `_verify_pr` — commit/tree guards + targeted `get(repo, number)` +
   `pr_ref_exact`; **save #2** дописывает `verified` в evidence и
   `entry.status="verified"` при успехе.

Crash между save #1 и verify (включая `KeyboardInterrupt` внутри GET):
durable `created` + `number`; повторный `pr_create` идёт через
`_reprove_created_pr` — targeted `get` по записанному номеру, без
fresh search и без второго create. GET failure во время verify →
`verified=false`, entry остаётся `created`; GET failure при re-prove →
`unknown` (75); доказанный 404/несовпадение → `blocked`; ни одна ветвь
не разрешает recreate автоматически.

## Взаимодействие с lineage и idempotency

- Body-check не ослабляет guards 21R2: `created`/lineage re-prove идут
  раньше и не доходят до body-проверки — записанный remote effect
  важнее пере-проверки входа.
- Inherited/resolved номера по-прежнему редоказываются targeted `get`
  по текущему spec (включая его body-поля), search для этого не
  выполняется.
- Повтор `create/reconcile/resume` без новых remote-фактов не даёт
  нового dispatch; `unknown` + пустой search — вечный blocked.
- Идемпотентный prepare и frozen intent spec сохранены; re-prepare при
  том же входе — no-op по `spec_sha256`.
