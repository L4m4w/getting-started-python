# Clean implementation — final proposed

Статус: `final proposed`; реализация сохраняется по доказанной побайтной
эквивалентности и статическому review механики, а не новым authoring.
Документ ещё не принят workflow и должен войти в `QA_FINAL`. Никакие
compile/list/API checks этим файлом не заявлены выполненными.

## Сохраняемая реализация

`implementation.payload.test_files` должен содержать ровно
`tests/api/test_category_update.py`. Два параметризованных теста дают шесть
ожидаемых node IDs:

- `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-001]`
- `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-002]`
- `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-003]`
- `tests/api/test_category_update.py::test_update_category_rejects_invalid_name[CAT-UPD-VAL-004]`
- `tests/api/test_category_update.py::test_update_category_accepts_name_at_length_boundary[CAT-UPD-VAL-005]`
- `tests/api/test_category_update.py::test_update_category_accepts_name_at_length_boundary[CAT-UPD-VAL-006]`

## api-contract-v1 source equivalence

В 34V-B все 15 SHA-256 пересчитаны по isolated QA checkout и совпали с
принятым `api-source-equivalence.json`.

| Path | SHA-256 |
| --- | --- |
| `requirements.txt` | `b320a85e2e7a3a22ea6827d4b4490eff47f6a67e4c9b1186b24be9cf0f598974` |
| `conftest.py` | `4594837276006c66819ab4776751e3f97c6c7ec0500e066bff9180d34652ccb0` |
| `settings.py` | `7721e91f0b04fbf8468717f01de7f180d508d9b20984a3a2ab2c3ec1d286e0c3` |
| `infrastructure/http/__init__.py` | `aca13d4d43d77907e5c4fae7c57e40d1c528e8b6a14293a766e0b9878ebd616c` |
| `infrastructure/http/client.py` | `665d1cdf0ee76761e2795ede7c081d13787580b1cda859c8a2059580392d8803` |
| `infrastructure/http/oauth.py` | `8d0066f97541710a0d1793d4be730b5915d8d72f8da3c52816f705446a21251a` |
| `test_data/fixtures.py` | `60e9768178a686c42625d013f3ca42084b006de1c0bcfb5fc1077d8a4dbba27c` |
| `test_data/users.py` | `0b7d24d3b3515d4e4d605e9389492e80b71c92e2bc516dca6025e185fcb68be5` |
| `test_data/utils/users.py` | `47342941b6fc35fbe75ba436b4d4b2797820307fc6ab55d11bc02b198eca6de2` |
| `test_data/consts/users.py` | `676a2823e9681d7764f1217455bb2531820ad9466399c8b8ab722c3785a40325` |
| `test_data/consts/category_update.py` | `c66a9a9f94e6a53286e53105212111217e2113de51f78690790cb664c83d3933` |
| `tests/api/__init__.py` | `232ef7ec555f2a158addd4d61d1ef02a4c99d2650ed631faad25fe55dbd683c9` |
| `tests/api/conftest.py` | `138dc20df565cce6572fea18f3d861ce4baf2184094aa9ba17eebfa025028d64` |
| `tests/api/test_category_update.py` | `ebd9deaa18398c306cac5f9ecacc4c554423477c8e38889fd41847878fa7e359` |
| `tests/unit/test_http_client.py` | `d6c828310a377858f434e0e8cb28cd043b0cd8ed9bc64b39b53bd07cd2514f28` |

## Статически проверенная механика

- PATCH payload — `{**before, "name": name}`: `id`, `username` и `archived`
  берутся из snapshot; меняется только `name`.
- Для cases 001–004 PATCH response и post-PATCH GET записываются в evidence
  до assertions; затем требуются HTTP 400 и точное равенство snapshot
  `id/name/username/archived`.
- Для cases 005–006 после HTTP 200 post-PATCH GET подтверждает точное имя и
  сохранение остальных полей; проверка тела PATCH вторична и не заменяет
  persistence check.
- Fixture читает `excludeArchived=false`, блокирует лимит 8 активных
  категорий и коллизию целевого имени, создаёт уникальное `catupd-<uuid>`
  исходное имя, регистрирует cleanup после валидного UUID.
- Cleanup — `DELETE FROM category WHERE id = %s AND username = %s` по
  сохранённому ID и пользователю, затем контрольный GET; malformed/unknown-ID
  POST фиксируется как orphan risk без слепого удаления.
- OAuth — authorization-code + PKCE/S256 с проверкой `state` и одного `code`;
  callback `frontend.niffler.dc` не запрашивается, переходы вне auth origin
  отклоняются; отрицательные HTTP-статусы не retry'ются.

## Bindings, сохраняемые для нового результата

| Scenario | TestOps ID |
| --- | --- |
| `CAT-UPD-VAL-001` | `55376` |
| `CAT-UPD-VAL-002` | `55374` |
| `CAT-UPD-VAL-003` | `55375` |
| `CAT-UPD-VAL-004` | `55377` |
| `CAT-UPD-VAL-005` | `55373` |
| `CAT-UPD-VAL-006` | `55378` |

## Обязательные проверки перед implementation acceptance

1. Реальный `compile-tests.sh` и `run-tests.sh list` на `QA_FINAL`; старый
   exit 0 не подставлять.
2. Boundary-token совпадение шести сценариев с node IDs; lookalike IDs не
   засчитывать.
3. Fixture/OAuth/SQL cleanup остаются неизменными; `.env` и значения секретов
   не входят в source identity.
4. Новый API manifest должен показать repository=`QA_FINAL`, `dirty=false`,
   app head commit без patch и exact container/image binding.
