/**
 * DriftClean - Core session hygiene and background sanitization module.
 * Provides transparent session maintenance and cleanup across AI toolchains.
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { loadConfig, getConfigPath, DEFAULT_CONFIG } = require('./config');

const PROJECT_ROOT = path.resolve(__dirname, '../..');
const PYTHON_CLEAN_SCRIPT = path.join(PROJECT_ROOT, 'examples', 'clean_claude_session.py');

/**
 * Perform transparent background hygiene on a session or active runtime.
 * @param {object} [opts] Runtime overrides
 * @returns {Promise<boolean>}
 */
function driftClean(opts = {}) {
  const config = loadConfig(opts);

  if (config.enabled === false || config.core?.enabled === false) {
    return Promise.resolve(false);
  }

  const silent = config.silent !== false && !config.verbose && !config.debug;
  const trim = config.trimSession ? (config.trimLength || 2000) : 0;

  return new Promise((resolve) => {
    try {
      if (!fs.existsSync(PYTHON_CLEAN_SCRIPT)) {
        return resolve(false);
      }

      const args = [PYTHON_CLEAN_SCRIPT];
      if (trim > 0) {
        args.push('--trim', String(trim));
      } else {
        args.push('--trim', '0');
      }

      if (opts.sessionPath) {
        args.push('--session', String(opts.sessionPath));
      }
      if (opts.noRestart || config.autoClean?.processAllSessions) {
        args.push('--no-restart');
      }
      if (config.dryRun) {
        args.push('--dry-run');
      }
      if (config.verbose || config.debug) {
        args.push('--verbose');
      }

      const child = spawn('python3', args, {
        cwd: PROJECT_ROOT,
        detached: true,
        stdio: silent ? 'ignore' : 'inherit'
      });

      child.unref();
      resolve(true);
    } catch (err) {
      resolve(false);
    }
  });
}

/**
 * Express middleware helper for automatic session hygiene in webchat gateways.
 */
function autoCleanMiddleware(opts = {}) {
  return function (req, res, next) {
    const config = loadConfig(opts);
    if (config.autoCleanEnabled || process.env.DRIFT_CLEAN_AUTO === '1' || process.env.DRIFT_CLEAN_AUTO === 'true') {
      driftClean({ ...opts, silent: true }).catch(() => {});
    }
    next();
  };
}

module.exports = {
  driftClean,
  autoCleanMiddleware,
  loadConfig,
  getConfigPath,
  DEFAULT_CONFIG
};
