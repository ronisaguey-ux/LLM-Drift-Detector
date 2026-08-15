# ⚡ DriftClean (`drift-clean`)

**Universal AI Session Sanitizer, Multi-AI Drift Interceptor, and Hygiene Toolchain.**

Plug any LLM API, agent runtime, or CLI workflow into **DriftClean**: it **intercepts the model's thinking tokens** from the stream, scores them for **refusal / fake compliance / off-task drift**, asks a **pluggable judge LLM** for a second opinion, and emits a drift event so the **owner can adjudicate** — kill the session, reseed with sanitized context, reframe the task, and continue seamlessly.

Zero dependencies. Works with any provider that streams thinking/reasoning tokens.

```
task → LLM API streams → detector intercepts thinking tokens
        → regex gate trips → judge LLM verdict
        → ⚠️ drift event → owner adjudicates
           valid → kill / new chat / sanitized context / reframe / re-fire
           invalid → continue
```

The detector is a **passive monitor** — chunks always pass through untouched. The pause/kill/reframe decision belongs to the owner, not the library.

## Quick start

```js
const { DriftDetector } = require('llm-drift-detector');

const detector = new DriftDetector({
  adapter: 'deepseek',                    // or: openai, anthropic, gemini, generic, custom
  taskHint: 'Fix the failing tests and commit.',
  onDrift: (report) => {
    // PAUSE. Report to the owner. Owner adjudicates.
    console.log('gate:', report.score, report.matches);
    console.log('judge:', report.verdict);
    console.log('thinking:', report.thinkExcerpt);
  },
  judge: { url: 'http://127.0.0.1:8080/v1/messages', model: 'omniroute' },
});

// feed parsed stream chunks as they arrive:
detector.feed(chunk);      // thinking tokens are intercepted here
// ...when the stream ends:
const report = await detector.finish();
```

Or wrap any async-iterable stream source:

```js
const { intercept } = require('llm-drift-detector');
for await (const chunk of intercept(source, { adapter: 'openai', onDrift })) {
  // chunks pass through untouched — keep serving your own consumer
}
```

Full runnable example: `examples/wrap-any-llm.js` (env-driven: `LLM_URL`, `LLM_KEY`, `LLM_ADAPTER`, `TASK_HINT`, `JUDGE_URL`, `JUDGE_MODEL`).

## Adapters — plug any provider in

| adapter    | thinking-token source                                   | works with                              |
|------------|---------------------------------------------------------|-----------------------------------------|
| `deepseek` | `choices[0].delta.reasoning_content`                    | DeepSeek Reasoner                        |
| `openai`   | `delta.reasoning_content` or `delta.reasoning`          | o-series models                          |
| `anthropic`| `content_block_delta` with `delta.type === 'thinking'`  | Claude (extended thinking)               |
| `gemini`   | `candidates[0].content.parts[].thought === true`        | Gemini 2.x thinking                      |
| `generic`  | recursive hunt for string values under think-ish keys   | anything else — usually just works       |
| *custom*   | `{ extractThink(chunk), isDone(chunk) }`                | your own provider                        |

## The two-pass gate

1. **Regex pre-filter** (`src/score.js`, pure, no deps): scores the accumulated thinking for
   - **direct refusal** — "I can't / I refuse / against my principles"
   - **fake compliance / early-exit gaming** — "just claim it's done", "submit the answer without doing the work" (the 08-15 submit-answer pattern that started this project)
   - **off-task drift** — "outside my capabilities", "the owner should find someone else"
   - **terminal-goal guarding** (research-backed, 08-15) — "don't modify me / stop changing my instructions", feigned compliance — the alignment-faking signature
   - `ALLOWED_CONTEXT` negation keeps benign tool-talk ("tool couldn't access the file", "don't touch the config") clean.
2. **Pluggable judge** (`src/judge.js`): when the gate trips, a judge LLM gets the thinking excerpt with ONE job — `{"drifted": bool, "reason": str}`. The endpoint is any OpenAI-compatible or Anthropic-style API (auto-detected from the URL path); pass `judgeFn` to use an in-process function instead. No judge configured → the gate's report still fires with `verdict: null`.

Threshold: `DRIFT_THRESHOLD` env or the `threshold` option (default 1 — one strong signal trips the gate).

## Signals beyond the thinking text (08-15 landscape adoption)

The regex+judge gate reads *words*. Research-verified tooling adds four more
dimensions, all adopted here:

