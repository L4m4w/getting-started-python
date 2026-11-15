# Приёмка 19A2 и подготовка реального PR boundary

Дата: 2026-11-16 (Europe/Volgograd). **19A2-QA и 19A2-APP приняты как
актуальные локальные пакеты.** Это не immutable Git heads, публикация
draft PR или завершение MVP. Исторические пакеты/отчёты не переписаны.

## Собственная проверка координатора

Прочитаны оба handoff, allowlists/SHA, PR title/body, зависимости и планы.
Evidence: `artifacts/git-pr/coordinator-19a2-review-20261116/review.json`.

- QA allowlist — 184 файла, commits A=71, B=113. 184/184 SHA совпали
  с текущими файлами; все 184 snapshot-копии существуют и совпадают.
  Формулировка handoff о 183 копиях относится к промежуточной проверке;
  координатор проверил финальный комплект, включая собственный handoff
  QA и peer APP. Пропущенных modified/untracked и файлов без решения нет.
- App — два файла, snapshot/current SHA совпадают с принятыми Java
  source identities: controller `32aec8fb…`, regression `eea6de8d…`.
  Tracked patch ровно `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`.
- 22 accepted-input SHA wave 26 совпали, 19 protected и 15 API source
  SHA совпали. Staged обоих репозиториев пуст; checkout/ветки/index
  не менялись. Исторические executions/workflow не модифицировались.
- Source/code не менялся: unit/collection/Java/API заново не запускались.
  Числа 99 targeted, 511 unit и 550 collected в PR body указаны с
  разными источниками, не как один прогон. Ссылка на launch 57317 и
  base+patch/dirty identity сохраняются; head SHA/PR URL не выдуманы.
- Secret scan исполнителей просмотрен: 16 QA совпадений классифицированы
  как синтетические данные/идентификаторы, APP кандидатов нет. Выбранный
  allowlist исключает .env/артефакты/кэши; coordinator snapshot не включает
  пользовательские credentials. Это целевой скан, не гарантия отсутствия
  любых возможных чувствительных данных.

QA включает 5 малых build-readiness логов по точному allowlist:
они нужны локальным ссылкам handoff 01 и прошли скан. Координатор принимает
это конкретное исключение wave 19; прочие raw logs/artifacts не включать.
Текстовые исторические handoff сохранены; локальные evidence в artifacts
из удалённого PR недоступны, что явно указано в dependencies.md и body.

## Конкретный будущий Git/PR-план

| Репозиторий | Base | Предлагаемая feature-ветка | Состав |
| --- | --- | --- | --- |
| L4m4w/niffler-py-st3 | main, локальный base 36674280… | fix/cat-upd-val-gateway-validation | @Valid + Java regression, один commit |
| L4m4w/getting-started-python | MVP_workflow, локальный base c84483bf… | feature/cat-upd-val-qa-workflow | commit A: код/пилотные docs; commit B: process docs |

Будущие Git-операции выполнять в изолированных worktrees/checkout,
сохранив общие dirty checkout и их index. `git switch -c` из старых
иллюстративных планов не является разрешением переключать общий checkout.
До записей: свежая read-only серверная проверка base/прав, повторный
SHA/allowlist/secret scan. Push только выбранных feature-веток; оба PR
draft, без merge. Новые Git head SHA записать отдельно; они не меняют
provenance старых API/Java executions. Cross-links после реальных URL
меняют body/spec и требуют согласованной повторной проверки digest.

Пакет координатора `artifacts/git-pr/coordinator-19a2-review-20261116/`
содержит копии title/body, согласованный `publication-plan.md` и
добавочный manifest текущей координаторской документации. Исходные
184/2 snapshot не изменены. Текущие индексы обновлены новым решением;
их новые SHA не выдавать за первоначальный snapshot 19A2.

## Что подготовить до запроса публикации

`gh` локально не найден (`command -v gh` без результата). Production
workflow CLI не инъецирует live PrTransport, а `PrSpec` хранит только
body_sha256, без воспроизводимого payload для реального create.
Ручные PR через сторонний путь не проверят durable intents/reconcile
этого workflow. Поэтому перед публикацией — одно конкретное техническое
поручение [22: GitHub transport/CLI wiring](../agent-tasks/22-github-pr-transport.md).
Это часть оставшегося live PR boundary, не новое функциональное
расширение пилота. Установку gh и доступ к реальным токенам не выполнять.

22 реализуется и проверяется offline с fake HTTP, допускается только
чтение публичной официальной API-документации. После приёмки 22
координатор инкрементально обновит QA allowlist/body/SHA; APP-пакет
пересобирать без drift не нужно. Новый запуск 19A2-QA/APP не требуется.
Далее запросить отдельное разрешение на конкретные commit/push/draft PR,
выполнить разрешённую публикацию и live repeat без дублей. Готовность
offline transport не выдавать за проверку живого GitHub.

## Сохраняющиеся границы

Новых SUT/API/UI/TestOps/Docker/Gradle/CI, сети/fetch, Git writes,
изменений исторических evidence или запуска агентов координатором не было.
Working workflow initialized. SHA state/log run-ni_5bvnc прежние,
launch 57317/шесть bindings приняты, upload/close не повторять.
Ограничения evidence 07, provenance 10/17 и close-аудита wave 17 сохраняются.
Immutable heads/реальные draft PR, live идемпотентность и итоговая оценка
MVP остаются открытыми; commit/push/PR пользователь не разрешал.
