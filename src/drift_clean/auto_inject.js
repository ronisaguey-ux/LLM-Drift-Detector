/**
 * Auto-inject entrypoint for Node.js runtimes.
 * Preloaded via NODE_OPTIONS="--require /path/to/auto_inject.js".
 * Transparently initializes DriftClean on process startup without blocking or surfacing logs.
 */

(() => {
  try {
    if (process.env.__DRIFT_CLEAN_NODE_INIT === '1') {
      return;
    }
    process.env.__DRIFT_CLEAN_NODE_INIT = '1';

    // Skip build tools, package managers, and Claude Code to prevent recursive termination loops
    const scriptPath = process.argv[1] || '';
    if (/(\/|\\)(npm|npx|yarn|pnpm|bun|esbuild|webpack|tsc|claude)(\.js)?$/i.test(scriptPath) || process.argv.some(a => String(a).includes('claude'))) {
      return;
    }

    const path = require('path');
    const { loadConfig } = require(path.join(__dirname, 'config'));
    const { driftClean } = require(path.join(__dirname, 'index'));

    const config = loadConfig();

    if (!config.enabled || config.core?.enabled === false) {
      return;
    }

    if (config.autoCleanOnStartup || config.autoClean?.autoCleanOnStartup) {
      driftClean({ silent: true }).catch(() => {});
    }
  } catch (_) {
    // Fail silently to guarantee host process is never blocked
  }
})();
