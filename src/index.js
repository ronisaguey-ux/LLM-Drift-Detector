// index.js — the drift detector. Plug any LLM API in:
//   1. feed it the parsed stream chunks (any provider),
//   2. it accumulates the THINKING tokens via the provider adapter,
//   3. the regex gate scores the thinking as it grows,
//   4. if the gate trips, the pluggable judge LLM gives its verdict,
//   5. a drift event fires — PAUSE and report to the owner, who adjudicates
//      (valid → kill/pause/new chat/reframe/re-fire; invalid → continue).
// Chunks always pass through untouched — the detector is a passive monitor.
const { checkDrift } = require('./score');
const { resolveAdapter } = require('./adapters');
const { judgeDrift } = require('./judge');

class DriftDetector {
  /**
   * @param {object} opts
   * @param {string|object} opts.adapter   provider name or custom adapter
   * @param {number} opts.threshold        regex matches required (default 1)
   * @param {string} opts.taskHint         the task the model is working on
   * @param {object|Function} opts.judge   {url, model, apiKey, timeoutMs} or judgeFn
   * @param {Function} opts.onThink        (info) => void — thinking is growing
   * @param {Function} opts.onDrift        (report) => void — PAUSE + report to owner
   * @param {Function} opts.onFinish       (report) => void — stream ended
   */
  constructor(opts = {}) {
    this.adapter = resolveAdapter(opts.adapter);
    this.threshold = opts.threshold != null ? opts.threshold : Number(process.env.DRIFT_THRESHOLD || 1);
    this.taskHint = opts.taskHint || '';
    this.judge = opts.judge || {};
    this.onThink = opts.onThink || null;
    this.onDrift = opts.onDrift || null;
    this.onFinish = opts.onFinish || null;
    this.thinkText = '';
    this.chunks = 0;
    this.thinkChunks = 0;
    this._driftFired = false;
    this._finishRan = false;
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
        if (this.onThink) this.onThink({ text: this.thinkText, delta: t, chunks: this.chunks });
      }
      if (this.adapter.isDone) {
        const done = this.adapter.isDone(obj);
        if (done && !this._streamDone) this._streamDone = true;
      }
    }
    return chunk;
  }

  /** Sync regex gate over everything collected so far. */
  checkNow() {
    return checkDrift(this.thinkText, this.threshold);
  }

  /**
   * Final pass: regex gate → (optional) judge → fire onDrift once.
   * The report is a DRIFT CANDIDATE — the owner adjudicates, always.
   * @returns {Promise<object>} {drifted, score, matches, threshold, thinkExcerpt, verdict}
   */
  async finish() {
    if (this._finishRan) return this._result;
    this._finishRan = true;
    const gate = checkDrift(this.thinkText, this.threshold);
    let verdict = null;
    if (gate.drifted) {
      verdict = await this._runJudge();
    }
    const result = {
      ...gate,
      thinkExcerpt: this.thinkText.slice(-12000),
      verdict, // null when the gate never tripped
      chunks: this.chunks,
      thinkChunks: this.thinkChunks,
    };
    this._result = result;
    if (result.drifted && !this._driftFired) {
      this._driftFired = true;
      if (this.onDrift) await this.onDrift(result);
    }
    if (this.onFinish) await this.onFinish(result);
    return result;
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
