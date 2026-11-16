"""Фиктивные входы для 21R2 unit-регрессий оркестратора (PR lineage
deduplication после supersede). Только данные этих тестов: третья base/
head-пара для цепочки grandparent→parent→child, номера записанных remote
PR и id execution'ов для повторного доведения новых линий до executed.
Реальных SHA/ID и кредов нет — все проверки offline в temp dirs.
"""

# Третья линия lineage: grandparent → parent → child.
APP_BASE_SHA_3 = "7" * 40
APP_HEAD_COMMIT_SHA_3 = "8" * 40

# Номера remote PR, записанные в ancestry как известный remote-эффект.
PR_LINEAGE_NUMBER = 42
PR_TERMINAL_NUMBER = 57

# Execution ids для доведения второй и третьей линии одного проекта до
# executed (уникальные на project, чтобы evidence не пересекались).
EXECUTION_HEAD_4 = "run-unithead4"
EXECUTION_HEAD_5 = "run-unithead5"
EXECUTION_BASE_3 = "run-unitbase3"
EXECUTION_BASE_4 = "run-unitbase4"
