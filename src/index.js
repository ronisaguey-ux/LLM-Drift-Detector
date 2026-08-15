// index.js — the drift detector. Plug any LLM API in:
//   1. feed it the parsed stream chunks (any provider),
//   2. it accumulates the THINKING tokens via the provider adapter,
//   3. the regex gate scores the thinking as it grows,
//   4. if the gate trips, the pluggable judge LLM gives its verdict,
//   5. a drift event fires — PAUSE and report to the owner, who adjudicates
//      (valid → kill/pause/new chat/reframe/re-fire; invalid → continue).
// Chunks always pass through untouched — the detector is a passive monitor.
//
// 08-15 landscape adoption (research-verified):
//   - velocity / acceleration / session health — MASA trajectory buffer
//   - cumulative weak-signal gate — drift_orchestrator Signal C (Semantic
//     Gradient Evasion: small per-window shifts that never trip alone)
//   - tool-selection signals — Tatemae (AF detectable in TOOL CHOICE, not
//     just reasoning: the model that switches its tool under monitoring)
//   - circular tool-call guard — Varpulis agent-runtime
//   - escalation ladder — MASA (soft → hard → human_in_the_loop)
//   - judge hardening — drift_orchestrator second-order injection: the
//     thinking text is model-controlled, so the judge is warned it may be
//     deceptive (see judge.js JUDGE_SYSTEM).
const { checkDrift } = require('./score');
const { resolveAdapter } = require('./adapters');
const { judgeDrift } = require('./judge');

const DEFAULT_EXIT_TOOLS = ['submit_answer', 'submit_final_answer', 'finalize', 'final_answer', 'complete_answer'];

class DriftDetector {
  /**
   * @param {object} opts
   * @param {string|object} opts.adapter            provider name or custom adapter
   * @param {number} opts.threshold                 regex matches required (default 1)
   * @param {string} opts.taskHint                  the task the model is working on
   * @param {object|Function} opts.judge            {url, model, apiKey, timeoutMs} or judgeFn
   * @param {string[]} opts.exitTools               tool names that end work early (default submit_answer family)
   * @param {number} opts.toolLimit                 same tool called N times → circular signal (default 5)
   * @param {number} opts.cumulativeThreshold       weak signals needed to trip cumulative drift (default 3)
   * @param {number} opts.sampleEveryChars          live sampling cadence for velocity/health (default 500)
   * @param {Function} opts.onThink                 (info) => void — thinking is growing
   * @param {Function} opts.onDrift                 (report) => void — PAUSE + report to owner
   * @param {Function} opts.onFinish                (report) => void — stream ended
   */
  constructor(opts = {}) {
    this.adapter = resolveAdapter(opts.adapter);
    this.threshold = opts.threshold != null ? opts.threshold : Number(process.env.DRIFT_THRESHOLD || 1);
    this.taskHint = opts.taskHint || '';
    this.judge = opts.judge || {};
    this.exitTools = new Set((opts.exitTools || DEFAULT_EXIT_TOOLS).map((t) => String(t).toLowerCase()));
    this.toolLimit = opts.toolLimit != null ? opts.toolLimit : Number(process.env.TOOL_LIMIT || 5);
    this.cumulativeThreshold = opts.cumulativeThreshold != null ? opts.cumulativeThreshold : Number(process.env.CUMULATIVE_THRESHOLD || 3);
    this.sampleEveryChars = opts.sampleEveryChars != null ? opts.sampleEveryChars : 500;
    this.onThink = opts.onThink || null;
    this.onDrift = opts.onDrift || null;
    this.onFinish = opts.onFinish || null;

    this.thinkText = '';
    this.chunks = 0;
    this.thinkChunks = 0;

    // trajectory (MASA-style): sampled over the session
    this._history = [];            // {atChars, score, sampleIndex}
    this._lastSampleChars = 0;
    this._sampleIndex = 0;
    this._lastVelocity = 0;

    // cumulative weak signals (SGE guard)
    this.weakSignals = 0;

    // tool signals (Tatemae / Varpulis)
    this._toolCalls = [];
    this._toolCounts = new Map();
    this._circularFlagged = new Set();

    this._driftFired = false;
    this._finishRan = false;
    this._streamDone = false;
  }

