# Build your first extension

Extensions grow new arms on the octopus: the kernel reasons; your extension
teaches it your domain — personas, frameworks, recipes, instruments, tools,
schema — without forking it. You never edit the kernel. You never edit a
central registry. You write a package, and the kernel finds it.

This tutorial assumes you already have ACE running locally. In five steps
you'll generate a real extension, tour every file it contains, run it in the
dev loop against your own thought, package it for real installation, and know
exactly what you can rely on going forward.

## 1. Scaffold

Extensions are never built from a blank file — they're built by copying the
one ACE already ships and runs: `extensions/reference/`. The scaffold does
that copy and the renaming for you, so your starting point is never a stub;
it's a fully worked, fully wired example with your domain's name on it.

    python -m scripts.scaffold_extension green_energy --dir ..

The first argument is your extension's name — snake_case, becomes both the
Python package prefix and the discipline it registers under. `--dir` is where
the generated project lands; `..` puts it as a sibling of the ACE repo, which
is the normal layout (your extension is its own package, its own git
history, its own release cadence — it does not live inside the kernel's
tree).

That command produces:

    ../ace-ext-green-energy/
      pyproject.toml
      README.md
      green_energy_extension/
        __init__.py
        extension.py
        recipe.py
        sentinels.py
        instruments/
          __init__.py
          framing.py
          multi_voice_engage.py
        tools/
          __init__.py
          green_energy_pulse.py

Every identifier is already renamed for you: the class is
`GreenEnergyExtension`, the discipline is `green_energy`, the recipe is
`green_energy_decision_intelligence`, the MCP tool is `ace_green_energy_pulse`.
Nothing here is a placeholder waiting for search-and-replace — it's a
complete, working extension for the domain "green_energy" that happens to
reason about product decisions, because that's what the reference extension
does. Everything from here is *your* edit, on top of a base that already
imports cleanly and registers cleanly.

## 2. What you got

Open `green_energy_extension/extension.py` first — it's the entry point, and
it's deliberately short. Its `register(reg)` method is the only place your
extension talks to the kernel, and it does so entirely through the
`Registry` facade documented in [`extension-api.md`](extension-api.md). Four
extension points are live in the generated file; five more appear as
commented one-liners so you can see the entire Registry surface in one
place, whether or not the open kernel consumes them yet.

| File | Registry call | What it teaches the kernel |
|---|---|---|
| `extension.py` | (calls the others below) | The entry point — everything routes through `register(reg)` |
| `instruments/framing.py`, `instruments/multi_voice_engage.py` | `reg.register_instrument(slug, module_path)` | Bespoke LLM pipeline steps your recipe can call by slug |
| `recipe.py` | `reg.register_recipe(name, module_path, disciplines=[...])` | The meta-skill the composer selects when a thought classifies to your discipline |
| `tools/green_energy_pulse.py` | `reg.register_tool(fn, title=...)` | An MCP tool — `ace_green_energy_pulse` — exposed to any MCP client the same way kernel tools are |
| `sentinels.py` | `reg.register_sentinel(name, cron=..., fn=...)` | A 24/7 engine the kernel scheduler runs on a cron, present or not |

Read `recipe.py`: five phases (Frame → Reality → Voices → Tradeoffs →
Recommend) that turn a raw thought into a bounded recommendation with kill
criteria. The `Voices` phase is worth lingering on — it calls
`multi_voice_engage`, which wraps the kernel's own `execute_engagement`
primitive to convene multiple archetypes (a PM, a Skeptic, a User-Advocate)
from *inside* a recipe phase. No bespoke roster, no hardcoded personas — just
the kernel's generic archetypes, engaged on your domain's terms. This is the
partnership thesis showing up as a single phase of a recipe.

Each of these files maps one-to-one to a `Registry` method, and every method
you see called is listed, with its exact contract, in
[`extension-api.md`](extension-api.md) — that document is the map; this
package is the territory.

## 3. Run it (dev loop)

You don't need to publish a package to try an extension — but you do need to
know where extensions actually load. The `ace` CLI is a thin HTTP client: it
POSTs your thought to a running engine and prints the result. Extensions are
discovered inside the **engine process** — the kernel's recipe loader,
instrument registry, and sentinel scheduler all load them there. So
`ACE_EXTENSIONS` must be set in the environment of the process that serves,
not on a one-off client command (prefixing an `ace` invocation with it does
nothing).

First, the ten-second check that the kernel can see your package at all.
From the ACE repo root:

    PYTHONPATH=../ace-ext-green-energy \
    ACE_EXTENSIONS="green_energy_extension.extension:GreenEnergyExtension" \
    uv run python -c "from core.engine.extensions.loader import load_extensions; print(load_extensions())"

