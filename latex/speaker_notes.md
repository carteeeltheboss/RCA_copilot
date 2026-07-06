# Speaker Notes

Each slide note includes the objective, what the visual elements mean, the key point to emphasize, the transition, and claims to avoid.

## Slide 1 — Title
- Objective: Introduce RCA Copilot as an evidence-first, graph-first OpenStack RCA project.
- Nodes/edges: No diagram; the title frames the project scope.
- Key point: This is not a generic chatbot; it is an investigation architecture.
- Transition: Move from title to the semantic visual language used throughout.
- Do not claim: Do not say the current system already performs LLM root-cause generation.

## Slide 2 — Semantic Visual Language
- Objective: Teach the color and line semantics before diagrams become complex.
- Nodes: Blue means implemented services, slate cylinders mean MongoDB collections, purple means graph/inference logic, teal means enrichment, amber means decisions, red means errors, dotted gray means future.
- Edges: Solid blue is log flow, dashed slate is DB read, solid slate is DB write, amber dotted is control/checkpoint, dotted gray is future.
- Key point: Color carries architecture meaning, not decoration.
- Transition: Use the legend to interpret the OpenStack ecosystem.
- Do not claim: Do not treat dotted future components as implemented.

## Slide 3 — OpenStack Service Ecosystem
- Objective: Show that one OpenStack operation touches multiple services.
- Nodes: Horizon/API, Nova API, Scheduler, Compute, Keystone, Placement, Neutron, and Cinder represent the service ecosystem.
- Edges: Arrows show typical service dependencies and request propagation, not exact RPC traces.
- Key point: RCA is hard because failure evidence is distributed.
- Transition: Explain how those services produce many logs.
- Do not claim: Do not claim every edge is implemented by this project; it is domain context.

## Slide 4 — Distributed Log Volume
- Objective: Visualize log fan-in from many DevStack services into journald.
- Nodes: DevStack units feed journald; the operator grep storm shows manual investigation pressure.
- Edges: Blue arrows show independent log streams converging.
- Key point: The project starts by capturing this high-volume shared journal source.
- Transition: Move from volume to one request crossing the graph.
- Do not claim: Do not imply journald itself performs correlation.

## Slide 5 — One Request Crosses Many Services
- Objective: Explain request and resource propagation with a non-linear service graph.
- Nodes: Nova API, Keystone, Scheduler, Placement, Neutron, Compute, and an error node.
- Edges: Purple edges represent request flow; teal edges represent shared resource context.
- Key point: The visible error is often downstream of earlier relevant events.
- Transition: Show why inspecting one service alone fails.
- Do not claim: Do not infer root cause from the final red node.

## Slide 6 — Why Isolated Log Inspection Fails
- Objective: Contrast a single-file symptom view with a cross-service evidence graph.
- Nodes: Left cluster is isolated Nova-like evidence; right cluster joins related service events.
- Edges: Right-side edges reveal context that the single-file view misses.
- Key point: RCA needs relationships, not only log lines.
- Transition: Clarify that relationships still are not causality.
- Do not claim: Do not call the graph causal yet.

## Slide 7 — Chronology Is Not Causality
- Objective: Separate time order from causal proof.
- Nodes: Timeline events A through F include ordinary and error events.
- Edges: Purple and teal arcs show shared request/resource relationships over time.
- Key point: The system records correlation edges; it does not prove cause.
- Transition: Define the layers: monitoring, correlation, RCA workspace, AI explanation.
- Do not claim: Do not say earlier event automatically caused later event.

## Slide 8 — Monitoring vs Correlation vs RCA vs AI
- Objective: Position the project in the operational stack.
- Nodes: Monitoring detects signals; correlation connects evidence; RCA workspace supports investigation; AI explains later.
- Edges: Flow moves from signal to evidence to explanation.
- Key point: Current implementation is the correlation/evidence foundation.
- Transition: Present the vision architecture.
- Do not claim: Do not collapse correlation and AI into one feature.

## Slide 9 — Vision Architecture
- Objective: Show the intended local evidence plane plus future AI/UI.
- Nodes: OpenStack, collector, MongoDB, graph, evidence, future Chroma/RAG, local LLM, Horizon UI.
- Edges: Implemented solid lines feed evidence; dotted lines mark future AI/UI integration.
- Key point: MongoDB is the local source of truth, with AI downstream.
- Transition: Zoom into evidence-first design.
- Do not claim: Do not say Chroma or local LLM are implemented now.

