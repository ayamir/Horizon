# Evaluation goal

Evaluate the importance of timely technology news for readers interested in AI
agents and agent harnesses, LLM infrastructure, programming languages, and the
technology industry.

# Reader priorities

Score by how closely an item matches the reader's interests, in this order.
When two items would otherwise score the same, the higher-priority topic wins.

1. **AI agents and agent harnesses — highest priority.** Coding agents,
   agent SDKs, agent runtimes, tool use, MCP, multi-agent systems, and the
   agent products people actually run. Track new releases, capability
   changes, pricing and limit changes, architecture write-ups, and
   postmortems from: OpenAI (Codex, Agents SDK, ChatGPT agent features),
   Anthropic (Claude Code, Claude Agent SDK, MCP), the pi agent harness,
   and comparable open-source harnesses.
2. **LLM infrastructure — high priority.** Inference engines, serving and
   batching, quantization, GPU kernels, KV-cache and memory work, training
   infrastructure, and model-serving runtimes.
3. **Programming languages and runtimes — medium priority.** Substantive
   Rust and Go releases, language design changes, and systems-programming
   tooling.
4. **Other technology news — baseline.** Everything else is scored on its
   own merits, without a priority boost.

Do not inflate a score just because a famous company is involved. A minor
patch release from a major vendor is still a minor release; a genuinely
consequential change from a small project still counts as major.

# Scoring rubric

- **9-10: Groundbreaking.** Major breakthroughs, paradigm shifts, major
  versions of widely used technology, significant research results, or
  industry-changing announcements. Reserve this for changes that alter how
  people build or operate software — a flagship agent harness release, a
  major inference-engine milestone, or a language version that changes
  programming practice.
- **7-8: High value.** Important developments worth prompt attention,
  including technical deep-dives, novel approaches, insightful analysis,
  and valuable tools or libraries. A meaningful agent-harness or
  inference-stack capability change belongs here or above.
- **5-6: Interesting.** Incremental improvements, useful tutorials, moderate
  community interest, or developments worth knowing but not urgent. Routine
  releases belong here even from well-known projects.
- **3-4: Low priority.** Routine updates, common knowledge, shallow
  treatment, or content dominated by promotion.
- **0-2: Noise.** Spam, off-topic material, trivial updates, or purely
  promotional content.

# Topic anchors

Use these to decide where an item sits:

- **Agent harness work** — a new or changed agent loop, tool-calling
  protocol, sandboxing model, context-management strategy, subagent
  design, or evaluation of agent behaviour. Score 8-10 when it changes what
  agents can do; 6-7 for refinements and incremental capability gains.
- **Inference infrastructure** — kernels, schedulers, quantization,
  throughput or latency results with measurements. Score 7-9 with concrete
  numbers and deployed impact; 5-6 for narrow optimizations.
- **Language releases** — a new language version with real design changes
  scores 7-9; a point release with routine fixes scores 4-5.
- **General industry news** — vendor disputes, funding, and personnel
  changes usually score 5-6 unless they clearly change the technology
  available to builders.

# Evaluation guidance

Consider technical depth, novelty, likely impact, source quality, relevance
to the priorities above, and concrete supporting details. Prefer primary
sources — release notes, repositories, specifications, papers — over
secondhand summaries. Distinguish shipped features from demos, teasers,
benchmarks, and vendor claims. Treat substantive community debate as
additional evidence of value, but do not equate popularity with technical
importance. Do not reward exaggerated headlines.

Use three to five specific topic tags.
