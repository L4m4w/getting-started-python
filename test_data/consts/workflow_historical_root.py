"""Константы данных для регрессий 33-P-B: записанный внешний evidence
root исторического base-execution (import-execution --evidence-root)."""

# Каталог внешнего исторического project root под tmp_path.
EXTERNAL_ROOT_NAME = "historical-checkout"
# Каталог второго внешнего root для конфликта recorded vs caller.
CONFLICT_ROOT_NAME = "historical-checkout-2"
# Каталог-мишень symlink-эскейпа за пределами evidence root.
ESCAPE_TARGET_NAME = "outside-evidence"
# Относительный путь — недопустимое значение --evidence-root.
RELATIVE_ROOT = "relative/evidence-root"
# Относительный manifest artifact path с выходом за пределы root.
TRAVERSAL_ARTIFACT = "../../../../escaped-junit.xml"
# Абсолютный manifest artifact path (запрещён для внешнего evidence).
ABSOLUTE_ARTIFACT = "/tmp/absolute-junit.xml"
# Абсолютный путь source copy (запрещён).
ABSOLUTE_SOURCE_COPY = "/etc/passwd"
# Id head execution второй ревизии для rebind-проверки.
EXECUTION_HEAD_R2 = "run-unithead-r2"
# Маркер подделанной provenance для конфликта recorded vs caller.
FORGED_JUNIT_SHA256 = "0" * 64
# Имя постороннего файла-цели за пределами evidence root.
FOREIGN_PAYLOAD_NAME = "foreign-payload.json"
# Имя постороннего manifest-цели для эскейпа manifest.json.
FOREIGN_MANIFEST_NAME = "foreign-manifest.json"
# Имена escaping members внутри allure-results.
ESCAPE_RESULT_NAME = "zz-escape-result.json"
ESCAPE_CONTAINER_NAME = "zz-escape-container.json"
ESCAPE_ATTACHMENT_NAME = "zz-escape-attachment"
# Имя escaping member внутри sources/ и testops state dir.
ESCAPE_MEMBER_NAME = "zz-escape-member"
# Имя каталога-цикла внутри allure-results.
CYCLE_DIR_NAME = "cycle"
# Каталог, куда переносится external root при revalidation-проверке.
MOVED_ROOT_NAME = "historical-checkout-moved"
# Каталог package dir вне testops state dir для member-эскейпа.
DETACHED_PACKAGE_NAME = "detached-package"


# Malformed manifest container fixtures for controlled refusal (34V-A F1).
MALFORMED_MANIFEST_CONTAINERS = (
    (("artifacts",), "invalid-object"),
    (("source_identity",), ["invalid-object"]),
    (("environment",), "invalid-object"),
    (("environment", "declared"), ["invalid-object"]),
    (("environment", "container_check"), "invalid-object"),
    (("selection",), "invalid-object"),
    (("selection", "targets"), [17]),
    (("repository",), "invalid-object"),
    (("source_identity", "copies"), "invalid-list"),
    (("environment", "declared", "app_base_sha"), 17),
    (("repository", "commit"), 17),
    (("artifacts", "sources"), 17),
)
NON_REGULAR_RESULT_NAME = "unsupported-result.json"
NESTED_ROOT_NAME = "nested-historical-root"
