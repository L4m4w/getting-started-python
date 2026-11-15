"""Фиктивные входы для 22B unit-регрессий оркестратора (durable PR body
payload и checkpoint читаемого create number). Только данные этих
тестов: тела PR в разных окончаниях строк/алфавитах, байты невалидного
UTF-8, номера remote PR и execution id для lineage. Реальных SHA/ID и
кредов нет — все проверки offline в temp dirs.
"""

# Тела PR: digest считается по точным UTF-8 bytes — без trim и без
# преобразования переводов строк.
BODY_REL = "docs/pr-body.md"
BODY_TEXT = "Unit PR body\nsecond line\n"
BODY_TEXT_CRLF = "first\r\nsecond\r\n"
BODY_TEXT_UNICODE = "Тело PR — описание изменений\n"
BODY_TEXT_ALT = "changed body after prepare\n"
BODY_EMPTY = ""
BODY_INVALID_UTF8 = b"\xff\xfe\x00not-utf8"

# Номера remote PR, записанных fake transport'ами.
PR_NUMBER = 200
PR_NUMBER_SECOND = 201
PR_LINEAGE_NUMBER = 88
PR_URL_TEMPLATE = "https://git.invalid/pr/{number}"

# Execution id для additional lineage/probe setups (уникальные на
# project, чтобы evidence не пересекались).
EXECUTION_HEAD_6 = "run-unithead6"
EXECUTION_BASE_6 = "run-unitbase6"
EXECUTION_HEAD_7 = "run-unithead7"
EXECUTION_BASE_7 = "run-unitbase7"
