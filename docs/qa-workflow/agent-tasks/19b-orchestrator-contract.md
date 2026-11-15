# 19B — контракт минимального оркестратора

Ты — исполнитель 19B. Спроектируй проверяемый контракт минимального
оркестратора QA workflow и сквозной идемпотентности. На этом этапе код
не реализуй. Других агентов не запускай.

Рабочая папка: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`.
Прочитай AGENTS.md, docs/plans/qa-workflow-mvp.md,
docs/qa-workflow/handoffs/coordination-wave-17.md,
docs/qa-workflow/handoffs/coordination-wave-18.md,
knowledge/integrations/testops.md, knowledge/components/README.md и
соответствующие разделы каталога; изучи tools/harness.py, tools/testops.py
и infrastructure/reporting/testops/{state,lifecycle,results,verification}.py.

Разрешённая запись — только:
- `docs/qa-workflow/design/19-orchestrator-contract.md`;
- `docs/qa-workflow/handoffs/19b-orchestrator-contract.md`;
- новый каталог `artifacts/workflow-design/19b-<UTC>/`.
19A параллельно готовит Git/PR-пакет. Общие README, планы, каталог
компонентов, реализацию, тесты и существующие state не меняй.

Подготовь контракт и примеры валидных/невалидных JSON:
1. Versioned manifest/state: workflow ID, идентичность события и входа,
   оба repo/base/head/test SHA, требования/сценарии/решение ревью,
   source digests, environment/build provenance, execution ID, bindings,
   TestOps launch, будущий draft PR, ошибки и история переходов.
   Различай отсутствующий immutable head и dirty snapshot; сейчас PR/head
   нет. Повторный вход не должен обходить журнал через новый workflow ID.
2. Таблица переходов MVP context_ready → scenarios_ready → awaiting_review
   → approved → implementation_ready → executed → published с условиями,
   stale/blocked/error и resume. Раздели TestOps published и PR pending:
   имеющийся launch не означает полного published. Новый head инвалидирует
   зависимые анализ/ревью; неизменившийся вход сохраняет принятые результаты.
3. CLI и программные adapters для последовательных этапов: какие действия
   реально выполняет оркестратор, какие принимает как проверенные артефакты
   человеческого/LLM-этапа, какие сейчас блокирует отсутствие разрешения.
   Нужен исполняемый workflow, а не только реестр старых Markdown-отчётов.
   Не строй универсальный scheduler/LLM framework; переиспользуй harness
   и TestOps CLI через явные контракты и фиксированные команды.
4. Crash-safe сохранение, блокировка с одним писателем, целостность входов,
   поведение при повреждении state, частичной записи и concurrent resume.
   Раздели workflow lock и execution lock; задай порядок захвата.
5. Идемпотентность всего входа: повтор события, перезапуск после каждого
   этапа, новый head, новый фактический execution, сбой до/после TestOps
   write и будущего PR create. Зафиксируй intent до внешнего вызова и
   read-only reconciliation после неизвестного исхода. Нельзя обещать
   exactly-once без поддержки сервера или слепо повторять create.
   Опиши ключ поиска будущего PR и проверки repo/base/head/состава,
   неоднозначное совпадение блокирует запись. Отсутствие PR в устаревшем
   локальном снимке не доказывает безопасность create.
6. Связь с существующими TestOps состояниями: state остаётся единственным
   источником жизненного цикла отправки; не копируй его в независимый
   управляющий флаг и не снимай guards. sent/unknown/in_progress/uploaded
   запрещают resend, сбой TestOps не повторяет API/генерацию. Read-only
   импорт принятого execution в НОВЫЙ workflow state не является новой
   отправкой или доказательством выполнения всех стадий оркестратором.
7. Матрица проверок будущей реализации: повтор одного входа и конфликт
   identities, resume после сбоя/прерывания, изменённый head/source,
   corrupt state, конкуренция, fake TestOps/PR transports с подсчётом вызовов,
   crash после внешнего успеха до local save, запрет обхода execution guards,
   отдельный новый execution. Без live write; mock-проверки обозначить
   как offline, будущий live PR criterion оставить открытым.
8. Минимальный список файлов реализации/тестов и порядок работ 20 →
   независимое ревью/повтор 21 → актуализация Git/PR → итоговая оценка.
   Перечисли метрики/источники затрат; отсутствующие time/token/cost данные
   остаются неизвестными, не восстанавливаются из предположений.

Проверь совместимость предложений с текущими API helpers, приложи ссылки
на символы/файлы и SHA входов. Зафиксируй открытые решения, но делай
обоснованный минимальный выбор там, где дополнительный ответ не нужен.
Никаких API/UI, Docker/Gradle, сети, TestOps writes, commit/push/PR.
Секреты не читать/не копировать; старые evidence/handoffs/state не менять.
Handoff: ready/blocked/needs_decision, входы, собственные статические
проверки, evidence, ограничения и критерии приёмки. Реализацию 20 не
начинать: координатор сначала проверяет и принимает контракт 19B.