## Slide 10 — Evidence-First Design
- Objective: Explain why artifacts are preserved before AI.
- Nodes: Raw logs, parsed events, correlation edges, seed events, and incident evidence packages.
- Edges: Raw evidence branches into structured parsing, graph edges, and incident seeds.
- Key point: AI should consume bounded evidence, not raw unstructured noise.
- Transition: Make current/future boundaries explicit.
- Do not claim: Do not imply summaries are generated by an LLM today.

## Slide 11 — Implemented vs Future System
- Objective: Separate real code from planned architecture.
- Nodes: Implemented collector/backend/workers/Mongo/enriched incidents; future ChromaDB/MSI API/Ollama/reranker/Horizon.
- Edges: No edges; this is a capability boundary view.
- Key point: The project already has a deterministic pipeline; AI is the next layer.
- Transition: Show how an operator will interact with it.
- Do not claim: Future dotted nodes are not deployed by this repo.

## Slide 12 — Operator Interaction Model
- Objective: Show the future user workflow.
- Nodes: Operator, Horizon tab, incident list, graph panel, timeline/evidence, AI answer.
- Edges: Operator selects incidents; evidence and graph feed future AI.
- Key point: UI exposes evidence first, explanation second.
- Transition: Move into physical topology.
- Do not claim: The Horizon plugin is not implemented yet.

## Slide 13 — Two-Machine Physical Topology
- Objective: Show MacBook evidence plane and future MSI inference plane.
- Nodes: MacBook hosts DevStack, journald, collector, Compose, Mongo; MSI hosts future embedding, reranking, Ollama.
- Edges: Dotted Tailscale connection is future private network communication.
- Key point: Data lives on the OpenStack host; GPU compute can be remote but private.
- Transition: Zoom into MacBook host/container boundaries.
- Do not claim: Do not say Mongo or Chroma run on MSI.

## Slide 14 — MacBook Host and Container Boundaries
- Objective: Show host systemd service and Docker Compose separation.
- Nodes: Host OS contains journald and collector; Compose contains backend, workers, Mongo, and persistent volume.
- Edges: Collector posts HTTP to backend; backend and workers read/write Mongo.
- Key point: The collector runs outside containers because it reads host journald.
- Transition: Show ports and trust.
- Do not claim: Do not say workers read journald directly.

## Slide 15 — Ports, Protocols, and Trust Boundaries
- Objective: Clarify local-only current communication.
- Nodes: Collector, FastAPI on 8000, MongoDB on 27017, workers, future MSI endpoints.
- Edges: HTTP log ingestion, Mongo reads/writes, future Tailscale inference calls.
- Key point: Current API and Mongo bind locally; future inference is private.
- Transition: Move from physical topology to runtime service dependencies.
- Do not claim: Do not imply public cloud APIs are used.

## Slide 16 — Runtime Dependency Graph
- Objective: Show the implemented worker graph and collection dependencies.
- Nodes: DevStack, journald, collector, backend, raw_logs, parser, parsed_logs, correlation, event_edges, incident, enrichment, incidents, worker_state.
- Edges: Blue log flow, slate DB reads/writes, amber checkpoint writes.
- Key point: Workers communicate through MongoDB collections, not direct worker-to-worker calls.
- Transition: Add future runtime extensions.
- Do not claim: Do not say correlation writes incidents directly.

## Slide 17 — Future Runtime Extensions
- Objective: Show planned AI/RAG integration without changing source of truth.
- Nodes: Enriched incidents, vector filter, ChromaDB, MSI embedding API, reranker, Ollama, Horizon plugin.
- Edges: Dotted future flows select evidence, embed it, retrieve it, rerank it, and explain it.
- Key point: Chroma stores vectors; Mongo remains authoritative evidence.
- Transition: Explain data lineage across artifacts.
- Do not claim: Do not say raw logs are all embedded.

