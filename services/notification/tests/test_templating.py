from app.templating import render


def test_render_substitutes_known_placeholders():
    assert render("Hello {{name}}, alert on {{service}}", {"name": "Sam", "service": "auth"}) == (
        "Hello Sam, alert on auth"
    )


def test_render_leaves_unmatched_placeholder_as_is():
    assert render("Hello {{name}}", {}) == "Hello {{name}}"


def test_render_handles_whitespace_inside_braces():
    assert render("{{ name }}", {"name": "Sam"}) == "Sam"


def test_render_with_no_placeholders_returns_unchanged():
    assert render("plain text, no substitutions", {"unused": "value"}) == "plain text, no substitutions"


def test_render_substitutes_same_key_multiple_times():
    assert render("{{x}} + {{x}} = double {{x}}", {"x": "5"}) == "5 + 5 = double 5"
