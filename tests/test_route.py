import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins/clay/scripts"))
from route import Rule, load_rules, route  # noqa: E402

RULES = [
    Rule("**/*.vue", "ui"),
    Rule("**/*.vue", "ux"),
    Rule("**/components/**", "ui"),
    Rule("**/auth/**", "security"),
    Rule("composer.lock", "security"),
]


def test_docs_only_returns_code():
    assert route(["README.md", "docs/a.md", ".github/ci.yml"], RULES) == ["code"]


def test_vue_file_adds_ui_and_ux():
    assert route(["src/Page.vue"], RULES) == ["code", "ux", "ui"]


def test_auth_path_adds_security():
    assert route(["app/auth/Login.php"], RULES) == ["code", "security"]


def test_multiple_matches_deduplicated():
    out = route(["src/components/A.vue", "src/components/B.vue"], RULES)
    assert out.count("ui") == 1


def test_order_is_fixed():
    out = route(["src/Page.vue", "composer.lock"], RULES)
    assert out == ["code", "security", "ux", "ui"]


def test_root_file_matches_double_star_prefix():
    assert route(["Page.vue"], RULES) == ["code", "ux", "ui"]


def test_load_rules_ignores_header_and_blank_lines(tmp_path):
    f = tmp_path / "routing.md"
    f.write_text("# Routing\n\n| glob | reviewer |\n|------|----------|\n| `**/*.vue` | ui |\n\n| composer.lock | security |\n")
    assert load_rules(f) == [Rule("**/*.vue", "ui"), Rule("composer.lock", "security")]


REAL = load_rules(HERE.parent / "plugins/clay/routing.md")


def test_nested_manifests_and_env_route_to_security():
    for p in ["frontend/package.json", "apps/web/.env", "backend/routes/api.php", "svc/go.mod"]:
        assert "security" in route([p], REAL), p


def test_docs_paths_do_not_pull_reviewers():
    assert route(["docs/components/x.md", "docs/auth/y.md", "docs/pages/z.md"], REAL) == ["code"]


def test_code_under_components_still_routes():
    assert "ui" in route(["src/components/Button.ts"], REAL)


def test_brace_alternation_in_glob():
    rules = [Rule("**/auth/**/*.{php,py}", "security")]
    assert route(["a/auth/x.php"], rules) == ["code", "security"]
    assert route(["a/auth/x.py"], rules) == ["code", "security"]
    assert route(["a/auth/x.md"], rules) == ["code"]


def test_markup_and_style_extensions_beyond_vue_and_tsx_reach_the_interface_reviewers():
    for p in ["templates/home.html", "views/layout.twig", "app/page.astro", "ui/Button.jsx", "mail/welcome.erb"]:
        assert route([p], REAL) == ["code", "ux", "ui"], p
    for p in ["styles/app.sass", "theme/dark.less"]:
        assert route([p], REAL) == ["code", "ui"], p


def test_plain_js_and_ts_count_only_inside_the_folders_that_hold_screens():
    assert route(["server/index.js", "lib/format.ts", "scripts/build.mjs"], REAL) == ["code"]
    assert route(["src/layouts/main.js"], REAL) == ["code", "ui"]
    assert route(["src/screens/home.ts", "src/forms/login.mjs"], REAL) == ["code", "ux"]
    assert route(["web/widgets/chart.ts"], REAL) == ["code", "ui"]
