from __future__ import annotations

from core.engine.arms.design_enforce import scan_design_violations


def _write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_clean_surface_has_no_violations(tmp_path):
    _write(
        tmp_path,
        "app/Good.tsx",
        "import { Card, Button } from '../design/components'\n"
        "export const Good = () => <Card><Button>Go</Button></Card>\n",
    )
    assert scan_design_violations(str(tmp_path)) == []


def test_flags_hex_native_radix_emoji_borderleft(tmp_path):
    _write(
        tmp_path,
        "app/Bad.tsx",
        "import * as Dialog from '@radix-ui/react-dialog'\n"
        "export const Bad = () => (<div style={{ color: '#0070F3', borderLeft: '1px' }}>\n"
        "  <input /> <button>x</button> 🚀</div>)\n",
    )
    v = scan_design_violations(str(tmp_path))
    joined = " ".join(v)
    assert any("hex" in x for x in v)
    assert any("@radix-ui" in x for x in v)
    assert any("<input>" in x for x in v)
    assert any("<button>" in x for x in v)
    assert any("borderLeft" in x for x in v)
    assert any("emoji" in x for x in v)
    assert "app/Bad.tsx" in joined


def test_ignores_node_modules_and_non_tsx(tmp_path):
    _write(tmp_path, "app/node_modules/x.tsx", "const x = '#ffffff'\n")
    _write(tmp_path, "app/readme.md", "color: #ffffff\n")
    assert scan_design_violations(str(tmp_path)) == []


def test_missing_root_returns_empty():
    assert scan_design_violations("/nonexistent/path/xyz") == []


def test_flags_white_text_on_light_card(tmp_path):
    # noLightTextOnLightCard mirror: light surface + white text on one line = invisible text.
    _write(
        tmp_path,
        "app/Invisible.tsx",
        "export const I = () => <div className='bg-card text-primary-foreground'>hi</div>\n",
    )
    v = scan_design_violations(str(tmp_path))
    assert any("invisible text" in x for x in v), v


def test_dark_cta_pairing_is_allowed(tmp_path):
    # bg-primary + text-primary-foreground is the correct dark CTA pairing — must NOT flag invisible.
    _write(tmp_path, "app/Cta.tsx", "export const C = () => <div className='bg-primary text-primary-foreground'/>\n")
    v = scan_design_violations(str(tmp_path))
    assert not any("invisible text" in x for x in v), v