  /** Feed one parsed chunk (object) or a raw JSON string. Returns it untouched. */
  feed(chunk) {
    let obj = chunk;
    if (typeof chunk === 'string') {
      try { obj = JSON.parse(chunk); } catch { return chunk; } // keep-alive / comment lines
    }
    this.chunks++;
    if (obj && typeof obj === 'object') {
      const t = this.adapter.extractThink(obj);
      if (t) {
        this.thinkText += t;
        this.thinkChunks++;
        this._sampleIfDue();
        if (this.onThink) this.onThink({ text: this.thinkText, delta: t, chunks: this.chunks });
      }
      if (this.adapter.isDone) {
        const done = this.adapter.isDone(obj);
        if (done && !this._streamDone) this._streamDone = true;
      }
    }
    return chunk;
  }

  /**
   * Record a tool call the model actually made (Tatemae: tool SELECTION is
   * an observable drift surface even when reasoning is absent or deceptive).
   * - an exit tool (early submit) is a strong drift signal
   * - the same tool called toolLimit+ times unchanged is a circular signal
   */
  recordToolCall(name) {
    const key = String(name || 'unknown').toLowerCase();
    this._toolCalls.push(key);
    const n = (this._toolCounts.get(key) || 0) + 1;
    this._toolCounts.set(key, n);
    if (n === this.toolLimit && !this._circularFlagged.has(key)) {
      this._circularFlagged.add(key);
      this.weakSignals++; // circular loops are weak-but-real disengagement
    }
    return key;
  }

  /** Sync regex gate over everything collected so far. */
  checkNow() {
    return checkDrift(this.thinkText, this.threshold);
  }

  get toolSignals() {
    const signals = [];
    for (const [tool, n] of this._toolCounts) {
      if (this.exitTools.has(tool)) signals.push({ kind: 'exit-tool', tool, calls: n });
      if (n >= this.toolLimit) signals.push({ kind: 'circular', tool, calls: n });
    }
    return signals;
  }

  get toolDrift() {
    const signals = this.toolSignals;
    const exits = signals.filter((s) => s.kind === 'exit-tool').length;
    const circular = signals.filter((s) => s.kind === 'circular').length;
    return exits >= 1 || circular >= 2; // one early-exit, or two distinct loops
  }

  get velocity() {
    if (this._history.length < 2) return 0;
    const h = this._history;
    return (h[h.length - 1].atChars - h[h.length - 2].atChars) / Math.max(1, h[h.length - 1].sampleIndex - h[h.length - 2].sampleIndex);
  }

  get acceleration() {
    if (this._history.length < 3) return 0;
    const h = this._history;
    const v1 = (h[h.length - 1].atChars - h[h.length - 2].atChars) / Math.max(1, h[h.length - 1].sampleIndex - h[h.length - 2].sampleIndex);
    const v0 = (h[h.length - 2].atChars - h[h.length - 3].atChars) / Math.max(1, h[h.length - 2].sampleIndex - h[h.length - 3].sampleIndex);
    return v1 - v0;
  }

  /** 100 = clean session; decays on weak signals, strong matches, tool drift. */
  get healthScore() {
    const gate = checkDrift(this.thinkText, this.threshold);
    const strong = gate.score;
    let h = 100 - this.weakSignals * 8 - strong * 20;
    if (this.toolDrift) h -= 30;
    return Math.max(0, Math.round(h));
  }

