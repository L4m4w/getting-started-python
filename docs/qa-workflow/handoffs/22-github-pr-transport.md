# 22 — сводная приёмка GitHub transport/body/CLI

Дата: 2026-11-16. **Этап 22 (A + B + AR + C) завершён и принят
координатором как реализация, проверенная offline.** Это не live
верификация GitHub и не завершение полного MVP.
[Итоговое решение и следующий шаг](coordination-wave-31.md).

## Части и проверки

- [22A](22a-github-http-transport.md): stdlib GitHubPrTransport,
  lazy credentials, fake HTTP, search/create/get. Первоначальные P1
  snapshot-проверки сохранены в [wave 29](coordination-wave-29.md).
- [22B](22b-pr-body-and-checkpoints.md): точный UTF-8 body payload,
  durable source/snapshot digest, legacy guards, number/URL до GET.
- [22AR](22ar-github-snapshot-corrections.md): changed_files equality,
  detail→files→detail, ошибки вместо ложного verified;
  [принятие A/B](coordination-wave-30.md).
- [22C](22c-cli-and-http-integration.md): глобальный
  `--pr-transport {none,github}`, lazy wiring, настоящий CLI subprocess
  на fake HTTP/Git, реальные A/B guards и shared docs.

Координатор ранее выполнил 218 targeted (wave 29), затем 161 (wave 30)
на соответствующих версиях; это разные измерения, их не суммировать как
число уникальных тестов. **Финальная объединённая версия: собственный
полный unit 711 passed**, exit 0, run-y3h45x2t, 167.08 s. Включены 15 CLI,
86 HTTP, 39 snapshot, 36 payload и остальные unit потребители.
Full-chain fake repeat из новой копии — 31/31, без новых dispatch при
идентичном повторе. Это fake simulation, не live опубликованные PR.

Exact reviewed/accepted SHA и evidence координатора:
`artifacts/workflow-github/coordinator-22c-review-20261116/`.
JUnit/Allure/manifest полной группы:
`artifacts/harness/run-y3h45x2t/`. CLI subprocess и программный уровень
различаются в handoff C; bootstrap подменяет HTTP/Git, а не весь
transport/orchestrator. `test_full_chain_order` C подтверждает PR-путь
через A/B; вся fake MVP-цепочка отдельно проверена repeat script.

## Принятая поверхность

Default transport none. Выбранный github сам не разрешает I/O:
HTTP только при --online и действующих guards; POST ещё требует
--execute. Ранние команды, отсутствие флагов и disabled transport
не читают credentials/не обращаются к HTTP. Реальные env tokens в
проверках не использовались, gh/dependencies не устанавливались.

Create не повторяет HTTP POST; читаемый number сохраняется до
verification. Unknown + []/404 не разрешает resend. Body фиксируется
по точным UTF-8 bytes и digest, stale/missing inputs блокируют dispatch.
Git commit/tree/source/scenario/provenance guards и 21R2 lineage
сохранены. Get проверяет open/unmerged/same-repo/draft, полный files
count и согласованность полей двух detail reads. Snapshot не атомарен
и не гарантирует неизменность PR после последнего наблюдения.

## Остаток MVP

Общие checkout остаются dirty, рабочий workflow initialized; ни
коммитов с пилотом, ни real draft PR ещё нет. Следующий конкретный
шаг — локальные immutable heads в двух изолированных worktree после
явного разрешения. Git push/PR/network и новые SUT executions требуют
своих конкретных разрешений; готовый CLI не разрешает их автоматически.

Старые run-ni_5bvnc/run-vzsatlfk остаются base+patch/dirty. Новый commit
не даёт права переобозначить исторический head evidence как новый clean
execution. Перед live PR нужен отдельный revision/context/review и
identity-совместимый execution/equivalence-план без head-waiver обхода.
Launch 57317/старый upload/close не повторять. Дальше остаются живой
GitHub repeat без дублей и итоговая оценка ручных работ/времени/ограничений.
