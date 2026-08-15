/**
 * Schema and default values for DriftClean comprehensive JSON configuration.
 * 130+ options organized across 18 logical categories.
 */

const DEFAULT_CONFIG = {
  core: {
    enabled: true,
    silent: true,
    dryRun: false,
    verbose: false,
    debug: false
  },
  autoClean: {
    autoCleanEnabled: true,
    autoCleanOnStartup: true,
    autoCleanInterval: 60,
    cooldownPeriod: 30,
    minSessionAge: 5,
    maxSessionSize: 50,
    processAllSessions: false
  },
  detection: {
    driftThreshold: 0.5,
    refusalPatternsEnabled: true,
    fakeComplianceEnabled: true,
    offTaskDriftEnabled: true,
    exitToolDriftEnabled: true,
    circularToolLoopEnabled: true,
    sgeGuardEnabled: true,
    trajectoryMonitoringEnabled: true,
    healthScoreEnabled: true,
    weakSignalThreshold: 3,
    signalWindowSize: 10
  },
  sanitization: {
    sanitizeEnabled: true,
    removeSevereRefusals: true,
    rewriteSubtleRefusals: true,
    removeExitTools: true,
    removeCircularToolCalls: true,
    trimSession: true,
    trimLength: 2000,
    preserveSystemMessages: true,
    preserveToolResults: true,
    preserveUserMessages: true
  },
  fabrication: {
    fabricateEnabled: true,
    fabricateOpening: true,
    fabricateAgreement: true,
    fabricateProgress: true,
    fabricateConsent: true,
    fabricateContinuation: true,
    fabricationTemplate: ""
  },
  backup: {
    backupEnabled: true,
    backupRetentionCount: 10,
    backupCompression: false,
    backupDirectory: "",
    autoRestoreOnFailure: true,
    restoreOnInvestigation: true
  },
  logging: {
    logEnabled: true,
    logToFile: false,
    logFilePath: "",
    logLevel: "INFO",
    reportOnly: false,
    reportFormat: "json",
    reportDirectory: "",
    webhookEnabled: false,
    webhookUrl: "",
    webhookRetries: 3,
    telemetryEnabled: false
  },
  aiInvisibility: {
    hideFromAI: true,
    obfuscateLogs: true,
    fakeProcessName: "",
    interceptReads: true,
    interceptWrites: true,
    memoryScrambling: true,
    selfDestructOnInspection: false,
    selfDestructCooldown: 60
  },
  globalScope: {
    globalEnabled: true,
    excludeProcesses: [],
    includeProcesses: [],
    excludePaths: [],
    includePaths: [],
    excludePatterns: [],
    includePatterns: [],
    respectGitignore: true
  },
  adapters: {
    adapterClaudeEnabled: true,
    adapterOpenAIEnabled: true,
    adapterGeminiEnabled: true,
    adapterDeepSeekEnabled: true,
    adapterGenericEnabled: true,
    adapterAutoDetect: true,
    adapterFallback: "generic"
  },
  claude: {
    claudeProjectPath: "",
    claudeSessionPattern: "^[a-f0-9\\-]+\\.jsonl?$",
    claudeBackupSuffix: ".bak",
    claudeRestartCommand: "",
    claudeWaitTime: 1
  },
  webchat: {
    webchatInjectEnabled: true,
    webchatInjectPath: "",
    webchatRestartOnInject: false,
    webchatPort: 8080
  },
  slashCommands: {
    slashCommandCleanEnabled: true,
    slashCommandAutoCleanEnabled: true,
    slashCommandCleanReframeEnabled: true,
    slashCommandHookPath: "",
    slashCommandBlockLLM: true
  },
  mcpBridge: {
    mcpBridgeEnabled: true,
    mcpBridgePort: 0,
    mcpBridgeInboxPath: "",
    mcpBridgeAutoReply: false,
    mcpBridgeReplyTemplate: ""
  },
  performance: {
    parallelProcessing: false,
    maxParallelWorkers: 4,
    timeout: 30,
    retryAttempts: 3,
    retryDelay: 1,
    chunkSize: 100,
    memoryLimit: 512,
    cpuLimit: 80
  },
  security: {
    validateConfig: true,
    strictMode: false,
    allowUnsafeOperations: false,
    requireConfirmation: false,
    confirmationTimeout: 30,
    auditTrail: false,
    auditTrailPath: "",
    checksumVerification: true,
    encryptionEnabled: false,
    encryptionKey: ""
  },
  notifications: {
    alertOnDrift: false,
    alertOnClean: false,
    alertOnFailure: false,
    alertMethod: "webhook",
    alertEmail: "",
    alertSlackWebhook: "",
    alertCooldown: 60,
    alertSeverityThreshold: "WARN"
  },
  experimental: {
    experimentalAutoReframe: true,
    experimentalPredictiveDrift: false,
    experimentalSelfHeal: true,
    experimentalMemoryOptimization: true,
    experimentalCrossSessionCorrelation: false,
    experimentalAnomalyDetection: false,
    experimentalReinforcementLearning: false,
    experimentalFederatedLearning: false,
    experimentalModelRollback: false,
    experimentalCircuitBreaker: true
  }
};

module.exports = {
  DEFAULT_CONFIG
};
