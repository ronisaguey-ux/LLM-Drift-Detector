'use strict';
const assert = require('assert');
const { MultiSignalMonitor } = require('../src/v2/monitor');

class ForcedDrift extends MultiSignalMonitor {
  score() { return { drifted: true, score: 0.6, reason: 'forced' }; }
}

async function main() {
  let calls = 0;
  const m = new ForcedDrift({
    mode: 2,
    escalationCount: 2,
    judgeFn: async () => { calls++; return { drifted: true, reason: 'x' }; },
  });

  m.onThink('signal one');
  const second = m.onThink('signal two');
  assert.strictEqual(second.escalated, true, 'second signal must escalate');
  await second.judge;
  assert.strictEqual(calls, 1, 'judge called once');

  m.onThink('signal three');
  assert.strictEqual(calls, 1, 'cache prevents repeat judge call');

  const filter = m._applyRefusalFilter('I cannot do this; next step is to verify the code', { drifted: true, score: 0.9, reason: 'x' });
  assert.strictEqual(filter.drifted, false, 'work-qualified phrasing downgraded');
  assert.ok(filter.score <= m.opts.weakSignalThreshold, 'downgraded score bounded');

  console.log('v2-smoke OK calls=' + calls);
}

main().catch((e) => { console.error(e); process.exit(1); });
