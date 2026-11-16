# Задача 21 разделена на три параллельных ревью

Дата: 2026-11-15. По запросу пользователя единое поручение 21 разделено
на 21A/21B/21C для параллельного выполнения. Это организация следующего
этапа, не отчёт о его выполнении. Принятие 20/20R2 из
[wave 22](coordination-wave-22.md) сохраняется.

| Исполнитель | Проверяет | Назначенный отчёт |
| --- | --- | --- |
| [21A](../agent-tasks/21a-state-and-evidence-review.md) | Schema/gates/revisions/envelopes, source/scenario contracts, historical provenance, read-only real evidence compatibility | 21a-state-and-evidence-review.md |
| [21B](../agent-tasks/21b-effects-and-recovery-review.md) | Run/TestOps/PR effects, immutable commit/tree, unknown reconciliation, crash boundaries и prepare checkpoints | 21b-effects-and-recovery-review.md |
| [21C](../agent-tasks/21c-cli-and-repeat-review.md) | Index/locks/concurrency, production CLI boundary, full-chain fake repeat и документированные capabilities | 21c-cli-and-repeat-review.md |

Все три могут стартовать сразу на одной принятой версии, без ожидания
результатов друг друга. Общие исходники доступны только для чтения;
отчёты, evidence/stores, pytest basetemp/cache и выводы раздельные.
Пользователь запускает исполнителей самостоятельно. Координатор агентов
не запускал; единое поручение 21 целиком вместе с 21A/B/C не запускать.

Распределены также existing targeted tests: никто не повторяет общий
unit/collection без новой конкретной причины. Так время не тратится
на три одинаковых полных прогона. Read scopes могут пересекаться на
стыках, write scopes — нет. Во время ревью реализация заморожена;
обнаруженные дефекты передаются, а не исправляются параллельно.
Исправления будут отдельными конкретными поручениями после сверки findings.

Координатор после трёх handoff:
1. сверяет SHA проверенных версий и неизменность protected state;
2. проверяет воспроизведения, устраняет дубли findings и проверяет стыки;
3. оформляет одно решение по задаче 21 и следующую очередь работы.

Сводный handoff `21-independent-workflow-review.md` резервируется для
интеграции координатором; 21A/B/C его не пишут. Никакая отдельная часть
не объявляет весь 21/MVP принятым. 21C выполняет свою integration
simulation независимо, а общая приёмка ждёт все три результата.

Границы прежние: никаких SUT/API/UI, Docker/Gradle, сети, CI, TestOps
writes, commit/push/PR, переключения/сброса checkout и изменения исторических
evidence/рабочего workflow. Реальные Git/PR и итоговая оценка MVP
остаются следующими этапами после независимой проверки.

Координатор изменил только поручения/текущие индексы и добавил этот
организационный handoff. Новых тестов/публикаций нет; проверены локальные
Markdown-ссылки и diff --check обоих репозиториев.
