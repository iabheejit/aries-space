# Architecture Decisions

## ADR-001: PostgreSQL Is Authoritative After Milestone 3

**Status**: Accepted — 2026-08-15

The live application does not dual-write SQLite. The Milestone 2 SQLite volume and image remain an isolated rollback artifact; post-cutover PostgreSQL writes are not back-ported.

## ADR-002: Object-First Ingestion With Compensation

**Status**: Accepted — 2026-08-15

Raw bytes are uploaded before metadata commits. PostgreSQL advisory transaction locks serialize each source/external-ID pair. A failed commit deletes only an object proven to have been created by that attempt. Ambiguous upload ownership is never deleted automatically.

## ADR-003: Verify Bytes, Not Object Metadata

**Status**: Accepted — 2026-08-15

Existing MinIO objects are downloaded and SHA-256 hashed before idempotent success. MinIO metadata is informational and never the provenance authority.

## ADR-004: Preserve MissionOps During Aries Expansion

**Status**: Accepted — 2026-08-15

Pass prediction, health, observations, and the Jinja dashboard remain the user-facing regression surface while storage changes. React, runners, ONNX workloads, metrics, and reports are introduced only in later milestones.
