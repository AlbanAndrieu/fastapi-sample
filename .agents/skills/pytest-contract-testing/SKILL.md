---
name: pytest-contract-testing
description: >-
  Pytest test-design rules for stable structured contracts, security-sensitive
  URL assertions, diagnostics, API payloads, and regression tests. Use whenever
  creating or modifying Python tests under tests/, especially health, topology,
  provider, URL, security, or observability tests.
---
# Pytest contract testing

Use pytest assertions to validate the strongest available contract, not a convenient rendering of that contract.

## Prefer structured fields over rendered text

When production code exposes structured data, assert the structured field directly with exact equality.

Prefer:

```python
selected = diagnostics["stages"][0]
assert selected["target_url"] == "https://truenas.albandrieu.com:7000"
assert selected["resolved"] == ["172.17.0.24"]
assert diagnostics["path_mode"] == "direct_lan"
```

Do not use free-form text as a proxy for the same contract:

```python
assert "https://truenas.albandrieu.com:7000" in selected["detail"]
assert "172.17.0.24" in selected["detail"]
assert "direct LAN" in selected["detail"]
```

This is especially important for URLs, hosts, ports, addresses, identifiers, states, booleans, counts, versions, enum-like values, and security decisions.

## URL and security assertions

Never express URL trust, allowlisting, routing, SSRF protection, redirect validation, or endpoint identity with substring membership such as:

```python
assert "https://trusted.example" in value
```

A trusted URL may occur at an arbitrary position in an unrelated or malicious string. This pattern can trigger CodeQL `py/incomplete-url-substring-sanitization` and, in production code, can represent a real validation flaw.

For structured URL contracts, compare the whole normalized value or parsed components:

```python
assert result["target_url"] == "https://trusted.example:443"
assert result["host"] == "trusted.example"
assert result["port"] == 443
```

If the production behavior itself is validating an untrusted URL, parse it first and test scheme, hostname, port and path as separate semantic fields rather than relying on string containment.

## When text containment is appropriate

Substring assertions remain appropriate when the text itself is the contract and no structured equivalent exists, for example a human-facing warning or diagnostic explanation:

```python
assert "could not be confirmed" in stage["detail"]
```

Before writing such an assertion, check whether the same fact already exists as a structured field. If it does, assert that field instead. Text assertions should normally cover wording semantics only, not endpoint identity or security state.

## Regression-test review checklist

For every new or modified pytest test:

- identify the semantic field being validated;
- prefer exact equality for structured scalar/list/dict values;
- use set/list membership only when collection membership is the actual contract;
- avoid URL/host/IP substring assertions against `detail`, `message`, `warning`, `reason`, `error`, HTML or logs when a structured field exists;
- assert status/state separately from explanatory prose;
- keep tests deterministic and independent of external network state unless explicitly marked integration tests;
- when CodeQL reports incomplete URL substring sanitization in a test, do not suppress it automatically: first replace weak rendered-text assertions with structured assertions where possible.

## Agent workflow

After changing pytest tests, run the repository's deterministic local fix/quality flow until it converges before publication. Formatter rewrites may require multiple passes. Do not weaken CodeQL, Ruff, pre-commit, or pytest checks merely to silence an assertion-design warning.