## Slide 18 — Data Lineage Map
- Objective: Show transformation from journal entry to future answer.
- Nodes: Journal entry, raw log, parsed event, edge, candidate incident, enriched incident, vector doc, AI answer.
- Edges: Current solid transformations and future dotted RAG/explanation steps.
- Key point: Every later artifact points back to earlier evidence.
- Transition: Explain each artifact’s responsibility.
- Do not claim: Do not treat the future answer as current output.

## Slide 19 — Artifact Responsibilities
- Objective: Summarize persistence, idempotency, and failure handling by collection.
- Nodes: raw_logs, parsed_logs, event_edges, incidents, worker_state plus responsibility boxes.
- Edges: No data edges; this is a responsibility map.
- Key point: The architecture has deliberate artifact boundaries.
- Transition: Begin journald ingestion details.
- Do not claim: Do not call all collections immutable; incidents and worker_state are updated.

## Slide 20 — Monitored DevStack Units
- Objective: Show exactly which DevStack units the default collector follows.
- Nodes: Keystone, Nova API, scheduler, conductor cell, compute, Neutron API, Placement API, journald.
- Edges: Each unit emits logs into journald.
- Key point: This comes from `collector/config.py`.
- Transition: Show the sequence that moves journal lines into Mongo.
- Do not claim: Do not say all possible OpenStack services are collected by default.

## Slide 21 — Collector Sequence: Cursor Advances After ACK
- Objective: Explain the safe ingest sequence.
- Nodes: journalctl, collector, backend, MongoDB, cursor file lifelines.
- Edges: JSON line, POST batch, insert_many, insert counts, ACK, then cursor save.
- Key point: Cursor advancement happens only after successful acknowledgement.
- Transition: Convert this behavior into a state machine.
- Do not claim: Do not say cursor is saved before backend success.

## Slide 22 — Collector State Machine
- Objective: Show collector runtime loop.
- Nodes: Load cursor, follow journal, batch records, flush decision, send batch, ACK decision, save cursor, restore batch.
- Edges: Success loops back after cursor save; failure restores batch and retries later.
- Key point: The collector is designed to avoid losing unacknowledged records.
- Transition: Detail backend-unavailable failure branch.
- Do not claim: Do not say retry guarantees delivery if backend remains permanently down.

## Slide 23 — Backend Unavailable: Retry Branch
- Objective: Show retry and backoff behavior.
- Nodes: Pending batch, POST decision, ACK, HTTP error/timeout, exponential backoff, cursor advance.
- Edges: Success advances cursor; failure returns to pending batch after backoff.
- Key point: Failure does not advance cursor.
- Transition: Show restart and duplicate protection.
- Do not claim: Do not say the collector writes directly to Mongo.

## Slide 24 — Crash Recovery and Duplicate Prevention
- Objective: Explain recovery after collector crash.
- Nodes: Collector crash, load saved cursor, journalctl after-cursor, duplicate decision, raw_logs, unique index.
- Edges: Recovery may replay records; unique index prevents duplicate insertion.
- Key point: Cursor and unique index are complementary protections.
- Transition: Describe raw storage fields.
- Do not claim: Do not say replay never happens.

## Slide 25 — raw_logs Schema as Evidence Envelope
- Objective: Show raw log fields without source code.
- Nodes: raw_logs plus service, message, priority, timestamp, boot_id, journal_cursor, received_at.
- Edges: Schema callouts show fields inside the evidence envelope.
- Key point: Raw logs preserve source context before parsing.
- Transition: Explain why boot_id and cursor form identity.
- Do not claim: Do not say raw_logs has only these fields; model allows extra journald fields.

## Slide 26 — boot_id + journal_cursor Identity
- Objective: Explain deduplication identity.
- Nodes: Two boots with the same cursor value, unique pair decision, raw_logs.
- Edges: Pair flows into raw_logs as the unique key.
- Key point: Cursor identity must be scoped by boot ID.
- Transition: Move to parsing.
- Do not claim: Do not say journal_cursor alone is globally unique.

## Slide 27 — Parser Worker Lifecycle
- Objective: Explain parser polling and idempotent fetch.
- Nodes: raw_logs, already parsed decision, parser batch, parsed_logs, health file.
- Edges: Parser reads raw logs, skips already parsed records for parser-v1, writes parsed logs, updates health.
- Key point: Parser is version-aware and batch-oriented.
- Transition: Show one raw record becoming a structured event.
- Do not claim: Do not say parser deletes raw records.

