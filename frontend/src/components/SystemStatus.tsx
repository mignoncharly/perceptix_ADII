/**
 * SystemStatus Component
 * Displays system health indicators and status
 */
import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  CircularProgress,
  Box,
  Stack,
  Tooltip,
} from '@mui/material';
import {
  CheckCircle,
  Error,
  Warning,
  Info,
} from '@mui/icons-material';
import { useHealth, useSystemConfig, useCycleStatus, useGeminiProof } from '../hooks/useMetrics';
import { SystemMode } from '../types/models';

const SystemStatus: React.FC = () => {
  const { data: health, isLoading: healthLoading } = useHealth();
  const { data: config, isLoading: configLoading } = useSystemConfig();
  const { data: cycleStatus, isLoading: cycleLoading } = useCycleStatus();
  const { data: geminiProof } = useGeminiProof();

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy':
      case 'ready':
      case 'up':
        return <CheckCircle color="success" />;
      case 'down':
      case 'error':
        return <Error color="error" />;
      case 'warning':
        return <Warning color="warning" />;
      default:
        return <Info color="info" />;
    }
  };

  const getModeColor = (mode: SystemMode) => {
    switch (mode) {
      case SystemMode.PRODUCTION:
        return 'error';
      case SystemMode.DEMO:
        return 'warning';
      case SystemMode.MOCK:
        return 'info';
      default:
        return 'default';
    }
  };

  const channelSet = new Set((config?.notification.channels || []).map((c) => c.toLowerCase()));
  const showChannelsSection =
    channelSet.size > 0 ||
    !!config?.notification.slack_configured ||
    !!config?.notification.email_configured;
  const confidenceThreshold = config?.system.confidence_threshold ?? 85;
  const thresholdTip = `Perceptix sends alerts only when confidence meets threshold (currently ${confidenceThreshold}).`;

  if (healthLoading || configLoading || cycleLoading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" minHeight={200}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          System Status
        </Typography>

        <Grid container spacing={2}>
          {/* Overall Status */}
          <Grid item xs={12} sm={6} md={3}>
            <Box display="flex" alignItems="center" gap={1}>
              {getStatusIcon(health?.status || 'unknown')}
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Overall
                </Typography>
                <Typography variant="body1">
                  {health?.status || 'Unknown'}
                </Typography>
              </Box>
            </Box>
          </Grid>

          {/* System Mode */}
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="body2" color="text.secondary">
                Mode
              </Typography>
              <Chip
                label={config?.system.mode || 'Unknown'}
                color={getModeColor(config?.system.mode as SystemMode)}
                size="small"
                sx={{ mt: 0.5 }}
              />
            </Box>
          </Grid>

          {/* Cycle Progress */}
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="body2" color="text.secondary">
                Cycles
              </Typography>
              <Typography variant="body1">
                {cycleStatus?.total_cycles || 0} / {cycleStatus?.max_cycles || 0}
              </Typography>
            </Box>
          </Grid>

          {/* Version */}
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="body2" color="text.secondary">
                Version
              </Typography>
              <Typography variant="body1">
                {health?.version || 'Unknown'}
              </Typography>
            </Box>
          </Grid>

          {/* Components Status */}
          <Grid item xs={12}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Components
            </Typography>
            <Box display="flex" gap={1} flexWrap="wrap">
              {health?.components &&
                Object.entries(health.components).map(([name, status]) => (
                  <Chip
                    key={name}
                    icon={getStatusIcon(status)}
                    label={`${name}: ${status}`}
                    size="small"
                    variant="outlined"
                  />
                ))}
            </Box>
          </Grid>

          {/* Gemini Runtime */}
          {geminiProof && (
            <Grid item xs={12}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Gemini Runtime
              </Typography>
              <Box display="flex" gap={1} flexWrap="wrap">
                <Chip
                  label={`Model: ${geminiProof.configured_model}`}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={`Provider: ${geminiProof.provider}`}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  icon={getStatusIcon(geminiProof.reasoning_path)}
                  label={`Path: ${geminiProof.reasoning_path}`}
                  size="small"
                  variant="outlined"
                  color={geminiProof.reasoning_path === 'api' ? 'success' : 'warning'}
                />
              </Box>
            </Grid>
          )}

          {/* Notification Channels */}
          {showChannelsSection && (
            <Grid item xs={12}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Alert Channels
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Tooltip
                  title={
                    config?.notification.email_configured
                      ? `${thresholdTip} Email delivery is enabled via SMTP settings.`
                      : channelSet.has('email')
                        ? 'Email channel is enabled, but SMTP settings are incomplete.'
                        : 'Email channel is not configured.'
                  }
                  arrow
                >
                  <Chip
                    size="small"
                    variant="outlined"
                    label={
                      config?.notification.email_configured
                        ? 'Email'
                        : channelSet.has('email')
                          ? 'Email (Config Missing)'
                          : 'Email (Not Configured)'
                    }
                    color={config?.notification.email_configured ? 'success' : 'warning'}
                  />
                </Tooltip>
                <Chip
                  size="small"
                  variant="outlined"
                  label={config?.notification.slack_configured ? 'Slack' : 'Slack (Not Configured)'}
                  color={config?.notification.slack_configured ? 'success' : 'default'}
                />
                {config?.notification.channels
                  ?.filter((channel) => !['email', 'slack', 'pagerduty'].includes(channel.toLowerCase()))
                  .map((channel) => (
                    <Chip
                      key={channel}
                      label={channel}
                      size="small"
                      color="primary"
                      variant="outlined"
                    />
                  ))}
              </Stack>
            </Grid>
          )}
        </Grid>
      </CardContent>
    </Card>
  );
};

export default SystemStatus;
