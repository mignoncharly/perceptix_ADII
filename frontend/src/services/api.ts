/**
 * API Client Service
 * Handles all HTTP communication with the backend API
 */
import axios, { AxiosInstance, AxiosError, AxiosHeaders } from 'axios';
import type {
  HealthStatus,
  MetricsSummary,
  Incident,
  IncidentDetails,
  SystemConfig,
  CycleStatus,
  TriggerCycleRequest,
  TriggerCycleResponse,
  TimeSeriesMetrics,
  DashboardSummary,
  DashboardTrends,
  GeminiProofStatus,
  TenantSummary,
  TenantDetails,
  PolicyDefinition,
  RemediationApproval,
} from '../types/models';

class APIClient {
  private client: AxiosInstance;
  private baseURL: string;
  private accessToken: string | null = null;
  private authInFlight: Promise<string> | null = null;
  private readonly tokenStorageKey = 'perceptix_access_token';
  private readonly tenantStorageKey = 'perceptix_tenant_id';
  private readonly triggerCycleTimeoutMs =
    Number(import.meta.env.VITE_TRIGGER_CYCLE_TIMEOUT_MS || 120000);

  constructor(baseURL: string = '') {
    this.baseURL = baseURL;
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.accessToken = this.readStoredToken();

    // Attach bearer token when available.
    this.client.interceptors.request.use((config) => {
      const tenantId = this.readStoredTenantId();
      if (tenantId) {
        const headers = AxiosHeaders.from(config.headers);
        headers.set('X-Tenant-ID', tenantId);
        config.headers = headers;
      }
      if (this.accessToken) {
        const headers = AxiosHeaders.from(config.headers);
        headers.set('Authorization', `Bearer ${this.accessToken}`);
        config.headers = headers;
      }
      return config;
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
      }
    );
  }

  private readStoredToken(): string | null {
    try {
      return localStorage.getItem(this.tokenStorageKey);
    } catch {
      return null;
    }
  }

  private readStoredTenantId(): string {
    try {
      return (
        localStorage.getItem(this.tenantStorageKey) ||
        import.meta.env.VITE_TENANT_ID ||
        'demo'
      );
    } catch {
      return import.meta.env.VITE_TENANT_ID || 'demo';
    }
  }

  private storeToken(token: string): void {
    this.accessToken = token;
    try {
      localStorage.setItem(this.tokenStorageKey, token);
    } catch {
      // Ignore storage failures and keep in-memory token.
    }
  }

  private clearToken(): void {
    this.accessToken = null;
    try {
      localStorage.removeItem(this.tokenStorageKey);
    } catch {
      // Ignore storage failures.
    }
  }

