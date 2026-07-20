# tests/llm — provider conformance suite.
#
# `conformance.py` defines the behavioral contract every LLMProvider must pass.
# Each `test_<provider>.py` file wires one provider's mocked transport into the
# shared suite. Adding a provider = one small wiring file (see the
# LLMConformanceSuite docstring).