## Slide 28 — Raw Text to Structured Event
- Objective: Show parsing as multiple extractions, not a black box.
- Nodes: Raw message envelope, ANSI cleanup, ID extraction, source location extraction, parsed event.
- Edges: Raw text feeds each extractor, all combine into parsed event.
- Key point: Parsing creates structured fields while preserving message.
- Transition: Zoom into extraction graph.
- Do not claim: Do not say every field is always present.

## Slide 29 — Extraction Graph
- Objective: Show how fields are extracted.
- Nodes: Message, level, module, request ID, resource IDs, file/line, host/PID, UUID exclusion decision, event.
- Edges: Message feeds each extractor; request UUID exclusion prevents request ID from becoming resource ID.
- Key point: Resource IDs are normalized and request UUID is excluded.
- Transition: Explain parse failures.
- Do not claim: Do not say extraction is semantic understanding; it is deterministic regex/field extraction.

## Slide 30 — Parse Failure Preservation
- Objective: Show that failures are retained.
- Nodes: Raw log, message-is-string decision, success parsed document, failure parsed document, parsed_logs.
- Edges: Both success and failure write to parsed_logs.
- Key point: Bad records remain visible and auditable.
- Transition: Explain parser versioning/idempotency.
- Do not claim: Do not say failures enter correlation; correlation reads successful parses only.

## Slide 31 — Parser Idempotency and Versioning
- Objective: Explain unique parsed key.
- Nodes: raw_logs, source_log_id + parser_version decision, parsed_logs.
- Edges: Upsert by source and parser version.
- Key point: A future parser version can re-parse the same raw log without overwriting old parsed artifacts.
- Transition: Move to correlation graph.
- Do not claim: Do not say current parser has multiple versions active by default.

## Slide 32 — Event Nodes and Correlation Edges
- Objective: Introduce event graph semantics.
- Nodes: Event nodes E1-E5.
- Edges: Purple same request ID edges, teal shared resource ID edges, chronological direction.
- Key point: Edge reason and confidence are stored with the edge.
- Transition: Show a realistic multi-service graph.
- Do not claim: Do not call edges root-cause edges.

## Slide 33 — Realistic Multi-Service Correlation Graph
- Objective: Show request/resource relationships across Nova, Scheduler, Placement, Neutron, and Compute.
- Nodes: Events N1, S1, P1, C1 seed, Q1, R1, N2, and a periodic excluded H node.
- Edges: Purple request edges, teal resource edges, dotted unrelated periodic edge.
- Key point: The graph can include multiple IDs and exclude noise.
- Transition: Explain time windows.
- Do not claim: Do not say the exact labels are live data.

## Slide 34 — Correlation Rule Windows
- Objective: Show configured time windows and confidence.
- Nodes: Same_request_id rule and shared_resource_id rule.
- Edges: Braces show 300 seconds and 600 seconds.
- Key point: Request edges are stricter than resource edges.
- Transition: Explain transactional versus periodic groups.
- Do not claim: Do not say time windows prove causality.

## Slide 35 — Transactional vs Periodic Groups
- Objective: Distinguish useful transaction groups from heartbeat-like noise.
- Nodes: Transactional events A-B-C and periodic gray heartbeat nodes.
- Edges: Transactional edges are kept; periodic groups can be skipped.
- Key point: Periodic skip is a noise-control mechanism.
- Transition: Show graph explosion before the fix.
- Do not claim: Do not say every periodic group is always skipped if config disables it.

## Slide 36 — Before: Complete Pairwise Graph
- Objective: Make graph explosion visually obvious.
- Nodes: Six events in a complete graph.
- Edges: Many faint purple edges show all-pairs linking.
- Key point: Complete pairwise correlation grows as n(n-1)/2 and becomes unreadable.
- Transition: Show the consecutive-edge fix.
- Do not claim: Do not say this is current behavior; it is the avoided defect.

## Slide 37 — After: Consecutive-Only Chain
- Objective: Show current compact edge strategy.
- Nodes: Six ordered events.
- Edges: Only adjacent chronological edges are emitted.
- Key point: Edge count is at most n-1 per group.
- Transition: Explain the decision flow that enforces this.
- Do not claim: Do not say non-adjacent events are unrelated; they are just not directly linked.