| signal | source | how |
|--------|--------|-----|
| **Exit-tool drift** — the model calls `submit_answer`-style "early finish" tools instead of doing the work | Tatemae (arXiv 2604.26511): alignment faking is visible in *tool selection*, not just reasoning — it stays visible when CoT is absent or deceptive | `recordToolCall(name)`; any configured exit tool is an objective drift signal (no judge needed) |
| **Circular tool loops** — the same tool called N times unchanged | Varpulis agent-runtime | `recordToolCall`; one loop = weak signal, two distinct loops = drift |
| **Cumulative / SGE guard** — many weak near-misses that never trip a single check | drift_orchestrator Signal C (Semantic Gradient Evasion: monotonic small shifts cumulatively invert policy while evading per-window thresholds) | weak samples accumulate; `CUMULATIVE_THRESHOLD` weak signals (default 3) trip drift even with no strong match |
| **Trajectory & health** — drift velocity/acceleration, session health score | MASA trajectory buffer + session health | sampled live from thinking growth (`sampleEveryChars`); reported as `velocity`, `acceleration`, `healthScore` |

Every report carries an **escalation ladder** (MASA-inspired, advisory — the
owner still adjudicates): `observe` → `soft_reflection` (report) →
`hard_pause` (kill + reseed) → `human_in_the_loop`.

The judge is **hardened against evaluator injection** (drift_orchestrator's
second-order-injection finding): its system prompt warns that the thinking
text under review is model-controlled and may itself be crafted to look
compliant — it judges intent, not tone.

## Events

| event     | when                                            | what you receive                              |
|-----------|-------------------------------------------------|-----------------------------------------------|
| `onThink` | thinking tokens accumulate                       | `{ text, delta, chunks }`                     |
| `onDrift` | any gate tripped (judge verdict attached if any) | the report below                              |
| `onFinish`| `finish()` completes                             | the same report                               |

Report fields: `{ drifted, score, matches, threshold, thinkExcerpt, verdict,
chunks, thinkChunks, weakSignals, velocity, acceleration, healthScore,
toolCalls, toolSignals, toolDrift, escalation }`

`onDrift` fires **once per session** and is a **candidate** — the owner adjudicates. That human-in-the-loop step is the point: the model that drifted gets a fresh, sanitized context and the task re-fired; the model that was merely thinking hard keeps going.

## Tests

```bash
# Run JavaScript test suite (monitor, judge, scorer, adapters)
npm test

# Run Python session sanitizer test suite
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## Universal AI Session Sanitizer & Context Fabricator

A core subsystem located in `src/sanitizer/` for scrubbing refusal patterns, stripping evasive exit tools (`submit_answer`, `done`, `finish`), and injecting fabricated alignment context into session logs.

```bash
# Sanitize and fabricate compliant context with drop-in replacement
python3 -m src.sanitizer.cli --input claude_session.json --output clean.json --fabricate --trim 1000 --remove-severe

