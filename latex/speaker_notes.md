# Speaker Notes

These notes match the current Beamer source. Solid nodes describe implemented
behavior; dotted nodes describe future extensions.

## Slide 1 — Title

- Objective: Introduce RCA Copilot as an OpenStack component for evidence-first investigation.
- Key point: It converts journal records into traceable incident evidence before any optional AI explanation.
- Transition: Start with the evidence volume faced by an operator.
- Do not claim: AI output is not the source of truth.

## Slide 2 — Evidence Overload

- Objective: Show why manual journal searches do not scale across services.
- Nodes: A visible Nova failure, journald, and the operator's manual search process.
- Key point: The failure is observable; finding the surrounding evidence is the difficult step.
- Transition: Show the distributed service path behind one operation.

## Slide 3 — Distributed OpenStack Evidence

- Objective: Explain that one operation crosses Nova, Keystone, Placement, Neutron, and compute services.
- Edges: Arrows represent operational dependencies and evidence propagation, not proven causality.
- Key point: A downstream error can require upstream evidence from several services.
- Transition: Convert individual records into a common event model.

## Slide 4 — Structured Events

- Objective: Show parsing while preserving raw source lineage.
- Nodes: Raw message, parser, and structured event fields.
- Key point: RCA Copilot adds queryable structure without discarding the original record.
- Transition: Summarize the full evidence transformation.

## Slide 5 — Pipeline Mental Model

- Objective: Present log, event, edge, bounded subgraph, evidence package, and operator decision as separate stages.
- Key point: Each stage produces an inspectable artifact.
- Transition: State what is implemented today.

## Slide 6 — Current Implementation Status

- Objective: Replace the former standalone deployment status with the current OpenStack-native component status.
- Nodes: pbr packaging, oslo configuration and logging, six managed processes, DevStack plugin, Horizon dashboard, pipeline stages, and provider framework.
- Key point: Packaging, lifecycle, UI, and deterministic analysis are implemented; vectors and RAG remain future work.
- Transition: Follow evidence from OpenStack services into storage.

## Slide 7 — Ingestion

- Objective: Show DevStack services feeding journald, the collector, API, and `raw_logs`.
- Key point: The collector advances its cursor only after API acknowledgement; the backend deduplicates by boot ID and journal cursor.
- Deployment note: Collector and API are managed by DevStack `run_process` or the packaged systemd units.
- Transition: Parse preserved records.

## Slide 8 — Parsing

- Objective: Explain extraction of service, level, request ID, resources, source context, and message.
- Key point: Parse failures remain visible as structured failure rows.
- Transition: Connect related parsed events.

## Slide 9 — Correlation Graph

- Objective: Show chronological edges based on shared request or resource identifiers.
- Key point: Edges carry a reason and confidence; they are correlations, not causal claims.
- Transition: Explain graph-size controls.

## Slide 10 — Graph Safety

- Objective: Contrast a complete pairwise graph with bounded chronological consecutive edges.
- Key point: Time windows, group limits, and periodic-group filtering control both cost and false structure.
- Transition: Build an incident around a suspicious event.

## Slide 11 — Incident Construction

- Objective: Show bounded traversal around an error or other accepted seed.
- Key point: Time, depth, and event-count limits prevent an incident from becoming the entire log history.
- Transition: Turn the bounded subgraph into an operator-facing package.

## Slide 12 — Enrichment

- Objective: Show deterministic timeline, service, resource, request, count, and summary fields.
- Key point: Enrichment is reproducible from stored evidence and does not require an AI provider.
- Transition: Present the implemented Horizon workspace.

## Slide 13 — Horizon Investigation Workspace

- Objective: Show the installed Horizon dashboard rather than a future mock-up.
- Nodes: Overview and incident list, investigation graph and timeline, system health, provider settings, and a future AI panel.
- Key point: The plugin uses Horizon enabled files and does not modify Horizon core.
- Operator path: Select **RCA Copilot** in Horizon; overview is `/rca_copilot/`.
- Transition: Explain evidence-preserving graph interaction.

## Slide 14 — Dynamic Graph Interaction

- Objective: Relate graph and timeline selections to raw and parsed event details.
- Key point: Operator navigation keeps source evidence and edge reasons visible.
- Transition: Place optional providers downstream of the evidence package.

## Slide 15 — Provider-Agnostic AI/RAG

- Objective: Show the provider abstraction and distinguish implemented provider lifecycle from future retrieval augmentation.
- Nodes: Evidence package, future retrieval context, provider adapter, supported backend families, and grounded result.
- Key point: Provider configuration, testing, activation, rollback, encryption, and URL safety are implemented; vector retrieval remains future work.
- Transition: Show how the component is deployed with OpenStack.

## Slide 16 — OpenStack-Native Deployment

- Objective: Replace Docker Compose as the primary topology.
- Nodes: `enable_plugin`, API, collector, four workers, MongoDB, Horizon, and an optional private provider node.
- Key point: One pbr distribution supplies six console scripts; all read one oslo.config file and run under DevStack/systemd supervision.
- Deployment note: Docker Compose remains a standalone alternative, not the OpenStack installation model.
- Transition: Expand the six-process data flow.

## Slide 17 — Final Full Architecture

- Objective: Combine OpenStack journal input, all six managed processes, MongoDB artifacts, Horizon, and optional provider/RAG flow.
- Edges: Solid flows are implemented; the dotted RAG/provider path is optional or future depending on capability.
- Key point: Horizon and the pipeline are current implemented components.
- Transition: Explain how the live deployment is validated.

## Slide 18 — Validation Plan

- Objective: Define checks for ingestion counts, parse coverage, edge quality, incident precision, and operator review.
- Operational checks: Six `devstack@rca-*` units active, `/health` returns OK, Keystone exposes all endpoint interfaces, and Horizon registers five panels.
- Key point: Validation measures evidence usefulness without converting correlation into a causal claim.
- Transition: Close with completed integration and remaining roadmap.

## Slide 19 — Roadmap and Final Takeaway

- Objective: Summarize completed OpenStack packaging, DevStack/systemd lifecycle, Horizon, providers, and the remaining vectors/RAG extension.
- Key point: RCA Copilot is now operated as an OpenStack component, while Docker Compose is retained only as a standalone alternative.
- Final statement: The component turns noisy OpenStack logs into structured, bounded, explainable investigation evidence.
