# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and follows semantic intent.

## [Unreleased]

## [0.1.0] - 2026-02-17

### Added

- Memory routing by `memory_kind` (`semantic`/`episodic`/`procedural`) across write/retrieve/recall.
- Explicit remember-hook in ask flows (CLI + MCP) with short-circuit for pure remember commands.
- Consolidation and supersede trails for contradictory memory values.
- Retrieval feedback reranking loop with decay and cluster-cap controls.
- Scope isolation and default scope fallback (`user_id`/`project_id`/`session_id`) across CLI + MCP memory flows.
- Optional PII egress policy (`off`/`pseudonymize`/`redact`) with run-log reason codes.
- Codex Desktop MCP bootstrap script and mobile CLI wrappers.
- Intake UI drag-and-drop support plus quick-action buttons (`Importera`, `Fraga`, `Kom ihag`, `TODO`) with in-UI explanations.

### Changed

- README expanded with Codex UI flow, mobile flow, and new policy/scope controls.
- Research index extended with AI Act + GDPR egress guidance.

