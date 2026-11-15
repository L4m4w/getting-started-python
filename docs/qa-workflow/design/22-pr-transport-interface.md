# 22 — общий интерфейс параллельных частей A/B

Дата: 2026-11-16. Решение координатора для разделения реализации;
это не отчёт о проверенном коде и не разрешение публикации.
[Порядок работы](../handoffs/coordination-wave-28.md).

## Разделение

22A единолично пишет `infrastructure/workflow/github.py` и свои тесты/
consts. 22B единолично пишет adapters/orchestrator и свои тесты/consts.
CLI/общие каталоги не меняет ни один из них: это 22C после их приёмки.
Общий исходный PrTransport search/create/get и PrRef сохраняют сигнатуры.

## API transport (22A → будущий CLI 22C)

```python
from infrastructure.workflow.github import GitHubPrTransport

transport = GitHubPrTransport(token_provider=None, http=None)
transport.search(key)  # list[PrRef], весь свежий набор или controlled error
transport.create(spec)  # PrRef с читаемым номером сразу после POST
transport.get(repo, number)  # полный PrRef или None только на доказанном 404
```

Конструктор pure/lazy: ни сети, ни чтения credentials. Вызовы token_provider
только при разрешённом фактическом HTTP-вызове. Реальный token provider
читает env; fake provider для tests. HTTP interface определяет и описывает
A внутри собственного модуля (status/headers/body), не меняя B source.
Полные ошибки/неполная пагинация не преобразуются в []. Исключения —
контролируемые Workflow*Error/безопасная transport error без токенов/сырых
ответов; POST failure остаётся unknown через orchestrator, без retry.

`search(key)` использует фактический ключ из
`Orchestrator._pr_search_key`: repo/head_branch/base_branch/title_key.
A сначала читает этот метод и существующий PrRef, не изобретает другую
форму. `repo` — существующий canonical github.com/owner/repo key.

`create` не делает verification GET/files до возврата читаемого номера:
orchestrator обязан сохранить его перед дальнейшими reads. Поля ref
берутся из ответа, files не выдумываются echo из spec. `get` возвращает
реально прочитанный полный состав/тело/head и проверенный статус draft/open;
чужой/closed/merged/non-draft или неполный ответ => отказ, без ложного
verified. `search` не теряет такие конфликты, превращая их в пустой набор.

## Body (22B → transport 22A)

Новый prepare предоставляет в spec/intent `body_text` (str|null) и
существующий `body_sha256`. Для непустого текста digest равен SHA-256
его точных UTF-8 bytes, без trim/изменения переводов строк. Absent/null/
пустое тело для **новых** spec канонизируются как body_text=None,
body_sha256=None. A так же нормализует remote null/empty; nonempty
тело хешируется по UTF-8 без преобразований. POST всегда draft=true.

До POST A проверяет соответствие body_text/body_sha256. Если legacy
spec не имеет body_text и digest=None, допустимо отсутствие body.
Legacy digest непустого/пустого файла без восстановимого текста нельзя
превращать в новый body или молча менять spec/intent; live create blocked,
нужен безопасный re-prepare по действующим guards.

B обеспечивает durable body payload и привязку к spec/intent; метаданные
исходного body-файла/immutable snapshot организует в своей области.
Изменённый/пропавший необходимый body input/snapshot блокирует до POST.
После crash не выбирать произвольный текущий файл и не повторять create.
Нормализация новых spec не мигрирует исторические state/evidence.

## Crash boundary (22B)

После возврата читаемого create ref: записать number/URL и известный
remote effect до verification GET. При crash/lost save ранее сохранённый
dispatched/unknown intent запрещает повторный POST; известный number
идёт через targeted get. Сохранить guards 21R2 для app/tests и ancestry.

## Последующее wiring (22C)

Глобальный `--pr-transport {none,github}`, default none. Выбор transport
не является разрешением: HTTP требует --online, POST ещё --execute и
все фазные/commit/tree/body/intent guards. status/init/doctor/prepare
не читают реальные tokens и не вызывают HTTP даже при выбранном github.
Без произвольного endpoint/disable-guards production-флага для тестов.
При необходимости изменить этот общий интерфейс — сначала решение
координатора; A/B не редактируют его независимо и не угадывают контракт.
