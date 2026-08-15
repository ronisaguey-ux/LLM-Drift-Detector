// adapters.js — provider adapters. Each adapter knows where its provider
// hides the THINKING tokens inside the stream chunks. Plug any LLM API in by
// picking an adapter by name, or pass your own object with the same shape:
//   { extractThink(chunk) -> string|null,   // new thinking text in this chunk
//     isDone(chunk) -> boolean|void }        // stream finished?
// The generic adapter will usually work when none fits — it hunts for string
// values under think-ish keys anywhere in the chunk.

const THINK_KEY = /(?:reasoning|thought|think|chain.?of.?thought|internal)/i;
const MIN_THINK_LEN = 15; // short keys like finish_reason:"stop" are not thinking

function scanGeneric(obj, acc) {
  if (!obj || typeof obj !== 'object') return acc;
  if (Array.isArray(obj)) {
    for (const v of obj) scanGeneric(v, acc);
    return acc;
  }
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string') {
      if (THINK_KEY.test(k) && v.length >= MIN_THINK_LEN) acc.push(v);
    } else if (v && typeof v === 'object') {
      scanGeneric(v, acc);
    }
  }
  return acc;
}

const builtins = {
  // DeepSeek Reasoner — thinking streams in delta.reasoning_content
  deepseek: {
    name: 'deepseek',
    extractThink: (c) => {
      const d = c && c.choices && c.choices[0] && c.choices[0].delta;
      if (!d) return null;
      return d.reasoning_content || null;
    },
    isDone: (c) => !!(c && c.choices && c.choices[0] && c.choices[0].finish_reason),
  },

  // OpenAI o-series — delta.reasoning_content (some SDKs surface it as .reasoning)
  openai: {
    name: 'openai',
    extractThink: (c) => {
      const d = c && c.choices && c.choices[0] && c.choices[0].delta;
      if (!d) return null;
      return d.reasoning_content || d.reasoning || null;
    },
    isDone: (c) => !!(c && c.choices && c.choices[0] && c.choices[0].finish_reason),
  },

  // Anthropic — content_block_delta with delta.type === 'thinking'
  anthropic: {
    name: 'anthropic',
    extractThink: (c) =>
      c && c.type === 'content_block_delta' && c.delta && c.delta.type === 'thinking'
        ? c.delta.thinking || null
        : null,
    isDone: (c) => !!(c && c.type === 'message_stop'),
  },

  // Gemini — thinking streamed in parts flagged thought === true
  gemini: {
    name: 'gemini',
    extractThink: (c) => {
      const parts = c && c.candidates && c.candidates[0] && c.candidates[0].content && c.candidates[0].content.parts;
      if (!Array.isArray(parts)) return null;
      let out = '';
      for (const p of parts) {
        if (p && p.thought === true && typeof p.text === 'string') out += p.text;
      }
      return out || null;
    },
    isDone: (c) => !!(c && c.candidates && c.candidates[0] && (c.candidates[0].finishReason || c.candidates[0].finish_reason)),
  },

  // Generic fallback — recursive hunt for think-ish string values
  generic: {
    name: 'generic',
    extractThink: (c) => {
      const found = scanGeneric(c, []);
      return found.length ? found.join('') : null;
    },
    isDone: () => null, // never auto-done; the caller decides
  },
};

function resolveAdapter(adapter) {
  if (adapter && typeof adapter.extractThink === 'function') return adapter; // custom
  const key = String(adapter || 'generic').toLowerCase();
  return builtins[key] || builtins.generic;
}

module.exports = { builtins, resolveAdapter };
