/**
 * IncidentTrends Component
 * Shows real incident volume trends and MTTR derived from persisted incident history.
 */
import React, { useMemo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Stack,
  Chip,
  Divider,
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { useDashboardTrends } from '../hooks/useMetrics';

const formatMinutes = (value: number | null) => {
  if (value === null || Number.isNaN(value)) return 'N/A';
  if (value < 1) return '<1m';
  if (value < 60) return `${Math.round(value)}m`;
  const hours = value / 60;
  return `${hours.toFixed(1)}h`;
};

const IncidentTrends: React.FC<{ days?: number }> = ({ days = 7 }) => {
  const { data, isLoading } = useDashboardTrends(days);

  const chartData = useMemo(() => {
    return (data?.timeline || []).map((p) => ({
      date: p.date.slice(5), // MM-DD for compact axis
      detected: p.detected,
      archived: p.archived,
    }));
  }, [data]);

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" minHeight={260}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  const mttrAvg = data?.mttr_minutes_avg ?? null;
  const mttrP95 = data?.mttr_minutes_p95 ?? null;
  const archivedSamples = data?.archived_sample_count ?? 0;
  const totalWindow = data?.incidents_total_window ?? 0;

  return (
    <Card
      sx={{
        borderRadius: 2.5,
        border: '1px solid',
        borderColor: 'divider',
        boxShadow: '0 10px 20px rgba(15, 23, 42, 0.05)',
      }}
    >
      <CardContent>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          justifyContent="space-between"
          spacing={1}
          sx={{ mb: 1.25 }}
        >
          <Box>
            <Typography variant="h6">Incident Trends</Typography>
            <Typography variant="body2" color="text.secondary">
              Derived from persisted incident history (last {days} days)
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={`Incidents: ${totalWindow}`} />
            <Chip size="small" label={`MTTR avg: ${formatMinutes(mttrAvg)}`} />
            <Chip size="small" label={`MTTR p95: ${formatMinutes(mttrP95)}`} />
          </Stack>
        </Stack>

        <Divider sx={{ mb: 1.75 }} />

        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="detected" stroke="#1d4ed8" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="archived" stroke="#b45309" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>

        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          MTTR is computed only from archived incidents ({archivedSamples} samples).
        </Typography>
      </CardContent>
    </Card>
  );
};

export default IncidentTrends;

