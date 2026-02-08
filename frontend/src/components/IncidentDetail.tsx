/**
 * IncidentDetail Component
 * Displays detailed information about a specific incident in a modal
 */
import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  Chip,
  Divider,
  CircularProgress,
  Grid,
  Paper,
  Stack,
} from '@mui/material';
import { useIncidentDetails } from '../hooks/useIncidents';
import { DecisionLogEntry, IncidentType } from '../types/models';

interface IncidentDetailProps {
  incidentId: string | null;
  open: boolean;
  onClose: () => void;
}

const IncidentDetail: React.FC<IncidentDetailProps> = ({ incidentId, open, onClose }) => {
  const { data: details, isLoading } = useIncidentDetails(incidentId);

  const getIncidentTypeColor = (type: IncidentType) => {
    switch (type) {
      case IncidentType.SCHEMA_CHANGE:
      case IncidentType.SCHEMA_EVOLUTION:
        return 'warning';
      case IncidentType.DATA_INTEGRITY_FAILURE:
      case IncidentType.ROW_COUNT_DROP:
        return 'error';
      case IncidentType.API_LATENCY_SPIKE:
      case IncidentType.UPSTREAM_DELAY:
        return 'info';
      case IncidentType.FRESHNESS_VIOLATION:
        return 'warning';
      case IncidentType.DISTRIBUTION_DRIFT:
        return 'primary';
      case IncidentType.PII_LEAKAGE:
        return 'error';
      default:
        return 'default';
    }
  };

  const formatStage = (stage: string) => {
    const normalized = String(stage || '').trim().toLowerCase();
    const map: Record<string, string> = {
      triage: 'Triage',
      reason: 'Reason',
      plan: 'Plan',
      verify: 'Verify',
      policy_suggest: 'Policy Suggestion',
      remediation_risk: 'Remediation Risk',
    };
    return map[normalized] || stage || 'Stage';
  };

  const renderDecisionLog = (entries: DecisionLogEntry[]) => {
    if (!entries || entries.length === 0) return null;

    return (
      <Box mb={2}>
        <Typography variant="subtitle2" gutterBottom>
          Reasoning Trace
        </Typography>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.25}>
            {entries.map((entry, idx) => {
              const meta = (entry?.meta || {}) as Record<string, any>;
              const ts = meta.timestamp as string | undefined;
              const provider = meta.provider as string | undefined;
              const model = meta.model_name as string | undefined;
              const cacheHit = Boolean(meta.cache_hit);
              const latencyMs =
                typeof meta.latency_ms === 'number' ? meta.latency_ms : undefined;
              const apiUsed = meta.api_used === false ? false : Boolean(meta.api_used);

              return (
                <Box
                  key={`${entry.stage || 'stage'}-${idx}`}
                  sx={{
                    borderLeft: '3px solid',
                    borderLeftColor: 'divider',
                    pl: 2,
                    py: 0.5,
                  }}
                >
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Chip size="small" label={formatStage(entry.stage)} />
                    {ts ? (
                      <Typography variant="caption" color="text.secondary">
                        {new Date(ts).toLocaleString()}
                      </Typography>
                    ) : null}
                    {provider ? (
                      <Chip size="small" variant="outlined" label={provider} />
                    ) : null}
                    {model ? (
                      <Chip size="small" variant="outlined" label={model} />
                    ) : null}
                    {cacheHit ? (
                      <Chip size="small" color="info" variant="outlined" label="cache" />
                    ) : null}
                    {latencyMs !== undefined ? (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${Math.round(latencyMs)}ms`}
                      />
                    ) : null}
                    {apiUsed ? (
                      <Chip size="small" color="success" variant="outlined" label="Gemini" />
                    ) : (
                      <Chip size="small" color="warning" variant="outlined" label="mock" />
                    )}
                  </Stack>

                  {entry?.summary ? (
                    <Typography variant="body2" sx={{ mt: 0.75 }}>
                      {entry.summary}
                    </Typography>
                  ) : null}

                  {/* Optional compact details for key stages (kept short for demo readability). */}
                  {entry.stage === 'triage' && entry.priority ? (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                      Priority: {String(entry.priority)}. Investigate: {String(entry.should_investigate ?? true)}.
                    </Typography>
                  ) : null}
                  {entry.stage === 'verify' && (entry.status || entry.confidence !== undefined) ? (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                      Status: {String(entry.status || 'N/A')}. Confidence: {typeof entry.confidence === 'number' ? `${entry.confidence.toFixed(1)}%` : 'N/A'}.
                    </Typography>
                  ) : null}
                  {entry.stage === 'remediation_risk' && entry.risk ? (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                      Risk: {typeof entry.risk?.risk_score === 'number' ? `${entry.risk.risk_score}/100` : 'N/A'}. Approval: {String(entry.risk?.require_approval ?? 'N/A')}.
                    </Typography>
                  ) : null}
                </Box>
              );
            })}
          </Stack>
        </Paper>
      </Box>
    );
  };

  return (
    <Dialog open= { open } onClose = { onClose } maxWidth = "md" fullWidth >
      <DialogTitle>
      <Box display="flex" justifyContent = "space-between" alignItems = "center" >
        <Typography variant="h6" > Incident Details </Typography>
  {
    details && (
      <Chip
              label={ details.incident_type }
    color = { getIncidentTypeColor(details.incident_type) }
      />
          )}
</Box>
  </DialogTitle>

  < DialogContent dividers >
    {
      isLoading?(
          <Box display = "flex" justifyContent = "center" alignItems = "center" minHeight = { 200} >
          <CircularProgress />
          </Box>
      ): details ? (
        <Box>
        <Grid container spacing = { 2} >
        {/* Basic Information */ }
        < Grid item xs = { 12} sm = { 6} >
        <Typography variant="body2" color = "text.secondary" >
        Report ID
        </Typography>
      < Typography variant = "body1" gutterBottom >
      { details.report_id }
      </Typography>
      </Grid>

      < Grid item xs = { 12} sm = { 6} >
      <Typography variant="body2" color = "text.secondary" >
      Cycle ID
      </Typography>
      < Typography variant = "body1" gutterBottom >
      { details.cycle_id }
      </Typography>
      </Grid>

      < Grid item xs = { 12} sm = { 6} >
      <Typography variant="body2" color = "text.secondary" >
      Confidence Score
      </Typography>
      < Chip
                  label = {`${details.final_confidence_score.toFixed(1)}%`}
        color = {
          details.final_confidence_score >= 90
            ? 'success'
            : details.final_confidence_score >= 70
              ? 'warning'
              : 'error'
        }
                  size = "small"
                  sx = {{ mt: 0.5 }}
                />
        </Grid>

        < Grid item xs = { 12} sm = { 6} >
        <Typography variant="body2" color = "text.secondary" >
        Verification Status
        </Typography>
      < Chip
                  label = {
          details.verification_result?.is_verified ? 'Verified' : 'Not Verified'
        }
                  color = { details.verification_result?.is_verified ? 'success' : 'warning' }
                  size = "small"
                  sx = {{ mt: 0.5 }}
                />
        </Grid>
        </Grid>

        < Divider sx = {{ my: 2 }} />

            {/* Hypothesis */ }
        < Box mb = { 2} >
        <Typography variant="subtitle2" gutterBottom >
        Hypothesis
        </Typography>
      < Paper variant = "outlined" sx = {{ p: 2, bgcolor: 'background.default' }}>
      <Typography variant="body2" > { details.hypothesis || 'N/A' } </Typography>
      </Paper>
      </Box>

            {/* Evidence & Runtime */}
            <Box mb={2}>
              <Typography variant="subtitle2" gutterBottom>
                Evidence & Runtime
              </Typography>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="caption" color="text.secondary">
                      LLM Provider
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {details.llm_provider || 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="caption" color="text.secondary">
                      LLM Model
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {details.llm_model || 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="caption" color="text.secondary">
                      Confidence Threshold
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {typeof details.confidence_threshold === 'number'
                        ? `${details.confidence_threshold.toFixed(1)}%`
                        : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="caption" color="text.secondary">
                      Trigger Signals
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                      {(details.trigger_signals || []).length > 0 ? (
                        details.trigger_signals!.slice(0, 6).map((signal, idx) => (
                          <Chip key={`${signal}-${idx}`} size="small" label={signal} />
                        ))
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          N/A
                        </Typography>
                      )}
                    </Stack>
                  </Grid>
                </Grid>
              </Paper>
            </Box>

            {/* Verification Result */ }
            {
          details.verification_result && (
            <Box mb={ 2} >
      <Typography variant="subtitle2" gutterBottom >
      Verification Summary
      </Typography>
      < Paper variant = "outlined" sx = {{ p: 2, bgcolor: 'background.default' }}>
      <Typography variant="body2" >
      { details.verification_result.summary || 'N/A' }
      </Typography>
                  {
          details.verification_result.verification_confidence && (
            <Box mt={ 1} >
      <Typography variant="caption" color = "text.secondary" >
      Verification Confidence: { ' '}
                        { details.verification_result.verification_confidence.toFixed(1) } %
        </Typography>
        </Box>
      )}
</Paper>
  </Box>
            )}

            {renderDecisionLog(details.decision_log || [])}

{/* Recommended Actions */ }
{
  details.recommended_actions && details.recommended_actions.length > 0 && (
    <Box mb={ 2 }>
      <Typography variant="subtitle2" gutterBottom >
        Recommended Actions
          </Typography>
          < Box display = "flex" flexDirection = "column" gap = { 1} >
          {
            details.recommended_actions.map((action, index) => (
              <Paper key= { index } variant = "outlined" sx = {{ p: 1.5 }} >
            <Typography variant="body2" > { action } </Typography>
              </Paper>
                  ))
}
</Box>
  </Box>
            )}

{/* Anomaly Evidence */ }
{
  details.anomaly_evidence && (
    <Box mb={ 2 }>
      <Typography variant="subtitle2" gutterBottom >
        Anomaly Evidence
          </Typography>
          < Paper variant = "outlined" sx = {{ p: 2, bgcolor: 'background.default' }
}>
  <pre
                    style={
  {
    margin: 0,
      fontSize: '0.75rem',
        overflow: 'auto',
          maxHeight: '200px',
                    }
}
                  >
  { JSON.stringify(details.anomaly_evidence, null, 2) }
  </pre>
  </Paper>
  </Box>
            )}
</Box>
        ) : (
  <Typography variant= "body1" color = "text.secondary" align = "center" >
    No details available
      </Typography>
        )}
</DialogContent>

  < DialogActions >
  <Button onClick={ onClose }> Close </Button>
    </DialogActions>
    </Dialog>
  );
};

export default IncidentDetail;
