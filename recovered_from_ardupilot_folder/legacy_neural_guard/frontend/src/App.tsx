import { useState, useEffect, useCallback } from 'react'

// ==================== Types ====================

interface Location {
    lat: number
    lon: number
    alt: number
}

interface DroneStatus {
    connection: string
    ai_active: boolean
    battery_pct: number
}

interface InferenceResult {
    risk_score: number
    anomaly_type: string
    confidence: number
}

interface PhysicsData {
    roll: number
    pitch: number
    vibe_x: number
}

interface TelemetryData {
    drone_id: string
    timestamp_ms: number
    status: DroneStatus
    inference: InferenceResult
    physics: PhysicsData
    location?: Location
}

interface Drone {
    drone_id: string
    name: string
    status: string
    last_seen: string
    battery_pct: number
    risk_score: number
    location?: Location
}

interface Alert {
    id: string
    drone_id: string
    alert_type: string
    message: string
    severity: string
    timestamp: string
    acknowledged: boolean
}

interface Stats {
    total_drones: number
    online: number
    warning: number
    offline: number
    high_risk: number
    total_alerts: number
    unacknowledged_alerts: number
}

// ==================== API Service ====================

const API_BASE = '/api'

async function fetchDrones(): Promise<Drone[]> {
    const response = await fetch(`${API_BASE}/drones`)
    if (!response.ok) throw new Error('Failed to fetch drones')
    return response.json()
}

async function fetchTelemetry(droneId: string): Promise<TelemetryData> {
    const response = await fetch(`${API_BASE}/drones/${droneId}/telemetry`)
    if (!response.ok) throw new Error('Failed to fetch telemetry')
    return response.json()
}

async function fetchAlerts(): Promise<Alert[]> {
    const response = await fetch(`${API_BASE}/alerts`)
    if (!response.ok) throw new Error('Failed to fetch alerts')
    return response.json()
}

async function fetchStats(): Promise<Stats> {
    const response = await fetch(`${API_BASE}/stats`)
    if (!response.ok) throw new Error('Failed to fetch stats')
    return response.json()
}

