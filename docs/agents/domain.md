# Domain Docs

This repo uses a single domain context for CLO–JD comparison and Chat.

## Before exploring

- Read root `GLOSSARY.md` when it exists.
- Read existing ADRs under `docs/adr/` that concern the area being changed.
- If these documents are absent, proceed silently. The domain-modeling skill creates them lazily when terminology or decisions are resolved.

## Layout

- `GLOSSARY.md`: shared domain vocabulary for the backend and frontend.
- `docs/adr/NNNN-<decision-slug>.md`: architecture decision records.

## Vocabulary

Use glossary terms in issue titles, proposals, hypotheses, and test names. When a needed term is missing, check current project usage and note a real vocabulary gap for domain-modeling.

## Decisions

Surface any conflict with an existing ADR explicitly, identify the ADR, and explain why the decision should be reopened.
