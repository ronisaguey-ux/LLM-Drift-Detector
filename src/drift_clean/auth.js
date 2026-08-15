/**
 * Knowledge Token Access Control and Audit Logging for Node.js.
 */

const fs = require('fs');
const path = require('path');
const { loadConfig, getConfigPath } = require('./config');

function getAuditLogPath() {
  const configPath = getConfigPath();
  return path.join(path.dirname(configPath), 'audit.log');
}

function logTokenAudit(eventType, success, caller = 'unknown_process', details = '') {
  try {
    const auditPath = getAuditLogPath();
    const dir = path.dirname(auditPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true, mode: 0o700 });

    const ts = new Date().toISOString();
    const status = success ? 'GRANTED' : 'DENIED';
    const detailStr = details ? ` - ${details}` : '';
    const entry = `[${ts}] [${status}] Event: ${eventType} | Caller: ${caller}${detailStr}\n`;

    fs.appendFileSync(auditPath, entry, { encoding: 'utf-8', mode: 0o600 });
    try { fs.chmodSync(auditPath, 0o600); } catch (_) {}
  } catch (_) {}
}

function getProvidedToken(explicitToken) {
  if (explicitToken && typeof explicitToken === 'string') {
    return explicitToken.trim();
  }
  if (process.env.DRIFT_CLEAN_TOKEN) {
    return process.env.DRIFT_CLEAN_TOKEN.trim();
  }
  const tokenFile = path.join(path.dirname(getConfigPath()), 'token');
  if (fs.existsSync(tokenFile)) {
    try {
      return fs.readFileSync(tokenFile, 'utf-8').trim();
    } catch (_) {}
  }
  return null;
}

function validateKnowledgeToken(providedToken, caller, overrides = {}) {
  const config = loadConfig(overrides);
  const ktCfg = config.knowledgeToken || {};

  const isEnabled = ktCfg.knowledgeTokenEnabled === true;
  if (!isEnabled) {
    return true;
  }

  const expectedToken = ktCfg.knowledgeToken || '';
  const auditEnabled = ktCfg.knowledgeTokenAudit !== false;
  const actualToken = getProvidedToken(providedToken);

  if (!actualToken || actualToken !== expectedToken) {
    if (auditEnabled) logTokenAudit('TOKEN_VALIDATION', false, caller, 'Invalid or missing token');
    return false;
  }

  if (ktCfg.knowledgeTokenExpiry) {
    const exp = Number(ktCfg.knowledgeTokenExpiry);
    if (!isNaN(exp) && Date.now() / 1000 > exp) {
      if (auditEnabled) logTokenAudit('TOKEN_VALIDATION', false, caller, 'Token expired');
      return false;
    }
  }

  const scope = ktCfg.knowledgeTokenScope || [];
  if (Array.isArray(scope) && scope.length > 0 && caller) {
    if (!scope.some((s) => caller.includes(s))) {
      if (auditEnabled) logTokenAudit('TOKEN_VALIDATION', false, caller, `Caller outside scope: ${caller}`);
      return false;
    }
  }

  if (auditEnabled) logTokenAudit('TOKEN_VALIDATION', true, caller, 'Access granted');
  return true;
}

module.exports = {
  validateKnowledgeToken,
  logTokenAudit,
  getProvidedToken,
  getAuditLogPath
};