async function acknowledgeAlert(alertId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/alerts/${alertId}/acknowledge`, {
        method: 'POST'
    })
    if (!response.ok) throw new Error('Failed to acknowledge alert')
}

async function generateMockData(): Promise<void> {
    const response = await fetch(`${API_BASE}/mock/generate`, {
        method: 'POST'
    })
    if (!response.ok) throw new Error('Failed to generate mock data')
}

// ==================== Components ====================

function Header() {
    return (
        <header className="header">
            <h1>
                <span className="header-logo">🛸</span>
                Neural Guard
                <span style={{ fontSize: '0.875rem', color: '#94a3b8', fontWeight: 400 }}>
                    Fleet Dashboard
                </span>
            </h1>
            <div className="header-status">
                <div className="status-indicator">
                    <span className="status-dot"></span>
                    <span>System Online</span>
                </div>
            </div>
        </header>
    )
}

function StatsGrid({ stats }: { stats: Stats | null }) {
    if (!stats) return null

    return (
        <div className="stats-grid">
            <div className="stat-card">
                <h3>Total Drones</h3>
                <div className="value blue">{stats.total_drones}</div>
            </div>
            <div className="stat-card">
                <h3>Online</h3>
                <div className="value green">{stats.online}</div>
            </div>
            <div className="stat-card">
                <h3>Warning</h3>
                <div className="value yellow">{stats.warning}</div>
            </div>
            <div className="stat-card">
                <h3>Offline</h3>
                <div className="value red">{stats.offline}</div>
            </div>
            <div className="stat-card">
                <h3>High Risk</h3>
                <div className="value red">{stats.high_risk}</div>
            </div>
            <div className="stat-card">
                <h3>Active Alerts</h3>
                <div className="value">{stats.unacknowledged_alerts}</div>
            </div>
        </div>
    )
}

function DroneCard({
    drone,
    selected,
    onClick
}: {
    drone: Drone
    selected: boolean
    onClick: () => void
}) {
    const getRiskLevel = (score: number) => {
        if (score < 0.3) return 'low'
        if (score < 0.7) return 'medium'
        return 'high'
    }

    return (
        <div
            className={`drone-card ${selected ? 'selected' : ''}`}
            onClick={onClick}
        >
            <div className="drone-header">
                <div>
                    <div className="drone-name">{drone.name}</div>
                    <div className="drone-id">{drone.drone_id}</div>
                </div>
                <span className={`drone-status-badge ${drone.status}`}>
                    {drone.status}
                </span>
            </div>

            <div className="drone-metrics">
                <div className="metric">
                    <div className="metric-label">Battery</div>
                    <div className="metric-value" style={{
                        color: drone.battery_pct < 20 ? '#ef4444' : drone.battery_pct < 50 ? '#eab308' : '#22c55e'
                    }}>
                        {drone.battery_pct}%
                    </div>
                </div>
                <div className="metric">
                    <div className="metric-label">AI Risk</div>
                    <div className="metric-value" style={{
                        color: drone.risk_score > 0.7 ? '#ef4444' : drone.risk_score > 0.3 ? '#eab308' : '#22c55e'
                    }}>
                        {(drone.risk_score * 100).toFixed(0)}%
                    </div>
                </div>
                <div className="metric">
                    <div className="metric-label">Anomaly</div>
                    <div className="metric-value" style={{
                        color: drone.risk_score > 0.7 ? '#ef4444' : '#94a3b8'
                    }}>
                        {drone.risk_score > 0.7 ? '⚠️' : '✓'}
                    </div>
                </div>
            </div>

            <div className="risk-bar">
                <div
                    className={`risk-fill ${getRiskLevel(drone.risk_score)}`}
                    style={{ width: `${drone.risk_score * 100}%` }}
                />
            </div>
        </div>
    )
}

function TelemetryPanel({ telemetry }: { telemetry: TelemetryData | null }) {
    if (!telemetry) {
        return (
            <div className="telemetry-panel">
                <h2>📡 Live Telemetry</h2>
                <div className="empty-state">
                    Select a drone to view telemetry
                </div>
            </div>
        )
    }

    return (
        <div className="telemetry-panel">
            <h2>📡 Live Telemetry - {telemetry.drone_id}</h2>
            <div className="telemetry-grid">
                <div className="telemetry-item">
                    <div className="telemetry-label">Roll</div>
                    <div className="telemetry-value">{telemetry.physics.roll.toFixed(2)}°</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-label">Pitch</div>
                    <div className="telemetry-value">{telemetry.physics.pitch.toFixed(2)}°</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-label">Vibration X</div>
                    <div className="telemetry-value">{telemetry.physics.vibe_x.toFixed(1)}</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-label">AI Confidence</div>
                    <div className="telemetry-value">{(telemetry.inference.confidence * 100).toFixed(0)}%</div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-label">Risk Score</div>
                    <div className="telemetry-value" style={{
                        color: telemetry.inference.risk_score > 0.7 ? '#ef4444' : telemetry.inference.risk_score > 0.3 ? '#eab308' : '#22c55e'
                    }}>
                        {(telemetry.inference.risk_score * 100).toFixed(0)}%
                    </div>
                </div>
                <div className="telemetry-item">
                    <div className="telemetry-label">Anomaly Type</div>
                    <div className="telemetry-value" style={{
                        color: telemetry.inference.anomaly_type !== 'none' ? '#ef4444' : '#22c55e'
                    }}>
                        {telemetry.inference.anomaly_type}
                    </div>
                </div>
                {telemetry.location && (
                    <>
                        <div className="telemetry-item">
                            <div className="telemetry-label">Latitude</div>
                            <div className="telemetry-value">{telemetry.location.lat.toFixed(4)}</div>
                        </div>
                        <div className="telemetry-item">
                            <div className="telemetry-label">Longitude</div>
                            <div className="telemetry-value">{telemetry.location.lon.toFixed(4)}</div>
                        </div>
                        <div className="telemetry-item">
                            <div className="telemetry-label">Altitude</div>
                            <div className="telemetry-value">{telemetry.location.alt.toFixed(1)}m</div>
                        </div>
                    </>
                )}
            </div>
        </div>
    )
}

function AlertPanel({
    alerts,
    onAcknowledge
}: {
    alerts: Alert[]
    onAcknowledge: (id: string) => void
}) {
    const unacknowledgedAlerts = alerts.filter(a => !a.acknowledged)

    return (
        <div className="alert-panel">
            <div className="alert-panel-header">
                <h2>🚨 Active Alerts</h2>
                {unacknowledgedAlerts.length > 0 && (
                    <span className="alert-count">{unacknowledgedAlerts.length}</span>
                )}
            </div>
            <div className="alert-list">
                {alerts.length === 0 ? (
                    <div className="empty-state">No alerts</div>
                ) : (
                    alerts.map(alert => (
                        <div
                            key={alert.id}
                            className={`alert-item ${alert.severity}`}
                        >
                            <div className="alert-content">
                                <div className="alert-message">{alert.message}</div>
                                <div className="alert-meta">
                                    {alert.drone_id} • {new Date(alert.timestamp).toLocaleString()}
                                </div>
                            </div>
                            {!alert.acknowledged && (
                                <button
                                    className="alert-ack-btn"
                                    onClick={() => onAcknowledge(alert.id)}
                                >
                                    Acknowledge
                                </button>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}

// ==================== Main App ====================

function App() {
    const [drones, setDrones] = useState<Drone[]>([])
    const [alerts, setAlerts] = useState<Alert[]>([])
    const [stats, setStats] = useState<Stats | null>(null)
    const [selectedDrone, setSelectedDrone] = useState<string | null>(null)
    const [telemetry, setTelemetry] = useState<TelemetryData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const loadData = useCallback(async () => {
        try {
            setLoading(true)
            setError(null)

            const [dronesData, alertsData, statsData] = await Promise.all([
                fetchDrones(),
                fetchAlerts(),
                fetchStats()
            ])

            setDrones(dronesData)
            setAlerts(alertsData)
            setStats(statsData)

            // Load telemetry for selected drone if any
            if (selectedDrone) {
                const telemetryData = await fetchTelemetry(selectedDrone)
                setTelemetry(telemetryData)
            }
        } catch (err) {
            console.error('Failed to load data:', err)
            setError('Failed to connect to backend. Make sure the API server is running.')
        } finally {
            setLoading(false)
        }
    }, [selectedDrone])

    const handleDroneSelect = async (droneId: string) => {
        setSelectedDrone(droneId)
        try {
            const telemetryData = await fetchTelemetry(droneId)
            setTelemetry(telemetryData)
        } catch (err) {
            console.error('Failed to fetch telemetry:', err)
        }
    }

    const handleAcknowledgeAlert = async (alertId: string) => {
        try {
            await acknowledgeAlert(alertId)
            setAlerts(prev => prev.map(a =>
                a.id === alertId ? { ...a, acknowledged: true } : a
            ))
        } catch (err) {
            console.error('Failed to acknowledge alert:', err)
        }
    }

    const handleGenerateMockData = async () => {
        try {
            await generateMockData()
            await loadData()
        } catch (err) {
            console.error('Failed to generate mock data:', err)
        }
    }

    // Initial load
    useEffect(() => {
        loadData()
    }, [loadData])

    // Auto-refresh every 5 seconds
    useEffect(() => {
        const interval = setInterval(() => {
            loadData()
        }, 5000)
        return () => clearInterval(interval)
    }, [loadData])

    if (loading && drones.length === 0) {
        return (
            <div className="app-container">
                <Header />
                <div className="main-content">
                    <div className="loading">
                        <div className="loading-spinner"></div>
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="app-container">
                <Header />
                <div className="main-content">
                    <div className="empty-state">
                        <h2>⚠️ Connection Error</h2>
                        <p>{error}</p>
                        <button
                            onClick={loadData}
                            style={{
                                marginTop: '1rem',
                                padding: '0.5rem 1rem',
                                background: '#3b82f6',
                                color: 'white',
                                border: 'none',
                                borderRadius: '0.25rem',
                                cursor: 'pointer'
                            }}
                        >
                            Retry
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="app-container">
            <Header />
            <div className="main-content">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Fleet Overview</h2>
                    <button
                        onClick={handleGenerateMockData}
                        style={{
                            padding: '0.5rem 1rem',
                            background: '#3b82f6',
                            color: 'white',
                            border: 'none',
                            borderRadius: '0.25rem',
                            cursor: 'pointer',
                            fontSize: '0.875rem'
                        }}
                    >
                        🔄 Refresh Data
                    </button>
                </div>

                <StatsGrid stats={stats} />

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '1.5rem' }}>
                    <div>
                        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem' }}>
                            Drones
                        </h2>
                        <div className="drone-grid">
                            {drones.map(drone => (
                                <DroneCard
                                    key={drone.drone_id}
                                    drone={drone}
                                    selected={selectedDrone === drone.drone_id}
                                    onClick={() => handleDroneSelect(drone.drone_id)}
                                />
                            ))}
                        </div>
                    </div>

                    <div>
                        <AlertPanel
                            alerts={alerts}
                            onAcknowledge={handleAcknowledgeAlert}
                        />
                    </div>
                </div>

                <TelemetryPanel telemetry={telemetry} />
            </div>
        </div>
    )
}

export default App
