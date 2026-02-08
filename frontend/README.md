# Cognizant Web Dashboard

Modern React-based web dashboard for monitoring and managing the Cognizant Autonomous Data Reliability Agent.

## Features

- **Real-time System Monitoring**: Live system health status and metrics
- **Incident Management**: View and manage detected incidents with detailed information
- **Metrics Visualization**: Interactive charts for system metrics
- **WebSocket Support**: Real-time updates for incidents and system events
- **Responsive Design**: Works on desktop and mobile devices

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Material-UI (MUI)** - Component library 
- **Recharts** - Data visualization
- **React Query** - Server state management
- **Vite** - Build tool and dev server
- **Axios** - HTTP client

## Prerequisites

- Node.js 18+ and npm
- Running Cognizant API backend (default: http://localhost:8000)

## Installation

1. **Install Dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Environment Configuration** (optional):
   Copy `.env.example` to `.env` if you need to customize auth defaults:
   ```bash
   cp .env.example .env
   ```
   Then edit values as needed:
   ```
   VITE_DEMO_USERNAME=demo
   VITE_DEMO_PASSWORD=secret
   ```

## Development

Start the development server:

```bash
npm run dev
```

The dashboard will be available at http://localhost:3000

The Vite dev server includes:
- Hot Module Replacement (HMR)
- Proxy to backend API
- Fast refresh for React components

## Building for Production

```bash
npm run build
```

This creates an optimized production build in the `dist` directory with:
- Code splitting (separate chunks for React, MUI, Charts, utilities)
- Minification and tree shaking
- Optimized asset loading
- Production-ready bundles

### Deploying to Production

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for complete production deployment instructions, including:
- Nginx configuration
- SSL setup
- Static file serving
- API proxying
- Troubleshooting guide

## Project Structure

```
frontend/
├── public/              # Static assets
│   └── index.html       # HTML template
├── src/
│   ├── components/      # React components
│   │   ├── Dashboard.tsx           # Main dashboard view
│   │   ├── IncidentList.tsx        # Incident list table
│   │   ├── IncidentDetail.tsx      # Incident detail modal
│   │   ├── MetricsChart.tsx        # Metrics visualization
│   │   └── SystemStatus.tsx        # Health indicators
│   ├── services/        # API services
│   │   ├── api.ts       # HTTP API client
│   │   └── websocket.ts # WebSocket service
│   ├── hooks/           # Custom React hooks
│   │   ├── useIncidents.ts
│   │   └── useMetrics.ts
│   ├── types/           # TypeScript definitions
│   │   └── models.ts    # Type definitions
│   ├── App.tsx          # Root component
│   └── index.tsx        # Entry point
├── package.json         # Dependencies
├── tsconfig.json        # TypeScript config
└── vite.config.ts       # Vite config
```

## API Integration

The dashboard communicates with the Cognizant API backend through:

1. **REST API** - For data retrieval and actions
2. **WebSocket** - For real-time updates

### REST Endpoints Used:
- `GET /health` - System health check
- `GET /api/v1/metrics` - System metrics
- `GET /api/v1/incidents` - List incidents
- `GET /api/v1/incidents/{id}` - Get incident details
- `POST /api/v1/cycles/trigger` - Trigger analysis cycle
- `GET /api/v1/metrics/timeseries` - Time-series data

### WebSocket Endpoint:
- `ws://localhost:8000/ws/incidents` - Real-time incident updates

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally
- `npm run lint` - Run ESLint

## Troubleshooting

### Backend Connection Issues

If the dashboard can't connect to the backend:

1. Verify the backend is running:
   ```bash
   curl http://localhost:8000/health
   ```

2. Check CORS settings in the backend API

3. Verify the proxy configuration in `vite.config.ts`

### WebSocket Connection Issues

If real-time updates aren't working:

1. Check browser console for WebSocket errors
2. Verify the backend WebSocket endpoint is accessible
3. Check firewall/proxy settings

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

## Performance

The dashboard is optimized for performance with:
- React Query for intelligent data caching
- Lazy loading of components
- Optimized re-renders
- Debounced API calls

## Contributing

When adding new features:

1. Add TypeScript types in `src/types/`
2. Create API methods in `src/services/api.ts`
3. Build React Query hooks in `src/hooks/`
4. Create UI components in `src/components/`
5. Maintain responsive design principles

## License

Part of the Cognizant project.
