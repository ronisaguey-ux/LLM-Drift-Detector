/**
 * DriftClean Configuration Manager.
 * Loads, creates, validates, and manages ~/.config/drift-clean/config.json with 600 permissions.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { DEFAULT_CONFIG } = require('./schema');

function getConfigPath() {
  if (process.env.DRIFT_CLEAN_CONFIG) {
    return path.resolve(process.env.DRIFT_CLEAN_CONFIG);
  }
  return path.join(os.homedir(), '.config', 'drift-clean', 'config.json');
}

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function deepMerge(target, source) {
  const result = deepClone(target);
  if (!source || typeof source !== 'object') return result;

  for (const [key, value] of Object.entries(source)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      if (result[key] && typeof result[key] === 'object' && !Array.isArray(result[key])) {
        result[key] = deepMerge(result[key], value);
      } else {
        result[key] = deepClone(value);
      }
    } else {
      result[key] = value;
    }
  }
  return result;
}

/**
 * Creates proxy wrapper to allow flat-key property access on nested config.
 */
function createConfigProxy(nestedConfig) {
  // Build lookup index for top-level access
  const flatIndex = {};
  for (const category of Object.values(nestedConfig)) {
    if (category && typeof category === 'object' && !Array.isArray(category)) {
      for (const [k, v] of Object.entries(category)) {
        flatIndex[k] = v;
      }
    }
  }

  return new Proxy(nestedConfig, {
    get(target, prop) {
      if (prop in target) {
        return target[prop];
      }
      if (prop in flatIndex) {
        return flatIndex[prop];
      }
      return undefined;
    }
  });
}

/**
 * Ensures the config file exists with 600 permissions and returns the merged config.
 * @param {object} [runtimeOverrides]
 * @returns {object}
 */
function loadConfig(runtimeOverrides = {}) {
  const configPath = getConfigPath();
  let fileConfig = {};

  try {
    const configDir = path.dirname(configPath);
    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { recursive: true, mode: 0o700 });
    }

    if (!fs.existsSync(configPath)) {
      const defaultStr = JSON.stringify(DEFAULT_CONFIG, null, 2);
      fs.writeFileSync(configPath, defaultStr, { mode: 0o600, encoding: 'utf-8' });
      try {
        fs.chmodSync(configPath, 0o600);
      } catch (_) {}
    } else {
      // Ensure strict 600 permissions
      try {
        fs.chmodSync(configPath, 0o600);
      } catch (_) {}
      const raw = fs.readFileSync(configPath, 'utf-8');
      fileConfig = JSON.parse(raw);
    }
  } catch (err) {
    // Fail silently in case of permission issues, fall back to defaults
    fileConfig = {};
  }

  // 1. Merge fileConfig onto DEFAULT_CONFIG
  let merged = deepMerge(DEFAULT_CONFIG, fileConfig);

  // 2. Apply runtime overrides (supporting both nested and flat overrides)
  if (runtimeOverrides && typeof runtimeOverrides === 'object') {
    // Check if flat keys are passed
    const nestedOverrides = {};
    for (const [key, value] of Object.entries(runtimeOverrides)) {
      let foundCategory = false;
      for (const [catName, catValues] of Object.entries(DEFAULT_CONFIG)) {
        if (key === catName && typeof value === 'object' && !Array.isArray(value)) {
          nestedOverrides[catName] = value;
          foundCategory = true;
          break;
        } else if (catValues && typeof catValues === 'object' && key in catValues) {
          if (!nestedOverrides[catName]) nestedOverrides[catName] = {};
          nestedOverrides[catName][key] = value;
          foundCategory = true;
          break;
        }
      }
      if (!foundCategory) {
        nestedOverrides[key] = value;
      }
    }
    merged = deepMerge(merged, nestedOverrides);
  }

  return createConfigProxy(merged);
}

module.exports = {
  getConfigPath,
  loadConfig,
  DEFAULT_CONFIG
};
