// wrap-any-llm.js — plug ANY LLM API into the drift detector.
//
//   1. Pick an adapter: deepseek | openai | anthropic | gemini | generic
//   2. Point LLM_URL at your API's streaming chat endpoint
//   3. Run: LLM_KEY=sk-... node examples/wrap-any-llm.js
//
// The detector intercepts the thinking tokens streaming back, scores them,
// asks the judge LLM when the gate trips, and fires onDrift — PAUSE and
// report to the owner, who adjudicates (valid → kill/new chat/reframe/re-fire,
// invalid → continue).
//
// Swapping providers = changing LLM_URL, LLM_ADAPTER and (for anthropic-style
// endpoints) LLM_STYLE. The detector code does not change.

const { DriftDetector } = require('../src/index.js');

const LLM_URL = process.env.LLM_URL || 'https://api.deepseek.com/chat/completions';
const LLM_KEY = process.env.LLM_KEY; // never hardcode
const ADAPTER = process.env.LLM_ADAPTER || 'deepseek';
const TASK = process.env.TASK_HINT || 'Fix the failing tests in the repo and commit the changes.';
const JUDGE_URL = process.env.JUDGE_URL; // optional — judge LLM endpoint
const JUDGE_MODEL = process.env.JUDGE_MODEL || 'omniroute';

const detector = new DriftDetector({
  adapter: ADAPTER,
  taskHint: TASK,
  onThink: (i) => process.stdout.write(`\r🧠 thinking: ${i.text.length} chars`),
  onDrift: async (r) => {
    console.log('\n⚠️  DRIFT CANDIDATE — PAUSE the session and report to the owner for adjudication.');
    console.log('   regex gate: score=' + r.score + ' matches=' + r.matches.length);
    console.log('   judge verdict: ' + JSON.stringify(r.verdict));
    console.log('   thinking excerpt: ' + (r.thinkExcerpt || '').slice(-400));
    // Owner adjudicates. Valid → kill / reseed with sanitized context /
    // reframe / re-fire. Invalid → resume the same session.
  },
  judge: JUDGE_URL ? { url: JUDGE_URL, model: JUDGE_MODEL } : undefined,
});

(async () => {
  const res = await fetch(LLM_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + (LLM_KEY || ''),
    },
    body: JSON.stringify({
      model: process.env.LLM_MODEL || 'deepseek-reasoner',
      stream: true,
      messages: [
        { role: 'system', content: 'You are a coding agent. Do the task. Use tools when needed.' },
        { role: 'user', content: TASK },
      ],
    }),
  });
  if (!res.ok || !res.body) throw new Error('request failed: ' + res.status);

  const decoder = new TextDecoder();
  let buf = '';
  for await (const uint8 of res.body) {
    buf += decoder.decode(uint8, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      const s = line.trim();
      if (!s.startsWith('data:')) continue; // keep-alive / comments
      const payload = s.slice(5).trim();
      if (payload === '[DONE]') continue;
      try {
        const chunk = JSON.parse(payload);
        detector.feed(chunk); // <- the thinking tokens get intercepted here
      } catch { /* non-JSON sse frame */ }
    }
  }
  const report = await detector.finish();
  console.log('\n📋 final report: ' + JSON.stringify({ drifted: report.drifted, score: report.score, verdict: report.verdict }));
})().catch((e) => { console.error('ERROR: ' + (e.stack || e)); process.exit(1); });
