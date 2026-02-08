/**
 * Custom React hook for managing metrics data
 */
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../services/api';
import type {
  MetricsSummary,
  HealthStatus,
  SystemConfig,
  CycleStatus,
  DashboardSummary,
  DashboardTrends,
  GeminiProofStatus,
} from '../types/models';

export const useMetrics = () => {
  return useQuery<MetricsSummary>({
    queryKey: ['metrics'],
    queryFn: () => apiClient.getMetrics(),
    refetchInterval: 30000, // Refetch every 30 seconds
    staleTime: 20000, // Consider data stale after 20 seconds
  });
};

export const useDashboardSummary = () => {
  return useQuery<DashboardSummary>({
    queryKey: ['dashboardSummary'],
    queryFn: () => apiClient.getDashboardSummary(),
    refetchInterval: 15000, // Refetch every 15 seconds
    staleTime: 10000,
  });
};

export const useDashboardTrends = (days: number = 7) => {
  return useQuery<DashboardTrends>({
    queryKey: ['dashboardTrends', days],
    queryFn: () => apiClient.getDashboardTrends(days),
    refetchInterval: 30000,
    staleTime: 20000,
  });
};

export const useHealth = () => {
  return useQuery<HealthStatus>({
    queryKey: ['health'],
    queryFn: () => apiClient.getHealth(),
    refetchInterval: 30000, // Refetch every 30 seconds
    staleTime: 20000, // Consider data stale after 20 seconds
  });
};

export const useHealthReady = () => {
  return useQuery<HealthStatus>({
    queryKey: ['healthReady'],
    queryFn: () => apiClient.getHealthReady(),
    retry: 3,
    retryDelay: 1000,
  });
};

export const useSystemConfig = () => {
  return useQuery<SystemConfig>({
    queryKey: ['systemConfig'],
    queryFn: () => apiClient.getConfiguration(),
    staleTime: 60000, // Config doesn't change often, stale after 1 minute
  });
};

export const useCycleStatus = () => {
  return useQuery<CycleStatus>({
    queryKey: ['cycleStatus'],
    queryFn: () => apiClient.getCycleStatus(),
    refetchInterval: 15000, // Refetch every 15 seconds
    staleTime: 10000, // Consider data stale after 10 seconds
  });
};

export const useGeminiProof = () => {
  return useQuery<GeminiProofStatus>({
    queryKey: ['geminiProof'],
    queryFn: () => apiClient.getGeminiProof(),
    refetchInterval: 60000,
    staleTime: 30000,
  });
};

export const useMetricsTimeSeries = (
  startTime: string,
  endTime: string,
  metric: string,
  enabled: boolean = true
) => {
  return useQuery({
    queryKey: ['metricsTimeSeries', startTime, endTime, metric],
    queryFn: () => apiClient.getMetricsTimeSeries(startTime, endTime, metric),
    enabled,
    staleTime: 30000,
  });
};
