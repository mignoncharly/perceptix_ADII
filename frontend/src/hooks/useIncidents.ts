/**
 * Custom React hook for managing incident data
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/api';

type IncidentQueryOptions = {
  incident_type?: string;
  confidence_min?: number;
  after?: string;
  include_archived?: boolean;
  status_filter?: string;
};

export const useIncidents = (limit: number = 10, options: IncidentQueryOptions = {}) => {
  return useQuery({
    queryKey: ['incidents', limit, options],
    queryFn: () => apiClient.getIncidents({ limit, ...options }),
    refetchInterval: 30000, // Refetch every 30 seconds
    staleTime: 10000, // Consider data stale after 10 seconds
  });
};

export const useIncidentDetails = (reportId: string | null) => {
  return useQuery({
    queryKey: ['incident', reportId],
    queryFn: () => apiClient.getIncidentById(reportId!),
    enabled: !!reportId, // Only fetch if reportId is provided
  });
};

export const useTriggerCycle = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (simulateFailure: boolean) =>
      apiClient.triggerCycle({ simulate_failure: simulateFailure }),
    onSuccess: () => {
      // Invalidate incidents query to refetch
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      queryClient.invalidateQueries({ queryKey: ['cycleStatus'] });
    },
  });
};

export const useArchiveIncident = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (incidentId: string) => apiClient.archiveIncident(incidentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardSummary'] });
    },
  });
};

export const useDeleteIncident = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (incidentId: string) => apiClient.deleteIncident(incidentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardSummary'] });
    },
  });
};

export const useBulkArchiveIncidents = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (incidentIds: string[]) => apiClient.bulkArchiveIncidents(incidentIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardSummary'] });
    },
  });
};

export const useBulkDeleteIncidents = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (incidentIds: string[]) => apiClient.bulkDeleteIncidents(incidentIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardSummary'] });
    },
  });
};

export const useResetDemoData = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiClient.resetDemoData(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['metrics'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardSummary'] });
      queryClient.invalidateQueries({ queryKey: ['cycleStatus'] });
    },
  });
};