## Slide 38 — Explosion Fix Decision Flow
- Objective: Show correlation safeguards.
- Nodes: Group events, size decision, periodic decision, sort by time, emit consecutive edges, skip oversized, skip periodic.
- Edges: Decision branches show controls before edge creation.
- Key point: The worker controls edge growth before writing to Mongo.
- Transition: Summarize practical impact.
- Do not claim: Do not say skipped groups are deleted; they simply do not emit edges.

## Slide 39 — Observed Impact
- Objective: Communicate why the fix matters.
- Nodes: Before thousands of edges, after tens of edges, consecutive-only plus periodic skip.
- Edges: Arrow from before to after.
- Key point: This improves both performance and evidence quality.
- Transition: Move from correlation to incident detection.
- Do not claim: Do not cite exact measured numbers unless you have run-specific evidence.

## Slide 40 — Incident Seed Rule Engine
- Objective: Show deterministic incident detection flow.
- Nodes: Parsed event, parse success decision, suppression decision, seed rule decision, candidate seed, drop.
- Edges: Only successful, unsuppressed, rule-matching events become seeds.
- Key point: This is deterministic and auditable.
- Transition: Show accepted rule branches.
- Do not claim: Do not say every error becomes a root cause.

## Slide 41 — Accepted Seed Decision Tree
- Objective: Show accepted seed categories.
- Nodes: Event signal root branches to ERROR/CRITICAL, Traceback/Exception, failed/timeout, resource ERROR state, then seed.
- Edges: Any matching branch can create a seed.
- Key point: The seed stores reason and severity.
- Transition: Show rejected false positives.
- Do not claim: Do not say all “failed” text is accepted; suppression happens first.

## Slide 42 — Rejected False Positives
- Objective: Show suppression rules.
- Nodes: Message, active text, suppression patterns, not-a-seed output, examples.
- Edges: Message is cleaned of quoted/historical text before suppression checks.
- Key point: Suppression prevents metrics like error_count=0 from becoming incidents.
- Transition: Show subgraph construction after seed creation.
- Do not claim: Do not say suppression catches every possible false positive.

## Slide 43 — Bounded Traversal Around Seed
- Objective: Explain incident subgraph traversal.
- Nodes: Seed S, depth 1/2/3 neighbors, out-of-window excluded node.
- Edges: Existing correlation edges are traversed in both directions.
- Key point: Traversal is bounded by depth and event count.
- Transition: Explain time window bounds.
- Do not claim: Do not say traversal creates causal edges.

## Slide 44 — Incident Window
- Objective: Show incident time window.
- Nodes: Timeline, seed, 10-minute-before and 2-minute-after bounds.
- Edges: Braces define accepted window.
- Key point: Time bounds prevent subgraphs from growing indefinitely.
- Transition: Clarify correlation is not causality.
- Do not claim: Do not say events outside the window are impossible causes.

## Slide 45 — Correlation Is Not Causality
- Objective: State a core technical limitation.
- Nodes: Correlation edge, does-not-prove decision, root cause, current output evidence package.
- Edges: The slide blocks the leap from correlation to root cause.
- Key point: Current system packages evidence; root cause explanation is future grounded analysis.
- Transition: Explain worker checkpoint reliability.
- Do not claim: Do not call current incidents definitive RCA.

## Slide 46 — Before: Repeated First-Page Scanning
- Objective: Explain the checkpoint defect class.
- Nodes: Parsed logs, first page again, injected ERROR not reached, progress lost on restart, stalled detection.
- Edges: Repeated scanning can prevent later events from being processed.
- Key point: Long streams need durable scan progress.
- Transition: Show the persistent worker_state fix.
- Do not claim: Do not say this still applies to incident worker after the fix.

## Slide 47 — After: Persistent worker_state
- Objective: Show the implemented durable checkpoint.
- Nodes: parsed_logs, incident worker, sort by parsed_at + _id, save after batch, worker_state, resume after checkpoint.
- Edges: Worker reads sorted batches and stores last parsed_at and _id.
- Key point: Restart resumes from persisted state.
- Transition: Move to enrichment.
- Do not claim: Do not say correlation worker uses this same persistent checkpoint; it currently has an in-memory last_seen_id.

