"""A hand-maintained roadmap is a lying instrument by construction.

The repo currently carries FOUR of them:

    docs/ace-master-roadmap.md
    docs/ace-roadmap.md
    docs/ace-roadmap-2026-06-25-refresh.md
    docs/ace-world-class-roadmap.md

Four roadmaps is no roadmap: a collaborator cannot tell which one is real. And every one is
hand-written markdown, so each began rotting the moment the next commit landed.

We have proof this is not theoretical. The DATABASE roadmap — the one that is supposed to be live —
had drifted so far that five specs said "build this" while the thing sat in the repo with eleven
test files. If the source of truth drifts, a copy of it typed out by hand has no chance.

So the roadmap is GENERATED: statuses come from the database, areas come from a human-owned manifest,
and the file says when it was generated and forbids hand-editing. The one judgement a machine cannot
make — which subsystem a piece of work belongs to — stays with a person, in a versioned file.

And it never silently drops anything. A spec that fits no area lands in "Unsorted", visibly, because
a roadmap that quietly omits work is the same lie in a politer voice.
"""

from __future__ import annotations

from core.engine.product.roadmap_doc import generate_roadmap


def _spec(objective, status="draft", capability=None, area=None):
    return {"objective": objective, "status": status, "capability_slug": capability, "id": "agent_spec:x"}


AREAS = {
    "voice": {"title": "Voice", "blurb": "The spoken layer.", "capabilities": ["voice_stream", "tts"]},
    "canvas": {"title": "Canvas & Surfaces", "blurb": "What you look at.", "capabilities": ["portal_graph"]},
}


def test_specs_are_grouped_into_their_areas():
    md = generate_roadmap(
        specs=[
            _spec("Ship the voice stream", "approved", "voice_stream"),
            _spec("Canvas onboarding", "draft", "portal_graph"),
        ],
        areas=AREAS,
    )

    assert "## Voice" in md and "## Canvas & Surfaces" in md
    voice_section = md.split("## Voice")[1].split("##")[0]
    assert "Ship the voice stream" in voice_section
    assert "Canvas onboarding" not in voice_section, "a spec must appear under its OWN area"


def test_a_spec_that_fits_no_area_is_shown_not_dropped():
    """A roadmap that quietly omits work is the same lie in a politer voice."""
    md = generate_roadmap(specs=[_spec("Something nobody classified", "draft", "mystery_cap")], areas=AREAS)

    assert "Unsorted" in md
    assert "Something nobody classified" in md
    assert "mystery_cap" in md, "and it must say WHY it is unsorted, so someone can fix the manifest"


def test_shipped_and_in_flight_work_are_distinguished():
    md = generate_roadmap(
        specs=[
            _spec("Done thing", "shipped", "voice_stream"),
            _spec("Being built", "building", "voice_stream"),
            _spec("Waiting on a human", "draft", "voice_stream"),
        ],
        areas=AREAS,
    )

    assert "Done thing" in md and "Being built" in md and "Waiting on a human" in md
    # The three must be visually distinguishable — a reader has to know what is real TODAY.
    assert md.count("✅") >= 1, "shipped work must read as shipped"
    assert "🔨" in md or "in progress" in md.lower()


def test_the_file_says_it_is_GENERATED_and_when():
    """Without this, someone hand-edits it, the edit is silently blown away on the next run, and
    they learn to distrust the whole thing."""
    md = generate_roadmap(specs=[], areas=AREAS)

    low = md.lower()
    assert "generated" in low
    assert "do not edit" in low or "do not hand-edit" in low
    assert "make roadmap" in low or "generate_roadmap" in low, "it must say HOW to regenerate it"


def test_an_empty_area_is_still_listed():
    """Silence is ambiguous: "no voice work" and "we forgot voice exists" must not look the same."""
    md = generate_roadmap(specs=[], areas=AREAS)

    assert "## Voice" in md
    assert "nothing" in md.lower() or "no open work" in md.lower()


def test_a_shipped_pillar_with_no_specs_does_not_read_as_neglected():
    """ "Done" and "empty" must not look identical — that is the whole reason this file exists.

    A mature subsystem can carry zero tracked specs precisely because it is finished: the built
    voice-of-product engine, the live extensions, the roadmap tooling itself. Rendering those the
    same as a genuine gap (Spoken Voice) tells a collaborator a shipped pillar is neglected. An area
    the manifest marks `status: shipped` must therefore read as shipped, and a real gap must still
    read as a gap — the two cannot be the same string.
    """
    areas = {
        "built": {"title": "Voice of Product", "blurb": "Built.", "status": "shipped", "capabilities": []},
        "gap": {"title": "Spoken Voice", "blurb": "A real gap.", "capabilities": []},
    }
    md = generate_roadmap(specs=[], areas=areas)

    built = md.split("## Voice of Product")[1].split("## ")[0]
    gap = md.split("## Spoken Voice")[1].split("## ")[0]

    assert "✅" in built or "shipped" in built.lower(), "a built pillar must read as shipped, not blank"
    assert "no open work" in gap.lower() or "nothing" in gap.lower(), "a real gap must still read as a gap"
    assert built.strip() != gap.strip(), "shipped and empty must not render identically"


def test_it_never_raises_on_junk_input():
    """It runs in CI and in a make target. It does not get to crash."""
    md = generate_roadmap(specs=[{"objective": None, "status": None}], areas=AREAS)  # type: ignore[list-item]
    assert isinstance(md, str) and md
