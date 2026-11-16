# Вспомогательные функции

[Оглавление каталога](README.md)

Новые вспомогательные функции работы с тестовыми данными размещаются
в `test_data/utils/`. Инфраструктурные helpers описаны в [отдельном разделе](infrastructure.md).
Здесь указаны текущие пути существующих функций.

| Компонент | Путь импорта | Назначение | Пример использования |
| --- | --- | --- | --- |
| `unique_username` | `test_data.utils.users.unique_username` | Генерация уникального имени пользователя | `username = unique_username()` |
| `unique_password` | `test_data.utils.users.unique_password` | Генерация пароля для тестового пользователя | `password = unique_password()` |
| `unique_user` | `test_data.utils.users.unique_user` | Генерация учётных данных нового пользователя без регистрации на стенде | `user = unique_user()` |
| `load_existing_user` | `test_data.utils.users.load_existing_user` | Загрузка учётных данных из окружения или переданного mapping | `user = load_existing_user()` |

Параметры генерации (префикс имени и длины значений) вынесены
в `test_data/consts/users.py`.

Имена также доступны через реэкспорт `test_data` (`from test_data import unique_user`).


## Workflow test-data helpers для clean revision

Путь импорта: `from test_data.utils import workflow as utils`.

| Helper | Назначение | Пример |
| --- | --- | --- |
| `Project.init(..., tests_repo=...)` | Передаёт canonical remote отдельно от checkout; default synthetic remote из workflow_tests_repo | `project.init(tests_repo=RC.TESTS_REPO)` |
| `historical_acceptance(evidence_dir, *, review_doc, historical_sha, current_sha, changed_file=None)` | Synthetic accepted-baseline record с реальными digest temp evidence; не авторизует изменение production registry | `utils.historical_acceptance(ev, review_doc=doc, historical_sha=old, current_sha=new)` |
| `move_evidence(src_root, dst_root, execution_id)` | Перенос temp harness evidence между temp project roots, без использования реальной истории | `utils.move_evidence(project.root, ext_root, C.EXECUTION_BASE)` |
| `snapshot_tree(root, *, include_artifacts=False)` | Прежний bytes snapshot; optional artifacts, symlink text без чтения target bytes | `utils.snapshot_tree(ext_root, include_artifacts=True)` |
| `snapshot_tree_metadata(root, *, include_artifacts=False)` | Отдельный no-write snapshot: relative names/types, dirs включая empty, mode/mtime_ns, file SHA и symlink text; atime исключён | `utils.snapshot_tree_metadata(ext_root, include_artifacts=True)` |

Helpers относятся к тестовым данным. Их исполнение может писать temp fixture
files; runtime разрешение тестов не означает разрешение менять HIST artifacts.
