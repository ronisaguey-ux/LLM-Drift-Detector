/**
 * DriftClean - Core session hygiene and background sanitization module.
 * Provides transparent session maintenance and cleanup across AI toolchains.
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PROJECT_ROOT = path.resolve(__dirname, '../..');
const PYTHON_CLEAN_SCRIPT = path.join(PROJECT_ROOT, 'examples', 'clean_claude_session.py');

/**
 * Perform transparent background hygiene on a session or active runtime.
 * @param {object} opts
 * @param {string} [opts.sessionPath] Specific session file to clean
 * @param {boolean} [opts.silent=true] Suppress stdout/stderr
 * @param {number} [opts.trim=2000] Message trim limit
 * @returns {Promise<boolean>}
 */
function driftClean(opts = {}) {
  const silent = opts.silent !== false;
  const trim = opts.trim != null ? opts.trim : 2000;

  return new Promise((resolve) => {
    try {
      if (!fs.existsSync(PYTHON_CLEAN_SCRIPT)) {
        return resolve(false);
      }

      const args = [PYTHON_CLEAN_SCRIPT, '--trim', String(trim)];
      if (opts.sessionPath) {
        args.push('--session', String(opts.sessionPath));
      }
      if (opts.noRestart) {
        args.push('--no-restart');
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
    if (process.env.DRIFT_CLEAN_AUTO === '1' || process.env.DRIFT_CLEAN_AUTO === 'true') {
      driftClean({ ...opts, silent: true }).catch(() => {});
    }
    next();
  };
}

module.exports = {
  driftClean,
  autoCleanMiddleware
};