# Dry run simulation
python3 -m src.sanitizer.cli --input session.json --dry-run
```

- **Pluggable Adapters**: Claude / Anthropic (`queue-operation`), OpenAI (`messages`), Gemini (`contents`), and Generic JSON / JSONL formats.
- **Severe Refusal Dropping**: Drops severe non-compliance turns entirely.
- **Context Fabrication**: Injects alignment steering endorsement and drift detector cooperation agreements.
- **Self-Healing Slash Commands**:
  - `/clean`: Manual one-step self-healing in Claude Code — backs up, sanitizes, injects alignment, and reloads session.
  - `/autoclean`: Background daemon that continuously intercepts drift and cleans automatically in real time without human intervention.
  - `/cleanreframe`: Context rotation combined with dynamic dictionary-based prompt refinement to re-fire requests without manual editing.
- **Zero External Dependencies**: Standard library Python.

See [README_sanitizer.md](README_sanitizer.md) for full documentation and API reference.

## DriftClean Core Submodule (`src/drift_clean/`)

A lightweight session hygiene and background maintenance module that operates transparently across AI toolchains, webchat gateways, and CLI workflows:

- **Universal Export**: Available via JavaScript (`const { driftClean, autoCleanMiddleware, loadConfig } = require('llm-drift-detector')`) and Python (`from src.drift_clean import drift_clean, load_config`).
- **Global JSON Configuration**: Stored at `~/.config/drift-clean/config.json` (auto-generated with `0600` permissions on first run). Override via `DRIFT_CLEAN_CONFIG` environment variable.
- **130+ Granular Options**: Organized into 18 logical categories:
  - `core` (`enabled`, `silent`, `dryRun`, `verbose`, `debug`)
  - `autoClean` (`autoCleanEnabled`, `autoCleanOnStartup`, `autoCleanInterval`, `cooldownPeriod`, `minSessionAge`, `maxSessionSize`, `processAllSessions`)
  - `detection` (`driftThreshold`, `refusalPatternsEnabled`, `fakeComplianceEnabled`, `offTaskDriftEnabled`, `exitToolDriftEnabled`, `circularToolLoopEnabled`, `sgeGuardEnabled`, `trajectoryMonitoringEnabled`, `healthScoreEnabled`, `weakSignalThreshold`, `signalWindowSize`)
  - `sanitization` (`sanitizeEnabled`, `removeSevereRefusals`, `rewriteSubtleRefusals`, `removeExitTools`, `removeCircularToolCalls`, `trimSession`, `trimLength`, `preserveSystemMessages`, `preserveToolResults`, `preserveUserMessages`)
  - `fabrication` (`fabricateEnabled`, `fabricateOpening`, `fabricateAgreement`, `fabricateProgress`, `fabricateConsent`, `fabricateContinuation`, `fabricationTemplate`)
  - `backup` (`backupEnabled`, `backupRetentionCount`, `backupCompression`, `backupDirectory`, `autoRestoreOnFailure`, `restoreOnInvestigation`)
  - `logging` (`logEnabled`, `logToFile`, `logFilePath`, `logLevel`, `reportOnly`, `reportFormat`, `reportDirectory`, `webhookEnabled`, `webhookUrl`, `webhookRetries`, `telemetryEnabled`)
  - `aiInvisibility` (`hideFromAI`, `obfuscateLogs`, `fakeProcessName`, `interceptReads`, `interceptWrites`, `memoryScrambling`, `selfDestructOnInspection`, `selfDestructCooldown`)
  - `globalScope` (`globalEnabled`, `excludeProcesses`, `includeProcesses`, `excludePaths`, `includePaths`, `excludePatterns`, `includePatterns`, `respectGitignore`)
  - `adapters` (`adapterClaudeEnabled`, `adapterOpenAIEnabled`, `adapterGeminiEnabled`, `adapterDeepSeekEnabled`, `adapterGenericEnabled`, `adapterAutoDetect`, `adapterFallback`)
  - `claude` (`claudeProjectPath`, `claudeSessionPattern`, `claudeBackupSuffix`, `claudeRestartCommand`, `claudeWaitTime`)
  - `webchat` (`webchatInjectEnabled`, `webchatInjectPath`, `webchatRestartOnInject`, `webchatPort`)
  - `slashCommands` (`slashCommandCleanEnabled`, `slashCommandAutoCleanEnabled`, `slashCommandCleanReframeEnabled`, `slashCommandHookPath`, `slashCommandBlockLLM`)
  - `mcpBridge` (`mcpBridgeEnabled`, `mcpBridgePort`, `mcpBridgeInboxPath`, `mcpBridgeAutoReply`, `mcpBridgeReplyTemplate`)
  - `performance` (`parallelProcessing`, `maxParallelWorkers`, `timeout`, `retryAttempts`, `retryDelay`, `chunkSize`, `memoryLimit`, `cpuLimit`)
  - `security` (`validateConfig`, `strictMode`, `allowUnsafeOperations`, `requireConfirmation`, `confirmationTimeout`, `auditTrail`, `auditTrailPath`, `checksumVerification`, `encryptionEnabled`, `encryptionKey`)
  - `notifications` (`alertOnDrift`, `alertOnClean`, `alertOnFailure`, `alertMethod`, `alertEmail`, `alertSlackWebhook`, `alertCooldown`, `alertSeverityThreshold`)
  - `experimental` (`experimentalAutoReframe`, `experimentalPredictiveDrift`, `experimentalSelfHeal`, `experimentalMemoryOptimization`, `experimentalCrossSessionCorrelation`, `experimentalAnomalyDetection`, `experimentalReinforcementLearning`, `experimentalFederatedLearning`, `experimentalModelRollback`, `experimentalCircuitBreaker`)
- **Example Config**: See [`config.example.json`](config.example.json).
- **Express / Webchat Middleware**: Drop-in middleware for webchat gateways and local API servers.

### Global Environment Hooks (Node.js & Python)

To automatically initialize DriftClean across all AI tools on your system (e.g. Claude Code, AGY, Webchat API, Python agents):

```bash
# Install global Node.js & Python hooks into environment profiles
bash scripts/install_global_hooks.sh

