# Clean-user onboarding trial

This protocol measures whether a product builder can move from the public ACE
description to one useful reasoning result without maintainer help or knowledge
of ACE's architecture. It validates the R1 onboarding outcome; it is not a
developer installation rehearsal.

## Trial conditions

- Use a macOS or Linux account that has not previously installed or developed ACE.
- The participant must not be an ACE maintainer and should receive only the public README.
- Start without an ACE checkout, `.env`, database volume, saved bearer token, or running ACE process.
- Docker, `uv`, and the participant's chosen model access may already be installed, but record which
  prerequisites were missing and every intervention needed to supply them.
- Do not coach during the attempt. A request for help is evidence, not a cue to silently repair the trial.

Never collect credentials, task text, model responses, or the participant's private product data.

## Run the trial

The participant follows the README and runs:

```bash
uv sync
uv run ace setup --onboarding-trial
```

They should choose their own provider route and bring a real but non-sensitive
product decision. The activation outcome is a rendered ACE recommendation. A
healthy API or successful database migration alone is not activation.

After the result, verify lifecycle recovery:

```bash
uv run ace service status
uv run ace service stop
uv run ace service start
uv run ace doctor
uv run ace onboarding report
```

If a step fails, follow only the recovery shown by the command. `ace service
logs` may be used when the command directs the participant to inspect the API
log. Record any undocumented command, architecture explanation, or maintainer
action that was required.

## Evidence and pass conditions

`~/.ace/onboarding.jsonl` records privacy-local events for configuration,
readiness, first-result success, elapsed times, prompted interventions, failure
stage, platform, and the two trial self-reports. `ace onboarding report
--json-output` summarizes those events without task or credential content.

A trial passes when all of the following are true:

- setup reaches a completed first reasoning result;
- no maintainer help is reported;
- no ACE architecture knowledge is reported as necessary;
- every failure is recoverable using only the message shown;
- `ace doctor` passes after stopping and restarting the managed service;
- no credential appears in terminal output, logs, or onboarding evidence.

R1 must not be marked passed from unit tests, maintainer rehearsals, or one
operating system. Complete independent evidence must exist for both macOS and
Linux, with failures and interventions retained rather than edited out.

Before sharing evidence, the participant should inspect it locally and provide
explicit consent. Share only the onboarding JSONL/report and a redacted note of
prerequisites or interventions; never share `.env`, `token.json`, `api.log`, or
the reasoning result.
