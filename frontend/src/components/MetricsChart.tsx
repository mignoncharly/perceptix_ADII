/**
 * MetricsChart Component
 * Displays metrics data using charts
 */
import React, { useMemo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  SelectChangeEvent,
} from '@mui/material';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useMetrics } from '../hooks/useMetrics';

type ChartType = 'cycles' | 'confidence' | 'alerts';
type VisualizationType = 'line' | 'bar';

interface MetricsChartProps {
  chartType?: ChartType;
  visualizationType?: VisualizationType;
}

const MetricsChart: React.FC<MetricsChartProps> = ({
  chartType: initialChartType = 'cycles',
  visualizationType = 'line',
}) => {
  const [chartType, setChartType] = React.useState<ChartType>(initialChartType);
  const { data: metrics, isLoading } = useMetrics();

  const handleChartTypeChange = (event: SelectChangeEvent) => {
    setChartType(event.target.value as ChartType);
  };

  const chartData = useMemo(() => {
    if (!metrics) return [];

    // Convert metrics data to chart format
    // This is a simplified example - in production, you'd want more sophisticated data transformation
    switch (chartType) {
      case 'cycles':
        return [
          { name: 'Total Cycles', value: metrics.counters.cycles_total || 0 },
          { name: 'Anomalies', value: metrics.counters.anomalies_detected || 0 },
          { name: 'Hypotheses', value: metrics.counters.hypotheses_generated || 0 },
        ];
      case 'confidence':
        return [
          { name: 'Average', value: metrics.gauges.confidence_avg || 0 },
          { name: 'Min', value: metrics.gauges.confidence_min || 0 },
          { name: 'Max', value: metrics.gauges.confidence_max || 0 },
        ];
      case 'alerts':
        return [
          { name: 'Alerts Sent', value: metrics.counters.alerts_sent || 0 },
          { name: 'Critical', value: metrics.counters.alerts_critical || 0 },
          { name: 'Warnings', value: metrics.counters.alerts_warning || 0 },
        ];
      default:
        return [];
    }
  }, [metrics, chartType]);

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">Metrics Visualization</Typography>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Metric Type</InputLabel>
            <Select value={chartType} label="Metric Type" onChange={handleChartTypeChange}>
              <MenuItem value="cycles">Cycles</MenuItem>
              <MenuItem value="confidence">Confidence</MenuItem>
              <MenuItem value="alerts">Alerts</MenuItem>
            </Select>
          </FormControl>
        </Box>

        <ResponsiveContainer width="100%" height={300}>
          {visualizationType === 'line' ? (
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#8884d8"
                strokeWidth={2}
                activeDot={{ r: 8 }}
              />
            </LineChart>
          ) : (
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="value" fill="#8884d8" />
            </BarChart>
          )}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
};

export default MetricsChart;