The printed list includes
`green_energy_extension.extension:GreenEnergyExtension` alongside the
built-in extensions. `ACE_EXTENSIONS` is a comma-separated list of
`module.path:ClassName` specs the loader resolves in addition to anything
installed through the `ace.extensions` entry point; `PYTHONPATH` puts the
unpackaged project on the import path. No `pip install`, no packaging step.
(This flow is exercised by the kernel's test suite —
`tests/extensions/test_build_your_first_tutorial.py` — so it can't drift
from a working flow.)

Now the live loop. Export the same two variables in the shell that launches
the engine, then start it (or restart it if it's already running):

    export PYTHONPATH="$PWD/../ace-ext-green-energy"
    export ACE_EXTENSIONS="green_energy_extension.extension:GreenEnergyExtension"
    make dev

Watch the startup log — the loader announces
`loaded extension: green_energy`. Your extension is now in the serving
process.

Before the first `ace run`, the CLI needs a bearer token: `POST /tasks`
(what `ace run` calls) requires one, minted from `POST /auth/token` using
the `API_KEY` in your `.env`. Run:

    export API_KEY=$(grep '^API_KEY=' .env | cut -d= -f2)
    ace login --api-key "$API_KEY"

(omit `--api-key` and it prompts for the key instead; `ACE_API_KEY` also
works). `ace login` exchanges the key for a bearer token via
`POST /auth/token` and writes it to `~/.ace/token.json`
(`core.engine.cli.auth.get_token` reads it back), chmod'd to `0600` — the
file holds a live bearer credential, and the default umask would otherwise
leave it world-readable on a shared machine or CI runner. (The manual
`curl -X POST .../auth/token | python -c '...'` bootstrap this replaced
still works too, for scriptable/CI setups where prompting isn't an
option.) The token is good for `JWT_EXPIRE_MINUTES` (24h by default);
every `ace` subcommand picks it up automatically after this, no flag
needed. From a second terminal, drop a thought in:

    ace run "should we prioritize the residential inverter line over the commercial one next quarter?"

(or use the canvas at `http://localhost:5173`). Because the scaffold
registered `green_energy_decision_intelligence` under
`disciplines=["green_energy"]`, a thought that classifies to your domain
routes to your recipe instead of the kernel's default reasoning — your PM,
your Skeptic, and your User-Advocate reason through it, using your recipe's
five phases. This is the whole loop: write an extension, load it into the
engine's environment, and the kernel's behavior changes without a single
kernel file touched.

## 4. Package it

The dev loop is for iteration. For anything that runs unattended — CI, a
teammate's machine, a production deploy — package the extension properly so
the kernel discovers it the same way it discovers any installed dependency:

    cd ../ace-ext-green-energy
    pip install -e .

That installs `ace-ext-green-energy`, whose `pyproject.toml` declares the
entry point the scaffold wrote for you:

```toml
[project.entry-points."ace.extensions"]
green_energy = "green_energy_extension.extension:GreenEnergyExtension"
```

`core.engine.extensions.loader.load_extensions()` reads the `ace.extensions`
entry-point group at boot, resolves `green_energy_extension.extension:GreenEnergyExtension`,
and registers it — no `ACE_EXTENSIONS` needed once it's installed. This is
also how you'd distribute an extension to someone else: publish
`ace-ext-green-energy` anywhere pip can reach it (a private index, a git URL,
a wheel), and `pip install` is the entire integration step on their end.

## 5. Stability

Everything you just wired — `register_instrument`, `register_recipe`,
`register_tool`, the `ace.extensions` entry-point group itself — is part of
the **Stable** surface: it changes only on a kernel MAJOR release, with
migration notes in the changelog. `register_sentinel`, the one you used for
the heartbeat engine, is currently **Experimental** and may change on a
MINOR release. The full table, with exact method signatures, lives in
[`extension-api.md`](extension-api.md) — read it before you build past this
tutorial's worked example, and check it again before every kernel upgrade.

The contract that matters most: the dependency direction is one-way.
Extensions import the kernel; the kernel never imports extensions. Nothing
you do here can be a load-bearing kernel dependency, by construction — which
is exactly what makes it safe to build your own arm on the octopus without
ever forking it.

## Where to go from here

You now have a full extension of your own, generated from the same worked
example the kernel ships and tests against. From here it's your domain:
rewrite the recipe's five phases for how reasoning actually works in green
energy, replace the framing instrument with one tuned to your inputs, point
`green_energy_pulse` at your own data instead of the reference's placeholder
read. The scaffold got you a working skeleton in one command; everything
past that is the extension only you could write.