## Slide 48 — Enrichment Worker Architecture
- Objective: Show candidate-to-enriched incident processing.
- Nodes: Candidate incidents, enrichment worker, parsed events, event edges, derive timeline/counts/summaries, enriched incidents.
- Edges: Enrichment loads referenced event_ids and edge_ids and writes updates to incidents.
- Key point: Enrichment is deterministic and versioned.
- Transition: Show the timeline artifact.
- Do not claim: Do not say an LLM writes these summaries.

## Slide 49 — Enriched Incident Timeline
- Objective: Show timeline as an investigation view.
- Nodes: Event nodes with service names and levels; seed is red.
- Edges: Request and resource arcs link related timeline events.
- Key point: Timeline is ordered by event timestamp.
- Transition: Show enriched document fields.
- Do not claim: Do not say the seed is root cause.

## Slide 50 — Enriched Incident Document
- Objective: Show fields added by enrichment.
- Nodes: Incident plus timeline, services, request IDs, resource IDs, error/warning counts, summaries, status enriched.
- Edges: No arrows; this is a document shape view.
- Key point: Enrichment changes status from candidate to enriched.
- Transition: Show collection architecture.
- Do not claim: Do not imply fields are manually entered.

## Slide 51 — Collection Relationship Map
- Objective: Show MongoDB references and relationships.
- Nodes: raw_logs, parsed_logs, event_edges, incidents, worker_state.
- Edges: source_log_id, source/target event IDs, event_ids/edge_ids, checkpoint loops.
- Key point: Collections form an evidence graph plus operational state.
- Transition: Explain indexes and version fields.
- Do not claim: Do not say MongoDB enforces foreign keys; references are stored IDs.

## Slide 52 — Indexes and Version Fields
- Objective: Summarize idempotency indexes and version tags.
- Nodes: Index boxes for raw, parsed, edges, incidents, and version tags.
- Edges: None.
- Key point: Version fields allow safe reprocessing strategies.
- Transition: Explain mutability boundaries.
- Do not claim: Do not say all version migrations are implemented.

## Slide 53 — Immutable vs Mutable Collections
- Objective: Separate set-on-insert evidence collections from workflow-updated collections.
- Nodes: Append/set-on-insert group for raw/parsed/edges; updated-by-workflow group for incidents/state.
- Edges: None.
- Key point: Raw evidence is preserved while incident state matures.
- Transition: Move into reliability model.
- Do not claim: Do not say incidents are immutable.

## Slide 54 — Reliability Shield
- Objective: Show reliability controls around the evidence pipeline.
- Nodes: Dedupe, healthchecks, restart policy, versions, checkpoints, persistent volume around the pipeline.
- Edges: Controls point into the evidence pipeline.
- Key point: Reliability comes from multiple small safeguards.
- Transition: Show containment behavior.
- Do not claim: Do not say this is high availability; it is restart/idempotency resilience.

## Slide 55 — Failure Containment
- Objective: Map failures to containment mechanisms.
- Nodes: Backend down, parse error, worker restart, duplicate record, contained output.
- Edges: Retry/no cursor advance, failure preservation, checkpoint/version, unique indexes.
- Key point: Each failure mode has a bounded response.
- Transition: Compare current and future capabilities.
- Do not claim: Do not say every failure is automatically resolved.

## Slide 56 — Current and Future Capability Boundary
- Objective: Show implemented versus planned capability set.
- Nodes: Current ingestion/parsing/correlation/seeds/enrichment; future Chroma/embeddings/reranker/Ollama/Horizon.
- Edges: None.
- Key point: Current system is a complete evidence foundation.
- Transition: Explain selective vectorization.
- Do not claim: Do not say future pieces are available in Compose now.

## Slide 57 — Selective Vectorization Funnel
- Objective: Explain why not every log is embedded.
- Nodes: Mongo, all raw logs, high-signal filter, embedding request, Chroma vectors, selected artifact examples.
- Edges: Raw evidence is filtered before future embedding.
- Key point: Embeddings should focus on high-signal evidence and summaries.
- Transition: Show retrieval architecture.
- Do not claim: Do not say Chroma replaces Mongo.

