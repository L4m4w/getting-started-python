# 17 — закрепление ALLURE_ID и финальный API execution

Ты — исполнитель 17. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Других агентов не запускай. Прочитай AGENTS.md, локальный run-tests skill,
`knowledge/testing/run-tests.md`, `knowledge/integrations/testops.md`,
каталог компонентов/констант, requirement/scenarios пилота,
`docs/qa-workflow/handoffs/coordination-wave-13.md`,
handoff 10 и runbook запуска из задания 10/07.

Этап 16 закрыт: execution run-5tsmzg1d uploaded, launch 57316.
Согласованные ID: 001→55376, 002→55374, 003→55375, 004→55377,
005→55373, 006→55378. Их повторно согласовывать не нужно.

Цель: закрепить разные ALLURE_ID для шести параметризованных сценариев,
получить новый финальный fix-прогон с этими ID и подготовить bind-пакет.
**Новая публикация TestOps, create/close, commit/push/PR не разрешены.**
Разрешение на upload этапа 16 уже использовано и на новый execution не переносится.

Область записи: `tests/api/test_category_update.py`,
`test_data/consts/category_update.py`, при необходимости точечное обновление
соответствующих записей `knowledge/components/consts.md`, новые каталоги
artifacts и новый handoff `docs/qa-workflow/handoffs/17-bound-final-execution.md`.
Общие README/планы интегрирует координатор. Shared harness/production code
не меняй; при подтверждённой проблеме передай конкретный блокер.
Сохраняй чужие незакоммиченные изменения, checkout не переключай/не сбрасывай.

1. Сначала проверь, не выполнено ли уже задание 17. Прочитай актуальные
   файлы и сохрани identity до изменения. Добавь mapping scenario→case ID
   в константы и маркировку на каждый параметризованный случай.
   Один статический allure.id на функцию с четырьмя параметрами недопустим:
   каждый сценарий должен получить ровно один собственный ALLURE_ID.
   При runtime-разметке используй шаг теста по AGENTS.md. Не меняй значения
   параметров, node IDs, PATCH/GET assertions, fixtures/cleanup и поведение API.
2. Выполни подходящие локальные проверки/collection. Проверь реально
   сериализованный ALLURE_ID, а не только Python-разметку. Не запускай
   удалённый стенд ради локальной проверки. Точные ID и их назначение
   отрази в каталоге компонентов, если изменены общие константы.
3. Для фактического API execution используй прежний разрешённый локальный
   disposable scope проекта `catupdval` из задания 10: только сервисы
   пилота, собственный пользователь, OAuth/регистрация, категории
   POST/PATCH/GET и узкий cleanup. Не расширяй доступ на удалённый SUT,
   чужие аккаунты/ресурсы. Если прежний scope невозможно восстановить,
   сохрани локальный результат и точный блокер без расширения доступа.
   Требуемую sandbox escalation выполняй штатно.
4. Выполни **один новый fix API-прогон** всех шести сценариев, используя
   base+patch, source→build/image→live binding, readiness и manifests
   по требованиям задания 10. Baseline заново не запускай: сила тестов
   ранее доказана, assertions остаются прежними. Не переиспользуй ID
   старого фактического прогона. Сохрани новый source snapshot; новые SHA
   файлов маркировки ожидаемо отличаются от исторического api-contract-v1.
   Не подгоняй исторический manifest под новый код и не меняй версию
   формата контракта только ради изменившегося хеша файла.
5. Требуется шесть passed без setup/teardown errors, корректные повторные
   GET, cleanup всех своих категорий, завершение только своих ресурсов
   и post-down evidence. Полный image ID и pre/post binding обязательны.
   Во время execution тесты не редактируй. Чужой работающий стек —
   конфликт для диагностики, не разрешение его остановить.
6. В новых исходных Allure result JSON проверь соответствие каждого
   scenario→ровно один ALLURE_ID из согласованного mapping. Исторические
   результаты не модифицируй, ручной дописки IDs в новые result JSON тоже
   не допускай: они должны появиться при выполнении теста.
7. Для **нового execution** штатными plan/assign/package подготовь
   локальный `--mode bind` пакет для проекта 5444; шесть пар уже согласованы.
   Проверь input/mapping/package SHA, attachments и отсутствие лишних
   результатов; сохрани точный execution ID и package SHA. Source и
   производный пакет должны содержать правильные реальные ID.
   Старый execution run-5tsmzg1d и его uploaded state не меняй.
8. В handoff ready / blocked / needs_decision: версии входов, изменение
   только маркировки, команды/codes, новые manifest/JUnit/Allure,
   таблица шести исходов/ALLURE_ID, проверки identity/cleanup/post-down,
   bind-пакет и SHA, что не выполнено. Не выдавай локальную сборку
   bind-пакета за серверную публикацию. Выполни git diff --check.

После передачи координатор проверит новый execution и отдельно подготовит
решение о его публикации. Git/PR и оркестратор — следующие задачи.
