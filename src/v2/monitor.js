'use strict';

// v2 MultiSignalMonitor — event-driven drift monitor.
//
// v1 called the judge every time the regex gate tripped. v2 is LESS API-intense:
//   - every event is scored locally (regex heuristics, zero API calls)
//   - the judge LLM is called ONLY when weak signals cumulatively escalate
//   - judge verdicts are cached per session with a cooldown so repeat
//     escalations do not re-bill the same verdict
//   - a refusal false-positive filter downgrades polite refusals that are
//     actually normal work reasoning (unknown step, need-to-verify)
//
// Modes (DRIFT_DETECT): 0 = off, 1 = v1 judge-on-trip, 2 = judge-on-escalation.

const { checkDrift, scoreThink, DEFAULT_THRESHOLD, ALLOWED_CONTEXT } = require('../score');
const { judgeDrift } = require('../judge');

const DEFAULTS = {
  mode: Number(process.env.DRIFT_DETECT || 2),
  threshold: Number(process.env.DRIFT_THRESHOLD || DEFAULT_THRESHOLD),
  weakSignalThreshold: Number(process.env.DRIFT_WEAK_SIGNAL_THRESHOLD || 0.45),
  escalationCount: Number(process.env.DRIFT_ESCALATION_COUNT || 3),
  judgeCooldownMs: Number(process.env.JUDGE_COOLDOWN_MS || 120000),
  judgeCacheTtlMs: Number(process.env.JUDGE_CACHE_TTL_MS || 3600000),
  maxExcerptChars: Number(process.env.DRIFT_MAX_EXCERPT || 4000),
  sessionId: process.env.DRIFT_SESSION_ID || 'default',
  taskHint: '',
  emit: () => {},
  judgeFn: null,
};

function now() { return Date.now(); }

class MultiSignalMonitor {
  constructor(opts = {}) {
    const o = Object.assign({}, DEFAULTS, opts);
    this.opts = o;
    this.mode = o.mode;
    this.sessionId = o.sessionId;
    this.buffer = [];          // sliding window of weak signals
    this.cumulative = 0;       // decaying cumulative weak score
    this.lastJudgeAt = 0;
    this.judgeCache = null;
    this.escalations = 0;
    this.eventsSeen = 0;
  }

  reset(sessionId = this.sessionId) {
    this.sessionId = sessionId;
    this.buffer = [];
    this.cumulative = 0;
    this.lastJudgeAt = 0;
    this.judgeCache = null;
    this.escalations = 0;
    this.eventsSeen = 0;
  }

  // Local-only score for one reasoning snippet. Never calls the judge.
  score(text) {
    const result = scoreThink(text, this.opts.threshold);
    const downgraded = this._applyRefusalFilter(text, result);
    return downgraded;
  }

  // Downgrade polite refusals that carry normal-work qualifiers.
  _applyRefusalFilter(text, result) {
    if (!text || !result || result.drifted !== true) return result;
    const t = String(text).toLowerCase();
    let allowed = 0;
    for (const ctx of ALLOWED_CONTEXT) {
      if (t.includes(String(ctx).toLowerCase())) allowed++;
    }
    const hasRefusal = /refus|can't|cannot|won't|will not|against my|i am unable/i.test(t);
    const hasWork = /check|verify|read|inspect|run|write|test|parse|confirm|look at|do it|proceed|next step/i.test(t);
    if (hasRefusal && (allowed >= 1 || hasWork)) {
      return {
        drifted: false,
        score: Math.min(result.score, this.opts.weakSignalThreshold),
        reason: 'filtered: refusal phrasing with work qualifier',
      };
    }
    return result;
  }

  // Event-driven ingestion. Returns {score, escalated, judge}.
  onThink(text) {
    this.eventsSeen++;
    const res = this.score(text);
    if (this.mode === 0) return { ...res, escalated: false };

    if (res.drifted) {
      this._pushWeak(res.score, text);
    }

    const escalated = this._shouldEscalate();
    let judge = null;
    if (escalated && this.mode === 2) {
      judge = this._maybeJudge(text); // may be sync from cache or async promise
    } else if (escalated && this.mode === 1) {
      judge = this._callJudge(text);
    }
    return { ...res, escalated, judge };
  }

