import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/api';

export const useTenants = (params: { status_filter?: string; limit?: number; offset?: number } = {}) => {
  return useQuery({
    queryKey: ['admin', 'tenants', params],
    queryFn: () => apiClient.listTenants(params),
    staleTime: 5000,
  });
};

export const useCreateTenant = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { id: string; name: string; config?: any; metadata?: any }) => apiClient.createTenant(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tenants'] }),
  });
};

export const useUpdateTenant = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { tenantId: string; payload: { name?: string | null; status?: string | null; config?: any; metadata?: any } }) =>
      apiClient.updateTenant(args.tenantId, args.payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tenants'] }),
  });
};

export const useDeleteTenant = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { tenantId: string; hardDelete?: boolean }) => apiClient.deleteTenant(args.tenantId, Boolean(args.hardDelete)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tenants'] }),
  });
};

export const usePolicies = (enabledOnly: boolean = false) => {
  return useQuery({
    queryKey: ['admin', 'policies', enabledOnly],
    queryFn: () => apiClient.listPolicies(enabledOnly),
    staleTime: 5000,
  });
};

export const useUpsertPolicy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { id?: string | null; name: string; enabled: boolean; match: any; action: any }) =>
      apiClient.upsertPolicy(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'policies'] }),
  });
};

export const useDeletePolicy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (policyId: string) => apiClient.deletePolicy(policyId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'policies'] }),
  });
};

export const useApprovals = () => {
  return useQuery({
    queryKey: ['admin', 'approvals'],
    queryFn: () => apiClient.listApprovals(),
    refetchInterval: 10000,
    staleTime: 2000,
  });
};

export const useApproveRemediation = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { token_id: string; approver: string; comment?: string | null }) => apiClient.approveRemediation(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'approvals'] }),
  });
};

export const useRejectRemediation = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { token_id: string; rejector: string; reason?: string | null }) => apiClient.rejectRemediation(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'approvals'] }),
  });
};

