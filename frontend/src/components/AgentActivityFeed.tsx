import React, { useEffect, useState, useRef } from 'react';
import {
    Card,
    CardContent,
    Typography,
    List,
    ListItem,
    ListItemText,
    ListItemIcon,
    Box,
    Divider,
} from '@mui/material';
import {
    Info,
    Error as ErrorIcon,
    Update,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { useQueryClient } from '@tanstack/react-query';

interface ActivityEvent {
    type: string;
    data: any;
    timestamp: string;
}

const AgentActivityFeed: React.FC = () => {
    const [events, setEvents] = useState<ActivityEvent[]>([]);
    const ws = useRef<WebSocket | null>(null);
    const queryClient = useQueryClient();

    useEffect(() => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname;
        const port = window.location.port ? `:${window.location.port}` : '';

        // Use import.meta.env.MODE for Vite environment
        const isDev = import.meta.env.MODE === 'development';
        const wsUrl = isDev
            ? `ws://localhost:8000/ws/incidents`
            : `${protocol}//${host}${port}/ws/incidents`;

        const tenantId =
            localStorage.getItem('perceptix_tenant_id') ||
            import.meta.env.VITE_TENANT_ID ||
            'demo';
        ws.current = new WebSocket(`${wsUrl}?tenant_id=${encodeURIComponent(tenantId)}`);

        ws.current.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                // When a cycle completes (or an incident is detected), refresh dashboard data immediately.
                // This avoids requiring a hard page refresh during recordings.
                const msgType = String(message?.type || '');
                if (['incident_detected', 'cycle_completed', 'cycle_error'].includes(msgType)) {
                    queryClient.invalidateQueries({ queryKey: ['incidents'] });
                    queryClient.invalidateQueries({ queryKey: ['metrics'] });
                    queryClient.invalidateQueries({ queryKey: ['dashboardSummary'] });
                    queryClient.invalidateQueries({ queryKey: ['dashboardTrends'] });
                    queryClient.invalidateQueries({ queryKey: ['cycleStatus'] });
                }
                setEvents((prev) => [
                    {
                        type: message.type,
                        data: message.data,
                        timestamp: message.timestamp || new Date().toISOString(),
                    },
                    ...prev.slice(0, 49),
                ]);
            } catch (err) {
                console.error('Failed to parse WebSocket message:', err);
            }
        };

        ws.current.onerror = (err) => {
            console.error('WebSocket error:', err);
        };

        return () => {
            if (ws.current) {
                ws.current.close();
            }
        };
    }, []);

    const getEventIcon = (type: string) => {
        switch (type) {
            case 'incident_detected':
                return <ErrorIcon color="error" />;
            case 'cycle_started':
                return <Update color="primary" />;
            case 'system_status':
                return <Info color="info" />;
            default:
                return <Info color="action" />;
        }
    };

    return (
        <Card sx= {{ height: '100%', display: 'flex', flexDirection: 'column' }
}>
    <CardContent sx={ { pb: 1 } }>
        <Typography variant="h6" gutterBottom >
            Live Agent Activity
                </Typography>
                </CardContent>
                < Divider />
                <Box sx={ { flexGrow: 1, overflowY: 'auto', maxHeight: 600 } }>
                    {
                        events.length === 0 ? (
                            <Box display= "flex" justifyContent="center" alignItems="center" p={ 4} >
                            <Typography variant="body2" color = "text.secondary" >
                                Waiting for activity...
                        </Typography>
                        </Box>
        ) : (
                            <List dense >
                            {
                                events.map((event, index) => (
                                    <React.Fragment key= { index } >
                                    <ListItem alignItems="flex-start" >
                                <ListItemIcon sx={{ minWidth: 40, mt: 0.5 }} >
                            { getEventIcon(event.type)}
</ListItemIcon>
    < ListItemText
primary = {
                      < Box display = "flex" justifyContent = "space-between" alignItems = "center" >
    <Typography variant="body2" fontWeight = "bold" >
        { event.type.replace('_', ' ').toUpperCase() }
        </Typography>
        < Typography variant = "caption" color = "text.secondary" >
            { format(new Date(event.timestamp), 'HH:mm:ss')}
</Typography>
    </Box>
                    }
secondary = {
                      < Typography variant = "caption" display = "block" sx = {{ mt: 0.5 }}>
{
    typeof event.data === 'string'
        ? event.data
        : event.data?.message || JSON.stringify(event.data)
}
    </Typography>
                    }
                  />
    </ListItem>
{ index < events.length - 1 && <Divider component="li" />}
</React.Fragment>
            ))}
</List>
        )}
</Box>
    </Card>
  );
};

export default AgentActivityFeed;