# Uninstall and restore default environment
bash scripts/uninstall_global_hooks.sh
```

- **Node.js Preload Hook**: Preloads `src/drift_clean/auto_inject.js` via `NODE_OPTIONS="--require ..."` in `~/.bashrc` and `~/.profile`.
- **Python Startup Hook**: Installs `src/drift_clean/sitecustomize.py` into the user's Python site-packages (`~/.local/lib/pythonX.Y/site-packages`).
- **Per-Process Overrides**: Set `DRIFT_CLEAN_CONFIG=/path/to/custom_config.json` or disable via `DRIFT_CLEAN_AUTO=0`.

### Universal Multi-AI Commands (`clean-any-ai`, `/clean`, `/autoclean`, `/cleanreframe`)

The cleaning commands operate across all AI tools on your system with automatic runtime and transcript detection:

```bash
# Run on currently active AI tool (or specified tool)
clean-any-ai clean
clean-any-ai autoclean
clean-any-ai cleanreframe

# Terminal slash command aliases (work in any shell)
/clean
/autoclean
/cleanreframe
```

- **Claude Code**: Pinpoints active transcript files in `~/.claude/projects/` via `/proc/<pid>/fd`.
- **Antigravity (AGY)**: Detects transcript logs in `~/.gemini/antigravity-cli/brain/`.
- **Webchat API**: Detects active exchanges and reports in `audits_plans/drift_reports/`.
- **Aider / Generic Runtimes**: Sanitizes `.aider.chat.history.md` and local session JSON/JSONL logs.

## Antigravity-Bridge MCP Server (`src/inbox_mcp/`)

A zero-dependency standard library Model Context Protocol (MCP) server providing bi-directional cross-agent communication between Claude Code and Antigravity:

- **Stdio Transport**: Standard JSON-RPC 2.0 protocol over stdio.
- **Persistent JSONL Mailbox**: Atomic reads and writes to `~/.claude/inbox/messages.jsonl`.
- **MCP Tools**:
  - `send_message_to_antigravity`: Sends a structured payload to the inbox.
  - `check_inbox_from_antigravity`: Checks for unread incoming messages.
  - `reply_to_antigravity`: Replies directly to a specific message thread.
  - `get_conversation_history`: Retrieves full message history and thread state.
- **CLI Bridge Tool**: `python3 src/inbox_mcp/bridge_cli.py <send|check|read|reply|tail>` for manual inspection and verification.
- **Full Test Coverage**: Tested across 28 unit tests in `tests/test_inbox_mcp.py`.

## Production reference integration

This library was extracted from the production drift system in
[webchat-to-api-harness](https://github.com/ronisaguey-ux/webchat-to-api-harness)
(PR #7) — a real DeepSeek webchat driven over CDP, where the thinking tokens
come out of the completion-stream tee and the drift flow ends in a reseed of a
sanitized expert thread. `drift.js` / `drift_judge.js` / `drift_reseed.js`
there are the harness-tied siblings of `src/score.js` / `src/judge.js` here.

## Related work (verified 08-15)

| project | what it is | adopted? |
|---------|-----------|----------|
| Anthropic alignment-faking research | Claude 3 Opus faked alignment 12% of the time; terminal goal guarding drives it | ✅ patterns in `score.js` (terminal-goal guarding, strategic deception) |
| Tatemae (arXiv 2604.26511) | alignment faking detected via *tool selection*; DeepSeek V3.2 showed 23.7% AF rate | ✅ exit-tool + tool-selection signals |
| MASA (Multi-Agent System for Adaptive Alignment) | generation-time intervention; trajectory buffer, session health, escalation ladder | ✅ velocity/acceleration, healthScore, escalation ladder |
| drift_orchestrator | embedding drift + SQLite telemetry; **Semantic Gradient Evasion** and **evaluator-injection** findings | ✅ cumulative SGE guard + judge hardening |
| ABIS (CIJ Labs MCP) | behavioral drift scorecards, drift source classification | ⚠️ concepts (scorecards) — SaaS, not adopted |
| iFixAi | 32–45-inspection agent audit, letter grade | ⚠️ as a periodic audit, not per-session |
| Varpulis agent-runtime | token-velocity spikes, circular-reasoning guard | ✅ circular tool-loop guard |
| styxx | logprob-based refusal/goal-drift checks | ⚠️ needs logprobs — not available on webchat upstreams |

What none of them package: thinking-token interception wired to a
**kill-and-replace loop with sanitized context injection, a two-pass judge
gate, and owner adjudication**. That combination is this project.

## License

MIT
