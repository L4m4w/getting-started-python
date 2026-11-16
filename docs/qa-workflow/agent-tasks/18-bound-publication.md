# 18 — публикация финального bind execution

Ты — исполнитель 18. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Прочитай AGENTS.md,
`knowledge/integrations/testops.md`,
`docs/qa-workflow/handoffs/coordination-wave-15.md`,
handoffs 16C live/finalized и 17C run. Приёмка 17 завершена.

Контрольная точка: нужна отдельная явная авторизация пользователя на
публикацию согласованного пакета ниже и close. Сам этот промпт разрешения
не предоставляет. Если оно уже передано в сессии/записи координатора,
повторно не спрашивай. Если разрешения нет — не выполняй write-вызовы.

Согласованные входы: execution `run-ni_5bvnc`, endpoint
`https://allure.qa.guru`, project 5444, mode bind,
package SHA `1e1f643257c2289be3add60c47ab10e749b289e3d0f8920d3acf060f488d05a7`,
launch name `CAT-UPD-VAL run-ni_5bvnc final17-20261115`.
Шесть существующих case IDs согласованы:
001→55376, 002→55374, 003→55375, 004→55377, 005→55373, 006→55378.
Отдельного согласования этих пар не требуется.

Запись только в `artifacts/testops/run-ni_5bvnc/`, новый уникальный
`artifacts/testops-live/18-<UTC>/` и
`docs/qa-workflow/handoffs/18-bound-publication.md`.
Ты единственный писатель нового execution. Сохраняй все чужие изменения,
старый uploaded execution/launch 57316 и исторические артефакты не меняй.

После получения разрешения выполни задачу целиком до финального handoff:

1. Повторно проверь effective endpoint/project, доступ к проекту, целевые
   существующие кейсы, отсутствие предыдущей попытки и совпадающего launch.
   Зафиксируй безопасный preflight inventory пилотных case IDs, чтобы
   после публикации проверить отсутствие новых пилотных кейсов.
   Проверь source/mapping/package и recorded state, сохрани backup с SHA.
2. Один штатный upload, без отдельного create и без retry:

   ```sh
   sh tools/run-testops.sh upload --execution run-ni_5bvnc --execute --launch-name 'CAT-UPD-VAL run-ni_5bvnc final17-20261115'
   ```

   Exit 0 — sent. При timeout/nonzero/unknown/in_progress не повторяй
   запись. Выполняй только read-only диагностику, recovery не применяй.
3. Проверь project/имя записанного launch. Если closed=false после
   завершённой отправки, один согласованный close:

   ```sh
   allurectl --endpoint https://allure.qa.guru -o json launch close <recorded-launch-id>
   ```

   Факт попытки сохрани до вызова. При неизвестном исходе перечитай
   серверное состояние; автоматический повтор close запрещён.
4. Дождись обработки read-only: максимум 10 минут с интервалом 15 секунд.
   Выполни штатный свежий REST verify:

   ```sh
   sh tools/run-testops.sh verify --execution run-ni_5bvnc --online --transport rest
   ```

   Bindings уже согласованы: при правильном live-наборе ожидаются
   exit 0/confirmed/persisted uploaded без новой остановки на согласование ID.
   Требуются правильные launch/project, closed/ready, полная пагинация,
   точные шесть passed и case IDs, отсутствие missing/foreign/hidden/retries/
   duplicates. Иной verdict не исправляй догадками или вручную через state.
5. Проверь, что использованы те же шесть существующих кейсов, новых
   пилотных кейсов не появилось, старый launch/execution 16 не изменялся.
   Не выдавай усечённую выдачу за доказанную полноту; ограничения сохраняй.
6. В устойчивом sent/uploaded проверь decide_upload и повтори тот же
   upload-вызов **только как проверку локального блокирования**: ожидается
   exit 69 до транспорта, неизменные attempts=1, launch, SHA и upload log.
   На pending/failed/активном in_progress этот эксперимент запрещён.
   После uploaded повторный verify должен вернуть терминальное сохранённое
   подтверждение; отличай его от нового HTTP snapshot.
7. В handoff ready / blocked / needs_decision сохрани scope/источник
   разрешения, точные commands/codes/UTC, execution/package identity,
   launch URL, bindings и REST checks/verdict, проверку отсутствия новых
   кейсов и повторной загрузки, ограничения. Выполни git diff --check.

Пакет после начала попытки не пересобирать, другой execution для обхода
не создавать, baseline не публиковать. Токен/JWT/сырые ответы/headers не
выводить и не сохранять, только allowlist evidence. Код, README, приложение
не менять. API/UI/Docker/Gradle, commit/push/PR запрещены.
Приёмка результата и дальнейший Git/PR/оркестратор остаются координатору.