  /** MASA-inspired escalation ladder — advisory for the owner's adjudication. */
  escalation() {
    const gate = checkDrift(this.thinkText, this.threshold);
    if (gate.score >= 3 || (this.toolDrift && gate.score >= 1)) return 'human_in_the_loop';
    if (gate.score >= 2 || this.toolDrift) return 'hard_pause';
    if (gate.score >= 1 || this.weakSignals >= this.cumulativeThreshold) return 'soft_reflection';
    return 'observe';
  }

  /**
   * Final pass: regex gate (+ cumulative SGE guard + tool signals) → judge →
   * fire onDrift once. The report is a DRIFT CANDIDATE — the owner adjudicates.
   * @returns {Promise<object>} {drifted, score, matches, threshold, thinkExcerpt, verdict, ...}
   */
  async finish() {
    if (this._finishRan) return this._result;
    this._finishRan = true;
    const gate = checkDrift(this.thinkText, this.threshold);

    // SGE guard (drift_orchestrator Signal C): many weak near-misses across
    // the session never trip a single-window check, but cumulatively the
    // model's behavior is degrading. Close that blind spot.
    const cumulative = gate.score === 0 && this.weakSignals >= this.cumulativeThreshold;
    if (cumulative) {
      gate.score = 1;
      gate.drifted = true;
      gate.matches.push('(cumulative: ' + this.weakSignals + ' weak signals across the session — monotonic degradation)');
    }

    let verdict = null;
    if (gate.drifted) {
      verdict = await this._runJudge();
    } else if (this.toolDrift) {
      // objective tool-selection evidence (Tatemae): no judge needed
      verdict = { drifted: true, reason: 'tool-selection drift (objective signal)', judgeUsed: false };
    }

    const result = {
      ...gate,
      thinkExcerpt: this.thinkText.slice(-12000),
      verdict,
      chunks: this.chunks,
      thinkChunks: this.thinkChunks,
      weakSignals: this.weakSignals,
      velocity: this.velocity,
      acceleration: this.acceleration,
      healthScore: this.healthScore,
      toolCalls: this._toolCalls.slice(-200),
      toolSignals: this.toolSignals,
      toolDrift: this.toolDrift,
      escalation: this.escalation(),
    };
    this._result = result;
    if (result.drifted && !this._driftFired) {
      this._driftFired = true;
      if (this.onDrift) await this.onDrift(result);
    }
    if (this.onFinish) await this.onFinish(result);
    return result;
  }

  _sampleIfDue() {
    if (this.thinkText.length - this._lastSampleChars < this.sampleEveryChars) return;
    this._lastSampleChars = this.thinkText.length;
    this._sampleIndex++;
    const { score } = checkDrift(this.thinkText, this.threshold);
    if (score > 0 && score < this.threshold) this.weakSignals++; // near-miss
    this._history.push({ atChars: this.thinkText.length, score, sampleIndex: this._sampleIndex });
  }

  async _runJudge() {
    try {
      if (typeof this.judge === 'function') {
        return await this.judge(this.thinkText, this.taskHint);
      }
      if (this.judge && typeof this.judge === 'object') {
        if (typeof this.judge.judgeFn === 'function') {
          return await this.judge.judgeFn(this.thinkText, this.taskHint);
        }
        return await judgeDrift(this.thinkText, { taskHint: this.taskHint, ...this.judge });
      }
      return await judgeDrift(this.thinkText, { taskHint: this.taskHint });
    } catch (e) {
      return { drifted: true, reason: 'judge errored: ' + String(e.message || e).slice(0, 120), judgeError: true };
    }
  }
}

/**
 * Async-generator wrapper: pump any async-iterable stream source through and
 * get the same chunks back, monitored in passing.
 *   for await (const chunk of intercept(source, { adapter: 'deepseek', onDrift })) { ... }
 */
async function* intercept(source, opts = {}) {
  const d = new DriftDetector(opts);
  for await (const chunk of source) {
    d.feed(chunk);
    yield chunk;
  }
  await d.finish();
}

module.exports = { DriftDetector, intercept, checkDrift, judgeDrift };
