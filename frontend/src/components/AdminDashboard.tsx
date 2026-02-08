import React, { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Divider,
  Grid,
  IconButton,
  Stack,
  TextField,
  Typography,
  Alert,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import { ArrowBack, Delete, Add, Check, Close } from '@mui/icons-material';
import { Link as RouterLink } from 'react-router-dom';
import {
  useApprovals,
  useApproveRemediation,
  useCreateTenant,
  useDeletePolicy,
  useDeleteTenant,
  usePolicies,
  useRejectRemediation,
  useTenants,
  useUpsertPolicy,
} from '../hooks/useAdmin';

const tenantStorageKey = 'perceptix_tenant_id';

function readTenantId(): string {
  try {
    return localStorage.getItem(tenantStorageKey) || 'demo';
  } catch {
    return 'demo';
  }
}

function storeTenantId(tenantId: string): void {
  try {
    localStorage.setItem(tenantStorageKey, tenantId);
  } catch {
    // ignore
  }
}

const AdminDashboard: React.FC = () => {
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info';
  }>({ open: false, message: '', severity: 'info' });

  const [tenantId, setTenantId] = useState(readTenantId());
  const [createTenantOpen, setCreateTenantOpen] = useState(false);
  const [newTenantId, setNewTenantId] = useState('');
  const [newTenantName, setNewTenantName] = useState('');

  const [createPolicyOpen, setCreatePolicyOpen] = useState(false);
  const [policyName, setPolicyName] = useState('Schema changes require approval');
  const [policyEnabled, setPolicyEnabled] = useState(true);
  const [policyIncidentTypes, setPolicyIncidentTypes] = useState('SCHEMA_CHANGE');
  const [policyMinConfidence, setPolicyMinConfidence] = useState(0);
  const [policyPlaybook, setPolicyPlaybook] = useState('Fix Schema Mismatch');
  const [policyRequireApproval, setPolicyRequireApproval] = useState(true);

  const tenantsQuery = useTenants({ limit: 200, offset: 0 });
  const createTenant = useCreateTenant();
  const deleteTenant = useDeleteTenant();

  const policiesQuery = usePolicies(false);
  const upsertPolicy = useUpsertPolicy();
  const deletePolicy = useDeletePolicy();

  const approvalsQuery = useApprovals();
  const approveRemediation = useApproveRemediation();
  const rejectRemediation = useRejectRemediation();

  const tenantOptions = useMemo(() => {
    return (tenantsQuery.data?.tenants || []).map((t) => t.id);
  }, [tenantsQuery.data]);

  const handleTenantSwitch = (nextTenantId: string) => {
    const trimmed = nextTenantId.trim();
    if (!trimmed) return;
    storeTenantId(trimmed);
    setTenantId(trimmed);
    setSnackbar({
      open: true,
      message: `Active tenant set to "${trimmed}". Refresh dashboard to view tenant-scoped data.`,
      severity: 'success',
    });
  };

  const handleCreateTenant = async () => {
    try {
      const result = await createTenant.mutateAsync({
        id: newTenantId.trim(),
        name: newTenantName.trim(),
        config: {},
        metadata: {},
      });
      setSnackbar({
        open: true,
        message: `Tenant created: ${result.id}`,
        severity: 'success',
      });
      setCreateTenantOpen(false);
      setNewTenantId('');
      setNewTenantName('');
    } catch (e: any) {
      setSnackbar({
        open: true,
        message: e?.response?.data?.detail || e?.message || 'Failed to create tenant',
        severity: 'error',
      });
    }
  };

  const handleDeleteTenant = async (id: string) => {
    try {
      await deleteTenant.mutateAsync({ tenantId: id, hardDelete: false });
      setSnackbar({ open: true, message: `Tenant deleted: ${id}`, severity: 'success' });
    } catch (e: any) {
      setSnackbar({
        open: true,
        message: e?.response?.data?.detail || e?.message || 'Failed to delete tenant',
        severity: 'error',
      });
    }
  };

  const handleCreatePolicy = async () => {
    try {
      const incidentTypes = policyIncidentTypes
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload = {
        name: policyName.trim(),
        enabled: Boolean(policyEnabled),
        match: {
          incident_types: incidentTypes,
          min_confidence: Number(policyMinConfidence) || 0,
        },
        action: {
          playbook: policyPlaybook.trim(),
          require_approval: Boolean(policyRequireApproval),
        },
      };

      const result = await upsertPolicy.mutateAsync(payload);
      setSnackbar({ open: true, message: `Policy saved: ${result.id}`, severity: 'success' });
      setCreatePolicyOpen(false);
    } catch (e: any) {
      setSnackbar({
        open: true,
        message: e?.response?.data?.detail || e?.message || 'Failed to save policy',
        severity: 'error',
      });
    }
  };

  const handleDeletePolicy = async (id: string) => {
    try {
      const result = await deletePolicy.mutateAsync(id);
      setSnackbar({
        open: true,
        message: result.success ? `Policy deleted: ${id}` : `Policy not found: ${id}`,
        severity: result.success ? 'success' : 'info',
      });
    } catch (e: any) {
      setSnackbar({
        open: true,
        message: e?.response?.data?.detail || e?.message || 'Failed to delete policy',
        severity: 'error',
      });
    }
  };

  const handleApprove = async (tokenId: string) => {
    try {
      const result = await approveRemediation.mutateAsync({
        token_id: tokenId,
        approver: 'demo-admin',
        comment: 'Approved via UI',
      });
      setSnackbar({ open: true, message: result.message, severity: 'success' });
    } catch (e: any) {
      setSnackbar({
        open: true,
        message: e?.response?.data?.detail || e?.message || 'Approval failed',
        severity: 'error',
      });
    }
  };

  const handleReject = async (tokenId: string) => {
    try {
      const result = await rejectRemediation.mutateAsync({
        token_id: tokenId,
        rejector: 'demo-admin',
        reason: 'Rejected via UI',
      });
      setSnackbar({ open: true, message: result.message, severity: 'success' });
    } catch (e: any) {
      setSnackbar({
        open: true,
        message: e?.response?.data?.detail || e?.message || 'Rejection failed',
        severity: 'error',
      });
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 2, md: 4 } }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1.25}>
          <IconButton component={RouterLink} to="/dashboard" aria-label="Back to dashboard">
            <ArrowBack />
          </IconButton>
          <Box>
            <Typography variant="h4" component="h1">
              Admin Console
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Tenants, automation policies, and remediation approvals
            </Typography>
          </Box>
        </Stack>
        <Chip label={`Active Tenant: ${tenantId}`} color="primary" variant="outlined" />
      </Stack>

      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 2.5 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1 }}>
                Tenant Context
              </Typography>
              <Typography variant="body2" color="text.secondary">
                All API reads and writes are scoped by `X-Tenant-ID`. Switching tenant changes what you see in the main dashboard.
              </Typography>

              <Divider sx={{ my: 2 }} />

              <Stack direction="row" spacing={1} alignItems="center">
                <TextField
                  label="Tenant ID"
                  size="small"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  helperText={tenantOptions.length ? `Known: ${tenantOptions.join(', ')}` : 'Enter a tenant id'}
                  fullWidth
                />
                <Button variant="contained" onClick={() => handleTenantSwitch(tenantId)} sx={{ whiteSpace: 'nowrap' }}>
                  Use
                </Button>
              </Stack>

              <Divider sx={{ my: 2 }} />

              <Button
                startIcon={<Add />}
                variant="outlined"
                onClick={() => setCreateTenantOpen(true)}
                fullWidth
              >
                Create Tenant
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 2.5 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">Tenants</Typography>
                <Chip size="small" label={`Total: ${tenantsQuery.data?.total ?? 0}`} />
              </Stack>

              {tenantsQuery.isError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  Failed to load tenants. Ensure your user is admin.
                </Alert>
              )}

              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Created</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(tenantsQuery.data?.tenants || []).map((t) => (
                    <TableRow key={t.id} hover>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{t.id}</TableCell>
                      <TableCell>{t.name}</TableCell>
                      <TableCell>{t.status}</TableCell>
                      <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
                      <TableCell align="right">
                        <Stack direction="row" justifyContent="flex-end" spacing={1}>
                          <Button size="small" variant="outlined" onClick={() => handleTenantSwitch(t.id)}>
                            Use
                          </Button>
                          <IconButton
                            size="small"
                            aria-label={`Delete tenant ${t.id}`}
                            onClick={() => handleDeleteTenant(t.id)}
                            disabled={deleteTenant.isPending}
                          >
                            <Delete fontSize="small" />
                          </IconButton>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!tenantsQuery.data?.tenants?.length && (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography variant="body2" color="text.secondary">
                          No tenants found.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={7}>
          <Card sx={{ borderRadius: 2.5 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">Automation Policies</Typography>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip size="small" label={`Count: ${policiesQuery.data?.count ?? 0}`} />
                  <Button startIcon={<Add />} variant="outlined" onClick={() => setCreatePolicyOpen(true)}>
                    New Policy
                  </Button>
                </Stack>
              </Stack>

              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Enabled</TableCell>
                    <TableCell>Match</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(policiesQuery.data?.policies || []).map((p) => (
                    <TableRow key={p.id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={700}>
                          {p.name}
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: 'monospace' }} color="text.secondary">
                          {p.id}
                        </Typography>
                      </TableCell>
                      <TableCell>{p.enabled ? 'Yes' : 'No'}</TableCell>
                      <TableCell>
                        <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                          {JSON.stringify(p.match)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                          {JSON.stringify(p.action)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <IconButton size="small" onClick={() => handleDeletePolicy(p.id)} aria-label="Delete policy">
                          <Delete fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!policiesQuery.data?.policies?.length && (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography variant="body2" color="text.secondary">
                          No policies yet.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={5}>
          <Card sx={{ borderRadius: 2.5 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">Pending Approvals</Typography>
                <Chip size="small" label={`Pending: ${approvalsQuery.data?.length ?? 0}`} />
              </Stack>

              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Approvals are created when a policy forces approval (or when a playbook requires approval).
              </Typography>

              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Token</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(approvalsQuery.data || []).map((a) => (
                    <TableRow key={a.token_id} hover>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{a.token_id}</TableCell>
                      <TableCell>{a.action}</TableCell>
                      <TableCell align="right">
                        <Stack direction="row" justifyContent="flex-end" spacing={1}>
                          <IconButton size="small" color="success" onClick={() => handleApprove(a.token_id)} aria-label="Approve">
                            <Check fontSize="small" />
                          </IconButton>
                          <IconButton size="small" color="error" onClick={() => handleReject(a.token_id)} aria-label="Reject">
                            <Close fontSize="small" />
                          </IconButton>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!approvalsQuery.data?.length && (
                    <TableRow>
                      <TableCell colSpan={3}>
                        <Typography variant="body2" color="text.secondary">
                          No pending approvals.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Dialog open={createTenantOpen} onClose={() => setCreateTenantOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Tenant</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Tenant ID"
              value={newTenantId}
              onChange={(e) => setNewTenantId(e.target.value)}
              placeholder="demo"
              helperText="Lowercase alphanumeric with hyphens recommended"
            />
            <TextField label="Name" value={newTenantName} onChange={(e) => setNewTenantName(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateTenantOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateTenant} disabled={createTenant.isPending}>
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={createPolicyOpen} onClose={() => setCreatePolicyOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New Policy</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Name" value={policyName} onChange={(e) => setPolicyName(e.target.value)} />
            <FormControlLabel
              control={<Switch checked={policyEnabled} onChange={(e) => setPolicyEnabled(e.target.checked)} />}
              label="Enabled"
            />
            <TextField
              label="Incident Types (comma-separated)"
              value={policyIncidentTypes}
              onChange={(e) => setPolicyIncidentTypes(e.target.value)}
              helperText='Example: "SCHEMA_CHANGE,ROW_COUNT_DROP"'
            />
            <TextField
              label="Min Confidence"
              type="number"
              value={policyMinConfidence}
              onChange={(e) => setPolicyMinConfidence(Number(e.target.value))}
            />
            <TextField
              label="Playbook"
              value={policyPlaybook}
              onChange={(e) => setPolicyPlaybook(e.target.value)}
              helperText="Must match an existing playbook name"
            />
            <FormControlLabel
              control={
                <Switch checked={policyRequireApproval} onChange={(e) => setPolicyRequireApproval(e.target.checked)} />
              }
              label="Require Approval"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreatePolicyOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreatePolicy} disabled={upsertPolicy.isPending}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={5000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default AdminDashboard;

