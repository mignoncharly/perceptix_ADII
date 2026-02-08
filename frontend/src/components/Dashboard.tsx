import React, { useState } from 'react';
import {
  Container,
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  CircularProgress,
  Alert,
  Snackbar,
  Chip,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import { PlayArrow, BugReport, DeleteSweep } from '@mui/icons-material';
import { Link as RouterLink } from 'react-router-dom';
import SystemStatus from './SystemStatus';
import MetricsChart from './MetricsChart';
import IncidentList from './IncidentList';
import AgentActivityFeed from './AgentActivityFeed';
import { useMetrics, useDashboardSummary, useSystemConfig } from '../hooks/useMetrics';
import { useResetDemoData, useTriggerCycle } from '../hooks/useIncidents';
import IncidentTrends from './IncidentTrends';

const Dashboard: React.FC = () => {
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info';
  }>({ open: false, message: '', severity: 'info' });
  const [activeCycleAction, setActiveCycleAction] = useState<'run' | 'simulate' | null>(null);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);

  const { data: metrics } = useMetrics();
  const { data: summary } = useDashboardSummary();
  const { data: config } = useSystemConfig();
  const triggerCycle = useTriggerCycle();
  const resetDemoData = useResetDemoData();

  const kpiCards = [
    {
      title: 'System Health',
      value: `${summary?.system_health_score?.toFixed(0) ?? '100'}%`,
      subtitle: 'Overall quality signal',
      accent: '#0f766e',
      emphasis: 'positive',
    },
    {
      title: 'Active Incidents',
      value: `${summary?.active_incidents ?? 0}`,
      subtitle: summary?.critical_incidents
        ? `${summary.critical_incidents} critical`
        : 'No critical incidents',
      accent: '#b91c1c',
      emphasis: (summary?.active_incidents ?? 0) > 0 ? 'alert' : 'neutral',
    },
    {
      title: 'Agent Success',
      value: `${summary?.agent_success_rate?.toFixed(1) ?? '100.0'}%`,
      subtitle: 'Execution reliability',
      accent: '#166534',
      emphasis: 'positive',
    },
    {
      title: 'Total Cycles',
      value: `${metrics?.counters.cycles_total ?? 0}`,
      subtitle: 'Completed analysis cycles',
      accent: '#1d4ed8',
      emphasis: 'neutral',
    },
  ] as const;

  const handleTriggerCycle = async (action: 'run' | 'simulate') => {
    if (triggerCycle.isPending) return;
    setActiveCycleAction(action);
    const simulateFailure = action === 'simulate';

    try {
      const result = await triggerCycle.mutateAsync(simulateFailure);
      setSnackbar({
        open: true,
        message: result.message,
        severity: result.incident_detected ? 'error' : 'success',
      });
    } catch (error: any) {
      const isTimeout = error?.code === 'ECONNABORTED';
      const timeoutMessage =
        'Cycle request timed out on the client. The backend may still be processing. Please wait a few seconds and refresh.';
      const errorMessage = isTimeout
        ? timeoutMessage
        : error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        'Failed to trigger cycle - Unknown error';
      console.error('Trigger cycle error:', error);
      setSnackbar({
        open: true,
        message: errorMessage,
        severity: 'error',
      });
    } finally {
      setActiveCycleAction(null);
    }
  };

  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };

  const isCycleActionPending = triggerCycle.isPending;
  const runCycleLoading = isCycleActionPending && activeCycleAction === 'run';
  const simulateFailureLoading = isCycleActionPending && activeCycleAction === 'simulate';
  const isResetPending = resetDemoData.isPending;
  const isActionBusy = isCycleActionPending || isResetPending;

  const handleResetDemoData = async () => {
    try {
      const result = await resetDemoData.mutateAsync();
      setSnackbar({
        open: true,
        message: `${result.message} (incidents: ${result.incidents_deleted}, metrics: ${result.metrics_deleted})`,
        severity: 'success',
      });
      setResetDialogOpen(false);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to reset demo data';
      setSnackbar({
        open: true,
        message: errorMessage,
        severity: 'error',
      });
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 2, md: 4 } }}>
      <Card
        sx={{
          mb: 3,
          borderRadius: 3,
          color: 'common.white',
          background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          border: '1px solid rgba(148, 163, 184, 0.28)',
          boxShadow: '0 20px 45px rgba(15, 23, 42, 0.22)',
        }}
      >
        <CardContent
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', md: 'center' },
            flexWrap: 'wrap',
            gap: 2,
          }}
        >
          <Box>
            <Typography variant="h4" component="h1" fontWeight={700}>
              Perceptix Control Center
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.85, mt: 0.75 }}>
              Real-time reliability monitoring with autonomous incident triage
            </Typography>
            <Box sx={{ mt: 1.25 }}>
              <Chip
                size="small"
                label={`Mode: ${config?.system.mode ?? 'SYNCING'}`}
                sx={{
                  color: 'white',
                  bgcolor: 'rgba(148, 163, 184, 0.18)',
                  border: '1px solid rgba(148, 163, 184, 0.35)',
                }}
              />
            </Box>
          </Box>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
            <Button
              component={RouterLink}
              to="/admin"
              variant="outlined"
              sx={{
                borderWidth: 1.5,
                minWidth: 120,
                color: 'rgba(255, 255, 255, 0.9)',
                borderColor: 'rgba(148, 163, 184, 0.55)',
                '&:hover': {
                  borderColor: 'rgba(148, 163, 184, 0.85)',
                  bgcolor: 'rgba(148, 163, 184, 0.08)',
                },
              }}
            >
              Admin
            </Button>
            <Button
              variant="contained"
              color="success"
              startIcon={runCycleLoading ? <CircularProgress size={18} color="inherit" /> : <PlayArrow />}
              onClick={() => handleTriggerCycle('run')}
              disabled={isActionBusy}
              sx={{
                minWidth: 140,
                '&.Mui-disabled': {
                  bgcolor: 'success.dark',
                  color: 'rgba(255, 255, 255, 0.78)',
                  opacity: 1,
                },
              }}
            >
              {runCycleLoading ? 'Running...' : 'Run Cycle'}
            </Button>
            <Button
              variant="outlined"
              color="warning"
              startIcon={simulateFailureLoading ? <CircularProgress size={18} color="inherit" /> : <BugReport />}
              onClick={() => handleTriggerCycle('simulate')}
              disabled={isActionBusy}
              sx={{
                borderWidth: 1.5,
                minWidth: 170,
                '&.Mui-disabled': {
                  borderColor: 'warning.main',
                  color: 'rgba(255, 255, 255, 0.78)',
                  opacity: 1,
                },
              }}
            >
              {simulateFailureLoading ? 'Simulating...' : 'Simulate Failure'}
            </Button>
            <Button
              variant="outlined"
              color="error"
              startIcon={isResetPending ? <CircularProgress size={18} color="inherit" /> : <DeleteSweep />}
              onClick={() => setResetDialogOpen(true)}
              disabled={isActionBusy}
              sx={{ borderWidth: 1.5, minWidth: 170 }}
            >
              {isResetPending ? 'Resetting...' : 'Reset Demo Data'}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <SystemStatus />
        </Grid>

        {kpiCards.map((kpi) => (
          <Grid item xs={12} sm={6} lg={3} key={kpi.title}>
            <Card
              sx={{
                height: '100%',
                minHeight: 136,
                borderRadius: 2.5,
                border: '1px solid',
                borderColor: 'divider',
                boxShadow: '0 10px 20px rgba(15, 23, 42, 0.06)',
              }}
            >
              <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Typography
                  variant="caption"
                  sx={{
                    textTransform: 'uppercase',
                    letterSpacing: 1,
                    color: 'text.secondary',
                    fontWeight: 700,
                  }}
                >
                  {kpi.title}
                </Typography>
                <Typography
                  variant="h3"
                  sx={{
                    fontWeight: 800,
                    lineHeight: 1.05,
                    color: kpi.emphasis === 'alert' ? 'error.main' : 'text.primary',
                  }}
                >
                  {kpi.value}
                </Typography>
                <Box sx={{ mt: 'auto', pt: 0.5 }}>
                  <Typography variant="body2" color="text.secondary">
                    {kpi.subtitle}
                  </Typography>
                  <Box
                    sx={{
                      mt: 1.1,
                      width: 42,
                      height: 4,
                      borderRadius: 999,
                      bgcolor: kpi.accent,
                    }}
                  />
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}

        <Grid item xs={12} lg={8}>
          <Stack spacing={3}>
            <IncidentTrends days={7} />
            <MetricsChart visualizationType="bar" />
          </Stack>
        </Grid>

        <Grid item xs={12} lg={4}>
          <AgentActivityFeed />
        </Grid>

        <Grid item xs={12}>
          <IncidentList />
        </Grid>
      </Grid>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity} variant="filled" sx={{ width: '100%' }}>
          {snackbar.message}
        </Alert>
      </Snackbar>

      <Dialog open={resetDialogOpen} onClose={() => setResetDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Reset Demo Data</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            This will permanently delete all incidents and metric history, then reset counters to zero.
            Use this only for demo retakes.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetDialogOpen(false)} disabled={isResetPending}>
            Cancel
          </Button>
          <Button
            onClick={() => void handleResetDemoData()}
            color="error"
            variant="contained"
            disabled={isResetPending}
            startIcon={isResetPending ? <CircularProgress size={16} color="inherit" /> : <DeleteSweep />}
          >
            Confirm Reset
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Dashboard;