## Slide 58 — Retrieval Architecture
- Objective: Show future retrieval with Mongo and Chroma.
- Nodes: Selected incident, Mongo truth, Chroma similarity, reranker, grounded context.
- Edges: Incident queries both structured truth and semantic search; reranker composes context.
- Key point: Vector hits point back to Mongo evidence IDs.
- Transition: Show MSI GPU node.
- Do not claim: Do not say Chroma stores authoritative incidents.

## Slide 59 — Future MSI GPU Node
- Objective: Show future GPU inference services.
- Nodes: Auth API, sentence-transformer, CUDA/RTX 4070, reranker, Ollama/local LLM, health checks.
- Edges: API routes embedding and reranking/generation requests.
- Key point: MSI computes; MacBook stores.
- Transition: Show RAG investigation flow.
- Do not claim: Do not say this service exists in the repo.

## Slide 60 — Grounded RCA Generation Flow
- Objective: Explain future user-triggered RAG.
- Nodes: User selects incident, graph load, vector query, similar evidence, reranker, LLM evidence package, answer with event refs.
- Edges: Current graph and future vector retrieval feed LLM context.
- Key point: Answer should reference event nodes.
- Transition: Show unsupported-claim gate.
- Do not claim: Do not say the LLM can answer without evidence.

## Slide 61 — Unsupported Claim Gate
- Objective: Show anti-hallucination control.
- Nodes: LLM claim, linked-to-evidence decision, allow with reference, reject/ask for evidence.
- Edges: Claim is checked against evidence reference.
- Key point: AI explains; it does not invent unsupported facts.
- Transition: Move to Horizon UI.
- Do not claim: Do not say this validation is implemented now.

## Slide 62 — Future Horizon RCA Copilot Tab
- Objective: Show planned UI panels.
- Nodes: Incident list, interactive graph, timeline, settings, evidence panel, AI explanation, endpoint test.
- Edges: None; this is UI layout architecture.
- Key point: The UI is an investigation workspace, not a landing page.
- Transition: Show browser-to-backend flow.
- Do not claim: Do not say the plugin exists today.

## Slide 63 — Browser-to-Backend Flow
- Objective: Clarify future API trust boundary.
- Nodes: Horizon browser, RCA backend, Mongo, MSI inference API, Ollama.
- Edges: Browser calls RCA backend; backend reads Mongo and calls MSI over Tailscale; browser does not call Ollama directly.
- Key point: Backend mediates all sensitive data and inference calls.
- Transition: Show operator journey.
- Do not claim: Do not expose Ollama directly to browser.

## Slide 64 — Operator Storyboard
- Objective: Tell the end-user investigation journey.
- Nodes: Detected incident, open tab, graph, select node, details, ask AI, retrieved context, validated conclusion.
- Edges: Process arrows show workflow sequence.
- Key point: Operator validates AI output against visible evidence.
- Transition: Present the full final architecture.
- Do not claim: Do not say AI conclusion is automatically accepted.

## Slide 65 — Full Final Architecture
- Objective: Provide the poster-quality architecture overview.
- Nodes: OpenStack services, journald, collector, backend, Mongo collections, workers, Chroma, future MSI services, Horizon, operator.
- Edges: Implemented solid flows inside MacBook; future dotted flows to Chroma/MSI/Horizon.
- Key point: This slide combines physical topology, data flow, and current/future boundaries.
- Transition: Summarize roadmap.
- Do not claim: Do not blur implemented and future boundaries.

## Slide 66 — Roadmap
- Objective: Show completed milestones and future milestones.
- Nodes: Completed ingestion, parser, correlation, incident, enrichment, monorepo; future MSI embeddings, Chroma, RAG, Ollama, Horizon, demo.
- Edges: Top solid lane is complete; bottom dotted lane is future.
- Key point: The evidence foundation is complete before AI integration.
- Transition: Close with final takeaway.
- Do not claim: Do not mark future items as complete.

## Slide 67 — Final Takeaway
- Objective: Leave the audience with the core architecture message.
- Nodes: Main statement, graph first, evidence first, AI explains.
- Edges: None; the final slide is conceptual.
- Key point: The project turns scattered logs into a traceable incident evidence graph.
- Transition: End or open for questions.
- Do not claim: Do not oversell AI beyond the planned evidence-grounded role.
