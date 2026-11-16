# Приёмка 14A/14B: доступ и контракт TestOps

Дата: 2026-11-14. Координатор проверил сохранённые handoffs/evidence,
без собственных сетевых вызовов, запуска подагентов и внешних записей.
14A/14B приняты как исследование read-only доступа и серверного контракта.
Это не приёмка живого upload/per-result verification.

## Что подтверждено

- 14A summary: allurectl 2.24.0; project get 5444 — exit 0,
  id 5444, name ai_project_Larkin_EA; два поиска CAT-UPD-VAL — exit 0,
  пустые массивы. Контроли true/id >= 0 также вернули 0 кейсов.
  Ни один реальный TestOps case ID не назначен.
- 14B 00-auth.txt: обмен credentials завершился HTTP 200, без сохранения
  значения JWT. 01-launch-list.json: HTTP 200, projectId=5444,
  totalElements=0, totalPages=0, content/items пусты, last=true.
  В этом временном снимке launches нет.
- Сохранённый OpenAPI extract: 3.1.0, allure-testops-service 527u01.
  LaunchDto содержит projectId/closed, но не статистику;
  statistic — отдельный массив status/count; progress — ready;
  testresult — Page с id/name/status/testCaseId/launchId/projectId,
  hidden/retriedBy. Это схемы, не наблюдавшиеся непустые ответы.
- Контроль launch/0 — 404; results/progress для 0 — 403.
  Ошибка доступа к результатам сама по себе не доказывает missing launch.

Evidence:
`artifacts/testops-readonly/14a-20261114T155451Z/`;
`artifacts/testops-readonly/14b-155530/`.
Сверены summary, control, auth/page/error snapshots и OpenAPI extract.
control.json содержит три последовательных JSON-документа, а не один
валидный JSON: координатор прочитал их последовательно raw_decode.
Исторический файл не переписывался.

## Уточнения приёмки

1. Пустые успешные поиски поддерживают отсутствие найденных кейсов сейчас.
   Bare-array CLI и отсутствие page flags сами по себе не доказывают,
   что непустая выдача произвольного размера никогда не усекается.
   Непустая case item schema и общая полнота поиска ещё не проверены.
2. Увеличение --size списка launches само по себе не реализует пагинацию.
   Текущий fallback ищет точный id; нельзя объявлять его усечённым по
   примеру нефильтрованного списка. Для REST probe fallback не нужен,
   если прямой LaunchDto имеет достоверный projectId.
3. Empty content не означает успешный конец, если page metadata обещает
   оставшиеся записи. Несогласованные totals/last, пропущенные/повторные
   страницы, повторные ID и изменение набора должны давать inconclusive,
   а не частичную успешную проверку.
4. ready — булево поле OpenAPI; точная семантика на непустом launch не
   проверена. Даже ready=true не доказывает отсутствие частичного upload
   и не разрешает автоматический resend. Нужны полный набор и bindings;
   существующий запрет слепого retry сохранить.
5. Предложенный sort=id,ASC не был проверен live. Использовать только
   подтверждённую сервером сортировку; ошибка/нестабильность — неполнота.
6. 14A сохранил имена других видимых проектов и контроль чужого project ID:
   это избыточно для целевого проекта. Не повторять и не переносить эти
   сведения в новый пакет. Исторические evidence сохранены как есть.

## Следующее готовое поручение — 15

Реализовать read-only REST probe с инъецируемым HTTP-слоем и offline-тестами:
JWT exchange, launch/project, progress/statistic, строгая пагинация results,
allowlist полей, явная неполнота/ошибки, аномалии hidden/retries/duplicates.
Подключить probe к verify по явному выбору транспорта. Upload оставить
через allurectl. Исправить точную границу scenario ID в resolve.

Не создавать сущности ради тестирования; не выполнять upload, close,
commit/push/PR. Живой положительный тест results/bindings останется
отдельным этапом после отдельно разрешённой публикации пилота.

Текущие unit/collection результаты wave 7 (154/169) здесь не повторялись:
при проверке 14 реализация не менялась. TestOps IDs/launch не получены,
права записи не проверены. Полный MVP не завершён.
