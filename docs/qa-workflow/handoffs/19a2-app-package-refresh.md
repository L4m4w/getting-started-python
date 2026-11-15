# 19A2-APP — актуализированный локальный Git/PR-пакет приложения

Дата: 2026-11-16 (замеры 2026-11-15T21:47–21:49Z). Исполнитель: `19A2-APP`.
**Статус: `ready`** — локальный пакет собран и проверен; drift относительно
принятых identity нет. Это готовность пакета, **не** разрешение Git writes и
не завершение MVP. Commit/push/PR не выполнялись; index, ветки, checkout,
config и remotes обоих репозиториев не менялись.

Поручение: [19a2-app-package-refresh.md](../agent-tasks/19a2-app-package-refresh.md).
Основание: [wave 26](coordination-wave-26.md), решения 19A из
[wave 19](coordination-wave-19.md), старый [handoff 19A](19a-git-pr-preparation.md),
[wave 17](coordination-wave-17.md), пилотные
[requirement](../pilots/category-update-validation/requirement.md) /
[scenarios](../pilots/category-update-validation/scenarios.md) /
[testops-mapping](../pilots/category-update-validation/testops-mapping.md).
Область 19A2-QA не затрагивалась; других агентов не запускалось.

## 1. Read-only Git-инвентаризация приложения

Репозиторий: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`
(remote `origin` = `https://github.com/L4m4w/niffler-py-st3.git`, credentials
в URL отсутствуют). AGENTS.md в приложении отсутствует (подтверждено повторно).

| Параметр | Значение |
| --- | --- |
| HEAD | `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` — одновременно принятый base пилота |
| Ветка | `main`; upstream `origin/main` == HEAD (**локальный кеш ref, без fetch** — свежая серверная картина не проверялась) |
| Staged | пусто |
| Modified tracked | 1: `CategoriesController.java` (`@Valid`, 1 строка) |
| Untracked (неигнорируемые) | 1: `niffler-gateway/src/test/.../CategoriesControllerValidationTest.java` |
| Untracked incl. ignored | 448 — все `*/build/*` и `.gradle/*` (кэши/генерация Gradle); вне build/.gradle — только тот же тестовый файл |

Новых неучтённых файлов приложения нет: единственный non-ignored untracked —
тест из allowlist. Иные кандидаты отсутствуют. Дамп: `inventory/`.

## 2. Allowlist, snapshots, идентичность

Состав принят wave 19 (решение 1): production fix — только `@Valid` у
`@RequestBody` `updateCategory` + Java-регрессия. Файл:
`artifacts/git-pr/19a2-app-20261115T214752Z/allowlist-app.txt`.

| Файл | Статус | SHA-256 | Сверка |
| --- | --- | --- | --- |
| `niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java` | M | `32aec8fbd7a7a4533327a3eabeaccb5ba917ae3c0de338dac621c9025830b8a9` | == java-manifest `run-36tzwapr` (head) |
| `niffler-gateway/src/test/java/guru/qa/niffler/controller/CategoriesControllerValidationTest.java` | ?? | `eea6de8d14f8d5f1b7bb84dd2dd384b1d03e3056daad39dacc9568515604ca50` | == java-manifest `run-36tzwapr` |
| tracked patch `git diff` | — | `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e` | == принятому patch; **байт-идентичен** `catupdval-rerun/base-to-fix.patch` и `run-36tzwapr/source.patch` |

Drift относительно принятых identity **не обнаружен** — исправлений
приложения/истории не требовалось. Копии источников: `sources/`;
контрольные суммы: `SHA256SUMS.txt`; учёт untracked:
`checks/patch-and-untracked.txt`.

Immutable head с пилотным изменением по-прежнему отсутствует: прогоны
05/07/10/17 выполнялись на `base + patch`. Dirty snapshot digest и patch
SHA не заменяют будущий commit SHA.

## 3. Черновики PR

- `pr-title.txt`: `fix(gateway): validate request body on PATCH /categories/update`
- `pr-body.md`: дефект и поведение после fix; Java-регрессия выделена
  отдельно; исторические baseline (`run-pqzz4gmr`, 4 failed), head
  (`run-36tzwapr`, 6/6) и API `run-ni_5bvnc` (launch 57317, шесть
  bindings) названы прогонами **base + patch**, не из будущего commit/PR.
  Взаимная ссылка на QA PR — `pending` до реального URL.
- Предлагаемая ветка `fix/cat-upd-val-gateway-validation`, base `main`
  (решение wave 19/26). Ветка не создана.

## 4. Будущий план публикации

`publish-plan.md` — только записанные команды: read-only проверки свежей
server base/прав и `gh`-аутентификации → `switch -c` → `git add` двух файлов
→ `commit` → запись нового head SHA → `push -u` → `gh pr create --draft
--base main --body-file pr-body.md`. Зафиксированы: неизвестный исход
create запрещает слепой retry (сначала `gh pr list --head`/`api pulls`
диагностика, adopt единственного точного совпадения), обязательное
сохранение remote PR number до любых повторов, ноль результатов поиска
не доказывает отсутствие PR. Новых согласований это задание не запрашивает.

## 5. Проверки (offline, read-only)

| Проверка | Exit/результат | Файл |
| --- | --- | --- |
| Git-инвентаризация приложения | exit 0, см. §1 | `inventory/` |
| `git diff` sha256 vs принятый patch | `04eb4c87…`, IDENTICAL обоим историческим patch | `checks/patch-and-untracked.txt` |
| SHA-256 двух файлов vs java-manifest `run-36tzwapr` | 2/2 совпали | `SHA256SUMS.txt` |
| Snapshot-копии vs текущий checkout (after) | IDENTICAL, status UNCHANGED | `checks/final-recheck.txt` |
| 19 protected SHA по списку 20R2 | **19/19 идентичны** | `checks/protected-sha.txt` |
| 15 API source SHA vs manifest `run-ni_5bvnc` | **15/15 совпали** | `checks/api-sources-sha.txt` |
| Secret-скан allowlist (без вывода значений) | 0 кандидатов | `checks/secret-scan.txt` |
| `git diff --check` app / QA | exit 0 / exit 0 | `checks/final-recheck.txt` |
| Новые неучтённые файлы приложения | отсутствуют | `inventory/untracked-nonignored.txt` |

Unit/Java/collection не повторялись: код не менялся, использованы принятые
исторические evidence. Не выполнялось: сеть/fetch, SUT/API/UI, Docker/Gradle,
CI, TestOps/PR writes, Git commit/push/checkout/reset, чтение/копирование
секретов, запуск агентов. Все чужие изменения обоих репозиториев сохранены.

## 6. Ограничения и границы

- Локальные remote refs — кеш; свежесть `origin/main`, write-доступ и
  `gh`-аутентификация требуют read-only серверной проверки перед публикацией.
- Пакет актуален на момент замера; любой drift приложения или QA до
  публикации требует пересборки (см. шаг 0 плана).
- Live PR transport в workflow CLI отсутствует (wave 26); план записан
  как shell/`gh` последовательность для будущего исполнителя, а не как
  готовая интеграция оркестратора.
- MVP не завершён: отсутствуют immutable heads, реальные draft PR, решение
  по live PR transport и сквозная итоговая оценка.

## Evidence

`artifacts/git-pr/19a2-app-20261115T214752Z/` (gitignored):
`allowlist-app.txt`, `SHA256SUMS.txt`, `base-to-fix.patch`, `sources/` (2),
`pr-title.txt`, `pr-body.md`, `publish-plan.md`, `inventory/` (9 файлов),
`checks/` (5 файлов).
