# Clean context — final proposed

Статус: `final proposed`. Функциональный контекст фактически проверен
независимым review 34V-B, но документ ещё не принят в workflow и не входит
в commit. Путь принят координатором в рамках 32-review; source-write и
включение в `QA_FINAL` остаются будущими отдельными разрешениями.
Собственный будущий QA SHA здесь не фиксируется.

## Фактическая идентичность

| Компонент | Значение |
| --- | --- |
| Пилот | `category-update-validation` / `CAT-UPD-VAL` |
| APP canonical repo | `github.com/L4m4w/niffler-py-st3` |
| APP isolated checkout | `/Users/zenalark/.codex/worktrees/niffler-app-head/niffler-py-st3` |
| APP base | `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` |
| APP head | `0dcb50d2177ee2958189425a614b5bd0864d56d8` |
| APP branch/tree | `fix/cat-upd-val-gateway-validation` / `61a3e013efcf84bed62c2b05e111993dce447f24` |
| APP status | clean; head kind = `commit`; parent = `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` |
| QA canonical repo | `github.com/L4m4w/getting-started-python` |
| QA isolated checkout | `/Users/zenalark/.codex/worktrees/niffler-qa-head/getting-started-python` |
| QA frozen head | `2fa6c537016b9a5148117b5a348a158859062fec` |
| QA final head | определяется только после будущего commit; не угадывать |

QA canonical repo фиксируется принятым интерфейсом `init --tests-repo` →
`identity.tests_repo`: canonical remote отдельно от `locals.tests_repo_path`
(локальный checkout для commit/dirty/tree gates). Workflow ID и index key от
canonical remote не зависят: same repo + pilot + app base сохраняют линию.
Routing/code review этого интерфейса выполняется отдельным gate 34V-A и не
подтверждается этим документом.

## Сохраняемый контракт

Требование `requirement.md` версии `1`, SHA-256 `38d8455608f08ac5e8380422d56ded005eb6ed57ea36d1812ecadd560326467c`: R1–R4 без новых
ожиданий. Сценарии `scenarios.md` версии `2`, SHA-256 `a8cc7dab3a21b1b8a631c7d4c4d283a5f0f970b0c1df4b06660fa49f67a22686`: шесть
случаев сохраняются по доказанной source/scenario equivalence; их статусные
фразы про исторические прогоны читаются как историю, а не как новая проверка.
Scenario artifact digest: `98a4c6bedecb13ef6bfe19041d259af11446eea68052fea993aaedf38a9ebc0b`.

| Requirement | Scenarios |
| --- | --- |
| `R1` | `CAT-UPD-VAL-001`, `CAT-UPD-VAL-002` |
| `R2` | `CAT-UPD-VAL-003`, `CAT-UPD-VAL-004`, `CAT-UPD-VAL-005`, `CAT-UPD-VAL-006` |
| `R3` | `CAT-UPD-VAL-001`, `CAT-UPD-VAL-002`, `CAT-UPD-VAL-003`, `CAT-UPD-VAL-004` |
| `R4` | `CAT-UPD-VAL-005`, `CAT-UPD-VAL-006` |

## Actual APP context sources

Координатор подтвердил: девять sources достаточно для functional context этой
`@Valid` правки; build provenance — отдельный manifest, не заменяющий
functional scope. В 34V-B все SHA-256 и Git blob ID пересчитаны по APP
checkout и совпали.

| Path | SHA-256 | Git blob |
| --- | --- | --- |
| `niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java` | `32aec8fbd7a7a4533327a3eabeaccb5ba917ae3c0de338dac621c9025830b8a9` | `5582684592bbea973c43a14230fa8031b76b94a7` |
| `niffler-gateway/src/main/java/guru/qa/niffler/model/CategoryJson.java` | `d0e0fb63fd34e6b239d0c25596ba106b712d7326aae1164bc5d7e06e5191d552` | `a05e61cf26fd6e0be784e9a693d1573cced22fda` |
| `niffler-gateway/src/main/java/guru/qa/niffler/service/GlobalExceptionHandler.java` | `84895358ad9db3dcdbe3a955da6b713ae10ffabe72be7dfa226df13f2e0b9ede` | `b2b6a2e796fc2ea96b222332f14b9fe1d006f2a3` |
| `niffler-spend/src/main/java/guru/qa/niffler/service/CategoryService.java` | `f2e56a6ac07a68c1a34ee2e1a05df872c8215dbaf14fa9a5937b6537e5f65ba8` | `1e0385b34178a1072053217b08f2f6a20efc0357` |
| `niffler-spend/src/test/java/guru/qa/niffler/controller/CategoriesControllerTest.java` | `e4d2e539de94ba6fde39c89622855a8ec2f05ea91c79866e7dec4fb715d5bd2d` | `b4d423db89b2f3f336d7497d3d04a966f463ba3f` |
| `niffler-spend/src/test/java/guru/qa/niffler/service/CategoryServiceTest.java` | `80a2ea0ade155e81c589902cbbbde48b846b33ad2108c9f7aeee70f928967f48` | `e4ca2a64ddc395ec2bb61cd9aea63f92abfa5400` |
| `settings.gradle` | `cd037f0e5c9e342a44cc9ec367df317cd2fbeaa624f606bf19fd19485ca2eb06` | `4b3f8cbfcd5b95640eb385b35d182b24ae00489a` |
| `niffler-spend/src/main/resources/application-test.yaml` | `5bdaa6e5ba6a678eaa2e6d1e18bcbb97e43e71090e1ec8dae0b81c3148544446` | `b7726330814371aa1a2481278382545063625f79` |
| `niffler-gateway/src/test/java/guru/qa/niffler/controller/CategoriesControllerValidationTest.java` | `eea6de8d14f8d5f1b7bb84dd2dd384b1d03e3056daad39dacc9568515604ca50` | `9bedafd0bbbd52ecef682bdae790ea4797019ed0` |

## Границы provenance

- `run-vzsatlfk` — только принятый historical baseline по
  `accepted-baseline-record.json`; повторно не обозначать и не запускать.
  В новом store импортируется принятым интерфейсом `import-execution
  --evidence-root <absolute HIST root>` вместе с `--provenance` accepted
  record; внешний evidence root остаётся read-only навсегда (без locks/tmp/
  state/package writes и без delegated TestOps effects в исторический root).
- `run-ni_5bvnc` и launch `57317` — immutable historical evidence старой
  QA revision/base+patch; не импортировать как head clean commits.
- Требуется один новый actual head API execution после `QA_FINAL`, отдельного
  runtime/build разрешения и успешных artifact gates.
- Build/image readiness — отдельный план (33c `readiness-plan.md` в
  artifacts): rebuild auth/spend/gateway, полный Gradle configuration
  fingerprint, минимальный env без inherited real tokens, image pin/no-pull
  policy, суммарный 180-секундный readiness budget, exact username cleanup
  и узко разрешённый orphan cleanup. Этот документ не утверждает выполнение
  build, API run, GitHub или TestOps операций.