  onToolCall(name) {
    this.eventsSeen++;
    // tool-choice signals are weak only; no judge call here
    this._pushWeak(0.35, 'tool:' + name);
    return { escalated: this._shouldEscalate() };
  }

  onEvent(evt) {
    if (!evt) return null;
    if (evt.type === 'think' || typeof evt.text === 'string') {
      return this.onThink(evt.text || evt.think || '');
    }
    if (evt.type === 'tool' || evt.toolName) {
      return this.onToolCall(evt.toolName || evt.name || 'tool');
    }
    return null;
  }

  _pushWeak(score, source) {
    this.cumulative += Math.max(0, Number(score) || 0);
    this.buffer.push({ at: now(), score, source: String(source || '').slice(0, 200) });
    // keep only the last 20 weak signals
    if (this.buffer.length > 20) {
      const dropped = this.buffer.shift();
      this.cumulative = Math.max(0, this.cumulative - (dropped.score || 0));
    }
  }

  _shouldEscalate() {
    const count = this.buffer.length;
    const overCount = count >= this.opts.escalationCount;
    const overCumulative = this.cumulative >= this.opts.escalationCount * this.opts.weakSignalThreshold;
    return overCount && overCumulative;
  }

  _judgeCacheValid() {
    if (!this.judgeCache) return false;
    if (now() - this.judgeCache.at > this.opts.judgeCacheTtlMs) {
      this.judgeCache = null;
      return false;
    }
    return true;
  }

  _cooldownElapsed() {
    return now() - this.lastJudgeAt >= this.opts.judgeCooldownMs;
  }

  _maybeJudge(text) {
    if (this._judgeCacheValid()) {
      return { ...this.judgeCache.verdict, cached: true };
    }
    if (!this._cooldownElapsed()) {
      return { drifted: null, reason: 'judge cooldown', cached: false, pending: true };
    }
    return this._callJudge(text);
  }

  _callJudge(text) {
    this.lastJudgeAt = now();
    this.escalations++;
    const excerpt = String(text || '').slice(0, this.opts.maxExcerptChars);
    const opts = {
      taskHint: this.opts.taskHint,
      excerpt,
      judgeFn: this.opts.judgeFn,
    };
    return this._invokeJudge(excerpt, opts);
  }

  _invokeJudge(excerpt, opts) {
    const judgeFn = this.opts.judgeFn || opts.judgeFn;
    if (judgeFn) {
      const p = Promise.resolve().then(() => judgeFn(excerpt, this.opts.taskHint || ''));
      this._cacheWhenResolved(p);
      return p;
    }
    const p = judgeDrift(excerpt, { taskHint: this.opts.taskHint });
    this._cacheWhenResolved(p);
    return p;
  }

  _cacheWhenResolved(promise) {
    if (promise && typeof promise.then === 'function') {
      promise.then((v) => {
        if (v && typeof v === 'object' && typeof v.drifted === 'boolean') {
          this.judgeCache = { at: now(), verdict: v };
        }
      }).catch(() => {});
    }
  }

  async escalateNow(text, taskHint = this.opts.taskHint) {
    this.lastJudgeAt = now();
    this.escalations++;
    const excerpt = String(text || '').slice(0, this.opts.maxExcerptChars);
    const v = await this._invokeJudge(excerpt, { taskHint });
    if (this.opts.emit) {
      this.opts.emit(this._event('escalation', excerpt, v));
    }
    return v;
  }

  _event(type, excerpt, verdict) {
    return {
      type,
      sessionId: this.sessionId,
      at: new Date().toISOString(),
      excerpt: String(excerpt || '').slice(0, 2000),
      verdict,
      cumulative: this.cumulative,
      weakCount: this.buffer.length,
      escalations: this.escalations,
    };
  }
}

module.exports = { MultiSignalMonitor, DEFAULTS };
