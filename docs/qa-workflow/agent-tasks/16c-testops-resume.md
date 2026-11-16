# Продолжение 16C после приёмки подготовки

Ты — исполнитель 16C. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Прочитай `AGENTS.md`, `knowledge/integrations/testops.md`,
`docs/qa-workflow/agent-tasks/16c-testops-publication.md` и
`docs/qa-workflow/handoffs/coordination-wave-11.md` и
`docs/qa-workflow/handoffs/16c-publication-authorization.md`.

Координатор принял 16A/16B и зафиксировал конкретные входы в wave 11:
execution `run-5tsmzg1d`, project 5444, isolate,
package SHA-256 `a6f1cdddabfa460897b28fb8bd22cbe46bc0e6687489e61f86cbbfaf5e6e87ec`,
launch name `CAT-UPD-VAL run-5tsmzg1d pilot16-20261115`.
Остальные identity и точные команды — в wave 11.

Пользователь 2026-11-15 отдельно разрешил одну публикацию именно этого
пакета и закрытие launch; точный scope и источник решения записаны в
`16c-publication-authorization.md`. Эта контрольная точка закрыта;
повторно разрешение на согласованные upload/close не запрашивай.
Запись разрешения уточняет прежнее состояние needs_decision в wave 11
и исходном поручении 16C. Продолжи последовательный план:

1. Сохрани прошлый handoff 16C неизменным. Новый отчёт —
   `docs/qa-workflow/handoffs/16c-testops-publication-live.md`,
   новый evidence — `artifacts/testops-live/16c-publication-<UTC>/`.
   Ты единственный владелец записи `artifacts/testops/run-5tsmzg1d/`.
2. Повторно проверь state, все digest и целевой проект. При следах попытки
   или совпадающем launch не создавай новый. Не меняй execution/package
   для обхода состояния. Baseline не публикуй.
3. Одна штатная upload-команда из wave 11. Exit 0 — sent. Один close
   записанного launch при необходимости, после проверки project.
   Неизвестный исход любого write → read-only диагностика и отдельное
   решение. Автоматический повтор close из handoff 16B не разрешён.
4. Ожидание обработки ≤10 минут с интервалом 15 секунд, REST verify,
   точные шесть результатов/статусов, полная пагинация и аномалии.
   Case IDs сохрани как кандидаты и остановись перед assign до их
   явного согласования пользователем или координатором.
5. После согласования назначь пары штатным assign без пересборки пакета,
   выполни REST verify. Uploaded требует полного серверного доказательства.
6. После устойчивого sent/uploaded проверь локальную блокировку повторного
   вызова без повторного upload по правилам исходного задания 16C.

Все прежние ограничения по токенам, evidence, историческим артефактам,
кодовым изменениям, другим агентам и commit/push/PR сохраняются.
Не запускай API/UI/Docker/Gradle. В отчёте различай реально выполненные
write/read-only вызовы и прежние измерения. Выполни `git diff --check`.
