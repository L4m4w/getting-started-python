# Завершение 16C — согласованные assign и REST verify

Ты — исполнитель 16C. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Прочитай AGENTS.md, `knowledge/integrations/testops.md`,
`docs/qa-workflow/handoffs/16c-testops-publication-live.md` и
`docs/qa-workflow/handoffs/coordination-wave-12.md`.

Координатор независимо проверил живой launch 57316 и **явно согласовал**
шесть пар в wave 12. Контрольная точка согласования закрыта, повторно
разрешение пользователя на эти assign/verify не запрашивай.

Разрешённая запись: `artifacts/testops/run-5tsmzg1d/`, новый уникальный
`artifacts/testops-live/16c-finalize-<UTC>/` и новый handoff
`docs/qa-workflow/handoffs/16c-testops-finalized.md`.
Ты единственный писатель рабочего execution state. Сохраняй все чужие
изменения; исторические evidence/handoffs не меняй, других агентов не запускай.

1. Проверь текущее состояние и пакет штатными integrity-проверками:
   execution run-5tsmzg1d, project 5444, launch 57316, attempts=1,
   isolate package SHA
   `a6f1cdddabfa460897b28fb8bd22cbe46bc0e6687489e61f86cbbfaf5e6e87ec`.
   Если состояние уже изменилось, сначала диагностируй read-only;
   успешно выполненные действия не повторяй вслепую.
2. Сохрани безопасные копии state/log и их SHA до изменений в новом evidence.
   Назначь согласованные пары штатной локальной командой:

   ```sh
   sh tools/run-testops.sh assign --execution run-5tsmzg1d CAT-UPD-VAL-001=55376 CAT-UPD-VAL-002=55374 CAT-UPD-VAL-003=55375 CAT-UPD-VAL-004=55377 CAT-UPD-VAL-005=55373 CAT-UPD-VAL-006=55378
   ```

   Сохрани mapping-approved.json со ссылкой на решение wave 12.
   Isolate-пакет не пересобирай: его assignments digest не зависит от
   назначенных case IDs. Любой integrity-блокер сообщи без обхода.
3. Выполни свежий штатный REST verify:

   ```sh
   sh tools/run-testops.sh verify --execution run-5tsmzg1d --online --transport rest
   ```

   Ожидается exit 0 / confirmed / persisted uploaded. Требуются точные
   launch/project, закрытие/готовность, полные страницы, шесть passed,
   все шесть bindings без missing/foreign/hidden/retries/дублей.
   Не выставляй uploaded вручную. Иной verdict сохрани как ограничение.
4. Проверь неизменность package/input/assignments SHA, attempts=1,
   launch=57316. На uploaded повтори read-only verify и отметь, если он
   возвращает сохранённое подтверждение без нового HTTP. Повтор upload
   уже проверен исполнителем (exit 69); снова write-команду не вызывай.
5. В новом handoff: команды/codes, реальные свежие REST checks, источник
   согласования, таблица шести ID, launch URL, итоговый persisted status,
   identity и ограничения. Выполни git diff --check.

Запрещены create/upload/close/retry, recovery API, новые execution,
изменения API-кода, API/UI/Docker/Gradle, commit/push/PR. Секреты только
через штатный loader, не печатать/не сохранять token/JWT/сырые HTTP ответы.
Разрешены targeted read-only проверки того же launch/project и запись
безопасного evidence. Unit/collection без изменения кода не повторяй.
README и общий mapping-документ интегрирует координатор после отчёта.