  private async fetchDemoToken(): Promise<string> {
    const username = import.meta.env.VITE_DEMO_USERNAME || 'demo';
    const password = import.meta.env.VITE_DEMO_PASSWORD || 'secret';

    const form = new URLSearchParams();
    form.set('username', username);
    form.set('password', password);

    const response = await this.client.post<{
      access_token: string;
      token_type: string;
    }>('/api/v1/auth/token', form.toString(), {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    if (!response.data.access_token) {
      throw new Error('Authentication succeeded but no access token was returned');
    }

    this.storeToken(response.data.access_token);
    return response.data.access_token;
  }

  private async ensureAuthToken(): Promise<string> {
    if (this.accessToken) {
      return this.accessToken;
    }

    if (!this.authInFlight) {
      this.authInFlight = this.fetchDemoToken().finally(() => {
        this.authInFlight = null;
      });
    }

    return this.authInFlight;
  }

  private async requestWithAuthRetry<T>(
    requestFn: () => Promise<T>
  ): Promise<T> {
    await this.ensureAuthToken();
    try {
      return await requestFn();
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        this.clearToken();
        await this.ensureAuthToken();
        return requestFn();
      }
      throw error;
    }
  }

  // Health endpoints
  async getHealth(): Promise<HealthStatus> {
    const response = await this.client.get<HealthStatus>('/health');
    return response.data;
  }

  async getHealthReady(): Promise<HealthStatus> {
    const response = await this.client.get<HealthStatus>('/health/ready');
    return response.data;
  }

  // Metrics endpoints
  async getMetrics(): Promise<MetricsSummary> {
    const response = await this.client.get<MetricsSummary>('/api/v1/metrics');
    return response.data;
  }

  async getPrometheusMetrics(): Promise<string> {
    const response = await this.client.get<string>('/metrics');
    return response.data;
  }

  async getMetricsTimeSeries(
    startTime: string,
    endTime: string,
    metric: string
  ): Promise<TimeSeriesMetrics> {
    const response = await this.client.get<TimeSeriesMetrics>(
      '/api/v1/metrics/timeseries',
      {
        params: { start_time: startTime, end_time: endTime, metric },
      }
    );
    return response.data;
  }

  // Cycle endpoints
  async triggerCycle(request: TriggerCycleRequest): Promise<TriggerCycleResponse> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<TriggerCycleResponse>(
        '/api/v1/cycles/trigger',
        request,
        { timeout: this.triggerCycleTimeoutMs }
      );
      return response.data;
    });
  }

  async getCycleStatus(): Promise<CycleStatus> {
    const response = await this.client.get<CycleStatus>('/api/v1/cycles/status');
    return response.data;
  }

  // Incident endpoints
  async getIncidents(params: {
    limit?: number;
    incident_type?: string;
    confidence_min?: number;
    after?: string;
    include_archived?: boolean;
    status_filter?: string;
  } = {}): Promise<{ count: number; incidents: Incident[] }> {
    const response = await this.client.get<{ count: number; incidents: Incident[] }>(
      '/api/v1/incidents',
      { params }
    );
    return response.data;
  }

  async getIncidentById(reportId: string): Promise<IncidentDetails> {
    const response = await this.client.get<{
      id: string;
      timestamp: string;
      type: string;
      confidence: number;
      summary: string;
      details: IncidentDetails;
    }>(`/api/v1/incidents/${reportId}`);
    return response.data.details;
  }

  async archiveIncident(reportId: string): Promise<{ success: boolean; report_id: string; action: string }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{ success: boolean; report_id: string; action: string }>(
        `/api/v1/incidents/${reportId}/archive`
      );
      return response.data;
    });
  }

  async deleteIncident(reportId: string): Promise<{ success: boolean; report_id: string; action: string }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.delete<{ success: boolean; report_id: string; action: string }>(
        `/api/v1/incidents/${reportId}`
      );
      return response.data;
    });
  }

  async bulkArchiveIncidents(incidentIds: string[]): Promise<{
    success: boolean;
    action: string;
    requested_count: number;
    affected_count: number;
  }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{
        success: boolean;
        action: string;
        requested_count: number;
        affected_count: number;
      }>('/api/v1/incidents/bulk/archive', { incident_ids: incidentIds });
      return response.data;
    });
  }

  async bulkDeleteIncidents(incidentIds: string[]): Promise<{
    success: boolean;
    action: string;
    requested_count: number;
    affected_count: number;
  }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{
        success: boolean;
        action: string;
        requested_count: number;
        affected_count: number;
      }>('/api/v1/incidents/bulk/delete', { incident_ids: incidentIds });
      return response.data;
    });
  }

  // Dashboard endpoints
  async getDashboardSummary(): Promise<DashboardSummary> {
    const response = await this.client.get<DashboardSummary>('/api/v1/dashboard/summary');
    return response.data;
  }

  async getDashboardTrends(days: number = 7): Promise<DashboardTrends> {
    const response = await this.client.get<DashboardTrends>('/api/v1/dashboard/trends', {
      params: { days },
    });
    return response.data;
  }

  // Configuration endpoints
  async getConfiguration(): Promise<SystemConfig> {
    const response = await this.client.get<SystemConfig>('/api/v1/config');
    return response.data;
  }

  async resetDemoData(): Promise<{
    success: boolean;
    message: string;
    incidents_deleted: number;
    metrics_deleted: number;
  }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{
        success: boolean;
        message: string;
        incidents_deleted: number;
        metrics_deleted: number;
      }>('/api/v1/admin/reset-demo-data');
      return response.data;
    });
  }

  async getGeminiProof(): Promise<GeminiProofStatus> {
    const response = await this.client.get<GeminiProofStatus>('/api/v1/hackathon/gemini-proof');
    return response.data;
  }

  // ---------------------------------------------------------------------
  // Admin endpoints (tenants, policies, approvals)
  // ---------------------------------------------------------------------

  async listTenants(params: { status_filter?: string; limit?: number; offset?: number } = {}): Promise<{
    tenants: TenantSummary[];
    total: number;
    limit: number;
    offset: number;
  }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.get<{
        tenants: TenantSummary[];
        total: number;
        limit: number;
        offset: number;
      }>('/api/v1/admin/tenants', { params });
      return response.data;
    });
  }

  async getTenant(tenantId: string): Promise<TenantDetails> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.get<TenantDetails>(`/api/v1/admin/tenants/${tenantId}`);
      return response.data;
    });
  }

  async createTenant(payload: {
    id: string;
    name: string;
    config?: Record<string, unknown> | null;
    metadata?: Record<string, unknown>;
  }): Promise<TenantDetails> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<TenantDetails>('/api/v1/admin/tenants', payload);
      return response.data;
    });
  }

  async updateTenant(
    tenantId: string,
    payload: {
      name?: string | null;
      config?: Record<string, unknown> | null;
      status?: string | null;
      metadata?: Record<string, unknown> | null;
    }
  ): Promise<TenantDetails> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.put<TenantDetails>(`/api/v1/admin/tenants/${tenantId}`, payload);
      return response.data;
    });
  }

  async deleteTenant(tenantId: string, hardDelete: boolean = false): Promise<void> {
    return this.requestWithAuthRetry(async () => {
      await this.client.delete(`/api/v1/admin/tenants/${tenantId}`, {
        params: { hard_delete: hardDelete },
      });
    });
  }

  async listPolicies(enabledOnly: boolean = false): Promise<{ policies: PolicyDefinition[]; count: number }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.get<{ policies: PolicyDefinition[]; count: number }>(
        '/api/v1/admin/policies',
        { params: { enabled_only: enabledOnly } }
      );
      return response.data;
    });
  }

  async upsertPolicy(payload: {
    id?: string | null;
    name: string;
    enabled: boolean;
    match: Record<string, unknown>;
    action: Record<string, unknown>;
  }): Promise<{ success: boolean; id: string }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{ success: boolean; id: string }>('/api/v1/admin/policies', payload);
      return response.data;
    });
  }

  async deletePolicy(policyId: string): Promise<{ success: boolean }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.delete<{ success: boolean }>(`/api/v1/admin/policies/${policyId}`);
      return response.data;
    });
  }

  async listApprovals(): Promise<RemediationApproval[]> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.get<RemediationApproval[]>('/api/v1/remediation/approvals');
      return response.data;
    });
  }

  async approveRemediation(payload: { token_id: string; approver: string; comment?: string | null }): Promise<{
    success: boolean;
    message: string;
  }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{ success: boolean; message: string }>(
        '/api/v1/remediation/approve',
        payload
      );
      return response.data;
    });
  }

  async rejectRemediation(payload: { token_id: string; rejector: string; reason?: string | null }): Promise<{
    success: boolean;
    message: string;
  }> {
    return this.requestWithAuthRetry(async () => {
      const response = await this.client.post<{ success: boolean; message: string }>(
        '/api/v1/remediation/reject',
        payload
      );
      return response.data;
    });
  }
}

// Export singleton instance
export const apiClient = new APIClient();

// Export class for testing
export { APIClient };
