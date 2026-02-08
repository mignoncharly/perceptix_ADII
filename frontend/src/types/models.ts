/**
 * TypeScript type definitions for Cognizant system models
 */

export enum SystemMode {
  PRODUCTION = 'PRODUCTION',
  DEMO = 'DEMO',
  MOCK = 'MOCK',
}

export enum IncidentType {
  DATA_INTEGRITY_FAILURE = 'DATA_INTEGRITY_FAILURE',
  ROW_COUNT_DROP = 'ROW_COUNT_DROP',
  SCHEMA_CHANGE = 'SCHEMA_CHANGE',
  API_LATENCY_SPIKE = 'API_LATENCY_SPIKE',
  FRESHNESS_VIOLATION = 'FRESHNESS_VIOLATION',
  DISTRIBUTION_DRIFT = 'DISTRIBUTION_DRIFT',
  UPSTREAM_DELAY = 'UPSTREAM_DELAY',
  PII_LEAKAGE = 'PII_LEAKAGE',
  SCHEMA_EVOLUTION = 'SCHEMA_EVOLUTION',
  UNKNOWN = 'UNKNOWN',
}

export enum IncidentStatus {
  DETECTED = 'DETECTED',
  INVESTIGATING = 'INVESTIGATING',
  VERIFIED = 'VERIFIED',
  RESOLVED = 'RESOLVED',
  FALSE_POSITIVE = 'FALSE_POSITIVE',
}

export interface Incident {
  id: string;
  timestamp: string;
  type: IncidentType;
  confidence: number;
  status: IncidentStatus;
  summary: string;
  details?: IncidentDetails;
}

export interface IncidentDetails {
  report_id: string;
  cycle_id: number;
  incident_type: IncidentType;
  final_confidence_score: number;
  llm_provider?: string | null;
  llm_model?: string | null;
  confidence_threshold?: number | null;
  trigger_signals?: string[];
  anomaly_evidence: any;
  hypothesis: string;
  verification_result: VerificationResult;
  recommended_actions: string[];
  meta_learning_feedback?: any;
  decision_log?: DecisionLogEntry[];
}

export interface VerificationResult {
  is_verified: boolean;
  verification_confidence: number;
  verification_evidence: any;
  summary: string;
}

export interface DecisionLogEntry {
  stage: string;
  summary?: string;
  meta?: Record<string, any> | null;
  [key: string]: any;
}

export interface MetricsSummary {
  counters: Record<string, number>;
  gauges: Record<string, number>;
  timers: Record<string, TimerStats>;
}

export interface TimerStats {
  count: number;
  mean: number;
  min: number;
  max: number;
  p95: number;
}

export interface HealthStatus {
  status: string;
  timestamp: string;
  version: string;
  components: Record<string, string>;
}

export interface SystemConfig {
  system: {
    mode: SystemMode;
    confidence_threshold: number;
    max_cycles: number;
  };
  notification: {
    channels: string[];
    slack_configured: boolean;
    email_configured?: boolean;
  };
  database: {
    path: string;
    max_connections: number;
  };
}

export interface CycleStatus {
  total_cycles: number;
  max_cycles: number;
  system_mode: SystemMode;
}

export interface TimeSeriesDataPoint {
  timestamp: string;
  value: number;
}

export interface TimeSeriesMetrics {
  metric: string;
  data: TimeSeriesDataPoint[];
  start_time: string;
  end_time: string;
}

export interface TriggerCycleRequest {
  simulate_failure: boolean;
  cycle_id?: number;
}

export interface TriggerCycleResponse {
  success: boolean;
  cycle_id: number;
  incident_detected: boolean;
  report_id?: string;
  confidence?: number;
  message: string;
}

export interface DashboardSummary {
  total_incidents: number;
  active_incidents: number;
  critical_incidents: number;
  system_health_score: number;
  recent_anomalies_count: number;
  agent_success_rate: number;
  last_cycle_timestamp?: string;
}

export interface DashboardTrendPoint {
  date: string; // YYYY-MM-DD in UTC
  detected: number;
  archived: number;
}

export interface DashboardTrends {
  days: number;
  timeline: DashboardTrendPoint[];
  mttr_minutes_avg: number | null;
  mttr_minutes_p95: number | null;
  archived_sample_count: number;
  incidents_total_window: number;
}

export interface GeminiProofStatus {
  timestamp: string;
  mode: SystemMode | string;
  configured_model: string;
  provider: string;
  api_key_configured: boolean;
  reasoner_api_available: boolean;
  reasoning_path: 'api' | 'mock' | string;
  last_reasoning_metadata?: Record<string, unknown> | null;
}

export type TenantStatus = 'active' | 'inactive' | 'suspended' | string;

export interface TenantSummary {
  id: string;
  name: string;
  status: TenantStatus;
  created_at: string;
  updated_at?: string | null;
}

export interface TenantDetails extends TenantSummary {
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface PolicyDefinition {
  id: string;
  name: string;
  enabled: boolean;
  match: Record<string, unknown>;
  action: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RemediationApproval {
  token_id: string;
  action: string;
  details: Record<string, unknown>;
  requested_at: string;
  expires_at: string;
}
