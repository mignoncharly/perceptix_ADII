/**
 * IncidentList Component
 * Displays a list of incidents with filtering and pagination
 */
import React, { useMemo, useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Chip,
  Box,
  CircularProgress,
  IconButton,
  Tooltip,
  Stack,
  Divider,
  Checkbox,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar,
  Alert,
  Fade,
} from '@mui/material';
import {
  Visibility,
  Refresh,
  ArchiveOutlined,
  DeleteOutline,
  WarningAmberRounded,
} from '@mui/icons-material';
import { format } from 'date-fns';
import {
  useArchiveIncident,
  useBulkArchiveIncidents,
  useBulkDeleteIncidents,
  useDeleteIncident,
  useIncidents,
} from '../hooks/useIncidents';
import { IncidentType } from '../types/models';
import IncidentDetail from './IncidentDetail';

const IncidentList: React.FC = () => {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(8);
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);
  const [selectedIncidentIds, setSelectedIncidentIds] = useState<string[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [actionNoticeOpen, setActionNoticeOpen] = useState(false);
  const [actionNoticeMessage, setActionNoticeMessage] = useState('');
  const [actionNoticeSeverity, setActionNoticeSeverity] = useState<'success' | 'error' | 'info'>('success');
  const [showArchiveShortcut, setShowArchiveShortcut] = useState(false);
  const [confirmDeleteState, setConfirmDeleteState] = useState<{
    open: boolean;
    mode: 'single' | 'bulk';
    incidentId?: string;
    count: number;
  }>({
    open: false,
    mode: 'single',
    count: 0,
  });

  const { data, isLoading, refetch, isFetching } = useIncidents(
    100,
    showArchived ? { include_archived: true, status_filter: 'ARCHIVED' } : {}
  );
  const archiveIncident = useArchiveIncident();
  const deleteIncident = useDeleteIncident();
  const bulkArchiveIncidents = useBulkArchiveIncidents();
  const bulkDeleteIncidents = useBulkDeleteIncidents();

  const isActionPending =
    archiveIncident.isPending ||
    deleteIncident.isPending ||
    bulkArchiveIncidents.isPending ||
    bulkDeleteIncidents.isPending;

  const incidents = data?.incidents || [];
  const paginatedIncidents = incidents.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  const paginatedIncidentIds = useMemo(
    () => paginatedIncidents.map((incident) => incident.id),
    [paginatedIncidents]
  );
  const selectedOnPageCount = useMemo(
    () => paginatedIncidentIds.filter((id) => selectedIncidentIds.includes(id)).length,
    [paginatedIncidentIds, selectedIncidentIds]
  );

  const getErrorMessage = (error: unknown, fallback: string): string => {
    const e = error as {
      response?: { data?: { detail?: string; message?: string } };
      message?: string;
    };
    return e?.response?.data?.detail || e?.response?.data?.message || e?.message || fallback;
  };

  const showNotice = (
    message: string,
    severity: 'success' | 'error' | 'info' = 'success',
    archiveShortcut: boolean = false
  ) => {
    setActionNoticeMessage(message);
    setActionNoticeSeverity(severity);
    setShowArchiveShortcut(archiveShortcut);
    setActionNoticeOpen(true);
  };

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleViewDetails = (incidentId: string) => {
    setSelectedIncident(incidentId);
  };

  const handleCloseDetails = () => {
    setSelectedIncident(null);
  };

  const toggleSelectIncident = (incidentId: string) => {
    setSelectedIncidentIds((prev) => {
      if (prev.includes(incidentId)) {
        return prev.filter((id) => id !== incidentId);
      }
      return [...prev, incidentId];
    });
  };

  const toggleSelectCurrentPage = () => {
    setSelectedIncidentIds((prev) => {
      const next = new Set(prev);
      const allSelected =
        paginatedIncidentIds.length > 0 &&
        paginatedIncidentIds.every((incidentId) => next.has(incidentId));

      if (allSelected) {
        paginatedIncidentIds.forEach((incidentId) => next.delete(incidentId));
      } else {
        paginatedIncidentIds.forEach((incidentId) => next.add(incidentId));
      }

      return Array.from(next);
    });
  };

  const handleArchiveIncident = async (incidentId: string) => {
    try {
      await archiveIncident.mutateAsync(incidentId);
      setSelectedIncidentIds((prev) => prev.filter((id) => id !== incidentId));
      showNotice('Incident archived successfully.', 'success', true);
    } catch (error) {
      console.error('Failed to archive incident:', error);
      showNotice(getErrorMessage(error, 'Failed to archive incident.'), 'error');
    }
  };

  const handleOpenDeleteIncidentDialog = (incidentId: string) => {
    setConfirmDeleteState({
      open: true,
      mode: 'single',
      incidentId,
      count: 1,
    });
  };

  const handleBulkArchive = async () => {
    if (selectedIncidentIds.length === 0) {
      return;
    }
    try {
      await bulkArchiveIncidents.mutateAsync(selectedIncidentIds);
      setSelectedIncidentIds([]);
      showNotice(`${selectedIncidentIds.length} incidents archived successfully.`, 'success', true);
    } catch (error) {
      console.error('Failed to bulk archive incidents:', error);
      showNotice(getErrorMessage(error, 'Failed to archive selected incidents.'), 'error');
    }
  };

  const handleOpenBulkDeleteDialog = () => {
    if (selectedIncidentIds.length === 0) {
      return;
    }
    setConfirmDeleteState({
      open: true,
      mode: 'bulk',
      count: selectedIncidentIds.length,
    });
  };

  const handleCloseDeleteDialog = () => {
    setConfirmDeleteState({
      open: false,
      mode: 'single',
      count: 0,
    });
  };

  const handleConfirmDelete = async () => {
    try {
      if (confirmDeleteState.mode === 'single' && confirmDeleteState.incidentId) {
        const deletedIncidentId = confirmDeleteState.incidentId;
        await deleteIncident.mutateAsync(deletedIncidentId);
        setSelectedIncidentIds((prev) =>
          prev.filter((id) => id !== deletedIncidentId)
        );
        if (selectedIncident === deletedIncidentId) {
          setSelectedIncident(null);
        }
        showNotice('Incident deleted permanently.', 'success');
      } else if (confirmDeleteState.mode === 'bulk') {
        const deleteCount = selectedIncidentIds.length;
        await bulkDeleteIncidents.mutateAsync(selectedIncidentIds);
        setSelectedIncidentIds([]);
        showNotice(`${deleteCount} incidents deleted permanently.`, 'success');
      }
      handleCloseDeleteDialog();
    } catch (error) {
      console.error('Failed to delete incidents:', error);
      showNotice(getErrorMessage(error, 'Failed to delete incidents.'), 'error');
    }
  };

  const handleSwitchArchivedView = () => {
    setShowArchived((prev) => !prev);
    setPage(0);
    setSelectedIncidentIds([]);
  };

  const handleOpenArchivedFromNotice = () => {
    setShowArchived(true);
    setPage(0);
    setSelectedIncidentIds([]);
    setActionNoticeOpen(false);
  };

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

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 90) return 'success';
    if (confidence >= 70) return 'warning';
    return 'error';
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" minHeight={320}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card
        sx={{
          borderRadius: 2.5,
          border: '1px solid',
          borderColor: 'divider',
          boxShadow: '0 10px 20px rgba(15, 23, 42, 0.05)',
        }}
      >
        <CardContent sx={{ pb: 0 }}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={1.75}>
            <Stack spacing={0.25}>
              <Typography variant="h6">
                {showArchived ? 'Archived Incidents' : 'Recent Incidents'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {showArchived
                  ? 'Historical incidents moved out of active monitoring'
                  : 'Latest detection results and confidence signals'}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                variant={showArchived ? 'contained' : 'outlined'}
                color={showArchived ? 'warning' : 'inherit'}
                onClick={handleSwitchArchivedView}
                disabled={isActionPending}
              >
                {showArchived ? 'Back To Active' : 'View Archived'}
              </Button>
              <Tooltip title="Refresh">
                <span>
                  <IconButton onClick={() => refetch()} disabled={isFetching || isActionPending}>
                    <Refresh />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          </Box>

          <Divider sx={{ mb: 1.5 }} />

          {selectedIncidentIds.length > 0 && (
            <Box
              sx={{
                mb: 1.5,
                p: 1.25,
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1.5,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 1.25,
                flexWrap: 'wrap',
              }}
            >
              <Typography variant="body2">
                {selectedIncidentIds.length} selected
              </Typography>
              <Stack direction="row" spacing={1}>
                {!showArchived && (
                  <Button
                    size="small"
                    variant="outlined"
                    color="warning"
                    startIcon={<ArchiveOutlined fontSize="small" />}
                    onClick={handleBulkArchive}
                    disabled={isActionPending}
                  >
                    Archive Selected
                  </Button>
                )}
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteOutline fontSize="small" />}
                  onClick={handleOpenBulkDeleteDialog}
                  disabled={isActionPending}
                >
                  Delete Selected
                </Button>
                <Button
                  size="small"
                  variant="text"
                  onClick={() => setSelectedIncidentIds([])}
                  disabled={isActionPending}
                >
                  Clear
                </Button>
              </Stack>
            </Box>
          )}

          <TableContainer sx={{ maxHeight: 460, overflowY: 'auto' }}>
            <Table stickyHeader sx={{ tableLayout: 'fixed' }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 52, px: 1 }}>
                    <Checkbox
                      size="small"
                      checked={
                        paginatedIncidentIds.length > 0 &&
                        selectedOnPageCount === paginatedIncidentIds.length
                      }
                      indeterminate={
                        selectedOnPageCount > 0 &&
                        selectedOnPageCount < paginatedIncidentIds.length
                      }
                      onChange={toggleSelectCurrentPage}
                      disabled={paginatedIncidentIds.length === 0 || isActionPending}
                    />
                  </TableCell>
                  <TableCell sx={{ width: 190 }}>Timestamp</TableCell>
                  <TableCell sx={{ width: 180 }}>Type</TableCell>
                  <TableCell sx={{ width: 130 }}>Confidence</TableCell>
                  <TableCell>Summary</TableCell>
                  <TableCell align="right" sx={{ width: 140 }}>
                    Actions
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginatedIncidents.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
                      <Typography variant="body2" color="text.secondary">
                        {showArchived ? 'No archived incidents found' : 'No incidents found'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  paginatedIncidents.map((incident) => (
                    <TableRow
                      key={incident.id}
                      hover
                      sx={{ cursor: 'pointer' }}
                      onClick={() => handleViewDetails(incident.id)}
                    >
                      <TableCell sx={{ px: 1, verticalAlign: 'top' }}>
                        <Checkbox
                          size="small"
                          checked={selectedIncidentIds.includes(incident.id)}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => toggleSelectIncident(incident.id)}
                          disabled={isActionPending}
                        />
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        {format(new Date(incident.timestamp), 'MMM dd, yyyy HH:mm')}
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        <Chip
                          label={incident.type}
                          color={getIncidentTypeColor(incident.type)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        <Chip
                          label={`${incident.confidence.toFixed(1)}%`}
                          color={getConfidenceColor(incident.confidence)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell sx={{ verticalAlign: 'top' }}>
                        <Tooltip title={incident.summary} placement="top-start">
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: 'normal',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              lineHeight: 1.45,
                            }}
                          >
                            {incident.summary}
                          </Typography>
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right" sx={{ verticalAlign: 'top' }}>
                        <Tooltip title="View Details">
                          <span>
                            <IconButton
                              size="small"
                              onClick={(event) => {
                                event.stopPropagation();
                                handleViewDetails(incident.id);
                              }}
                              disabled={isActionPending}
                            >
                              <Visibility fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        {!showArchived && (
                          <Tooltip title="Archive">
                            <span>
                              <IconButton
                                size="small"
                                color="warning"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleArchiveIncident(incident.id);
                                }}
                                disabled={isActionPending}
                              >
                                <ArchiveOutlined fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        )}
                        <Tooltip title="Delete Permanently">
                          <span>
                            <IconButton
                              size="small"
                              color="error"
                              onClick={(event) => {
                                event.stopPropagation();
                                handleOpenDeleteIncidentDialog(incident.id);
                              }}
                              disabled={isActionPending}
                            >
                              <DeleteOutline fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>

          <TablePagination
            rowsPerPageOptions={[5, 8, 15, 25]}
            component="div"
            count={incidents.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
          />
        </CardContent>
      </Card>

      <Dialog
        open={confirmDeleteState.open}
        onClose={handleCloseDeleteDialog}
        TransitionComponent={Fade}
        maxWidth="xs"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            border: '1px solid',
            borderColor: 'error.light',
            boxShadow: '0 24px 60px rgba(15, 23, 42, 0.25)',
            background:
              'linear-gradient(170deg, rgba(255,255,255,1) 0%, rgba(254,242,242,0.95) 100%)',
          },
        }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Stack direction="row" alignItems="center" spacing={1.25}>
            <WarningAmberRounded color="error" />
            <Typography variant="h6" fontWeight={700}>
              Confirm Permanent Deletion
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent sx={{ pt: '8px !important' }}>
          <Typography variant="body2" color="text.secondary">
            {confirmDeleteState.mode === 'bulk'
              ? `This will permanently delete ${confirmDeleteState.count} incidents. This action cannot be undone.`
              : 'This incident will be permanently deleted and cannot be recovered.'}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, pt: 1 }}>
          <Button onClick={handleCloseDeleteDialog} variant="outlined" color="inherit">
            Cancel
          </Button>
          <Button
            onClick={() => void handleConfirmDelete()}
            variant="contained"
            color="error"
            disabled={isActionPending}
            startIcon={<DeleteOutline fontSize="small" />}
          >
            Delete Permanently
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={actionNoticeOpen}
        autoHideDuration={5500}
        onClose={() => setActionNoticeOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity={actionNoticeSeverity}
          variant="filled"
          onClose={() => setActionNoticeOpen(false)}
          action={showArchiveShortcut ? (
            <Button color="inherit" size="small" onClick={handleOpenArchivedFromNotice}>
              View Archived
            </Button>
          ) : undefined}
          sx={{ alignItems: 'center' }}
        >
          {actionNoticeMessage}
        </Alert>
      </Snackbar>

      <IncidentDetail
        incidentId={selectedIncident}
        open={!!selectedIncident}
        onClose={handleCloseDetails}
      />
    </>
  );
};

export default IncidentList;
