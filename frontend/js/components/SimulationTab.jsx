const { useState, useEffect, useRef, useCallback } = React;

function SimulationTab({ project, schemas, recipes, activeMapName, isActive }) {
    // Playback & Sim State
    const [simTime, setSimTime] = useState(0.0);
    const [isPlaying, setIsPlaying] = useState(true);
    const [speed, setSpeed] = useState(1.0);
    const [connected, setConnected] = useState(false);
    
    // Entities & Metrics
    const [agents, setAgents] = useState([]);
    const [machines, setMachines] = useState([]);
    const [metrics, setMetrics] = useState({
        sim_time: 0,
        throughput: 0,
        throughput_rate_hr: 0,
        avg_wait_time: 0,
        fleet_avg_utilization: 0,
        machines: [],
        agents: [],
        heatmap: {},
        top_bottlenecks: []
    });

    // Map & Rendering
    const [mapData, setMapData] = useState({ tracks: [], machines: [], nodes: {} });
    const [showHeatmap, setShowHeatmap] = useState(true);
    const [showLabels, setShowLabels] = useState(true);
    const [selectedEntity, setSelectedEntity] = useState(null);

    // Sidebar active sub-tab: 'kpi' | 'strategies' | 'fleet' | 'machines'
    const [sidebarTab, setSidebarTab] = useState('kpi');

    // Strategy & Fleet Settings
    const [strategies, setStrategies] = useState({
        pathfinding: 'dijkstra',
        traffic: 'block_reservation',
        vehicle_assignment: 'nearest',
        machine_allocation: 'least_loaded',
        idle_strategy: 'stay_and_nudge'
    });
    const [ohtSpecs, setOhtSpecs] = useState({
        length_m: 1.0,
        width_m: 0.4,
        buffer_m: 0.2,
        min_section_len_m: 1.2,
        speed_max: 2000.0,
        speed_curve: 800.0,
        speed_crawl: 300.0,
        accel: 1500.0,
        decel: 2000.0
    });
    const [fleetSize, setFleetSize] = useState(5);
    const [isApplyingConfig, setIsApplyingConfig] = useState(false);


    // Duration & Fast-Forward Benchmark State
    const [targetDuration, setTargetDuration] = useState(60.0);
    const [isFastForwarding, setIsFastForwarding] = useState(false);
    const [showBenchmarkModal, setShowBenchmarkModal] = useState(false);
    const [benchmarkResults, setBenchmarkResults] = useState(null);
    const [selectedMachinePie, setSelectedMachinePie] = useState("ALL");
    const [pieHoverSlice, setPieHoverSlice] = useState(null);

    // Canvas refs
    const canvasRef = useRef(null);
    const wsRef = useRef(null);
    const animFrameRef = useRef(null);
    const latestStateRef = useRef({ agents: [], machines: [], metrics: null, simTime: 0, serverTime: 0 });
    const renderedAgentsRef = useRef({});
    const lastFrameTimeRef = useRef(performance.now());
    const hasAutoFittedRef = useRef(false);
    const lastInitKeyRef = useRef("");
    const targetSimTimeEndRef = useRef(null);

    // View Transform
    const viewRef = useRef({ panX: 400, panY: 350, zoom: 120 });
    const mouseRef = useRef({ isDown: false, startX: 0, startY: 0, worldX: 0, worldY: 0 });

    // Helper: Norm Angle
    const normAng = (a) => {
        let ang = a % 360;
        if (ang < 0) ang += 360;
        return ang;
    };

    // Helper: Heading vector
    const dirVector = (h) => {
        const rad = h * Math.PI / 180;
        return { x: Math.sin(rad), y: Math.cos(rad) };
    };

    // Coordinate conversions
    const worldToScreen = (wx, wy) => {
        const v = viewRef.current;
        return {
            x: v.panX + wx * v.zoom,
            y: v.panY - wy * v.zoom
        };
    };

    const screenToWorld = (sx, sy) => {
        const v = viewRef.current;
        return {
            x: (sx - v.panX) / v.zoom,
            y: (v.panY - sy) / v.zoom
        };
    };

    // Center & Fit View to loaded tracks
    const fitViewToTracks = useCallback((tracks) => {
        if (!canvasRef.current || !tracks || tracks.length === 0) return;
        const c = canvasRef.current;
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        tracks.forEach(t => {
            minX = Math.min(minX, t.x - 1);
            maxX = Math.max(maxX, t.x + 2);
            minY = Math.min(minY, t.y - 1);
            maxY = Math.max(maxY, t.y + 2);
        });
        if (minX === Infinity) return;

        const w = Math.max(2, maxX - minX);
        const h = Math.max(2, maxY - minY);
        const cRect = c.getBoundingClientRect();
        const zoomX = (cRect.width * 0.75) / w;
        const zoomY = (cRect.height * 0.75) / h;
        const zoom = Math.max(50, Math.min(180, Math.min(zoomX, zoomY)));

        const midX = (minX + maxX) / 2;
        const midY = (minY + maxY) / 2;

        viewRef.current = {
            zoom: zoom,
            panX: cRect.width / 2 - midX * zoom,
            panY: cRect.height / 2 + midY * zoom
        };
    }, []);

    // SVG Donut / Pie Chart Geometry Helpers
    const polarToCartesian = (cx, cy, r, angleInDegrees) => {
        const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
        return {
            x: cx + (r * Math.cos(angleInRadians)),
            y: cy + (r * Math.sin(angleInRadians))
        };
    };

    const describeArc = (cx, cy, radius, innerRadius, startAngle, endAngle) => {
        const start = polarToCartesian(cx, cy, radius, endAngle);
        const end = polarToCartesian(cx, cy, radius, startAngle);
        const innerStart = polarToCartesian(cx, cy, innerRadius, endAngle);
        const innerEnd = polarToCartesian(cx, cy, innerRadius, startAngle);
        const arcSweep = endAngle - startAngle <= 180 ? "0" : "1";

        return [
            "M", start.x, start.y,
            "A", radius, radius, 0, arcSweep, 0, end.x, end.y,
            "L", innerEnd.x, innerEnd.y,
            "A", innerRadius, innerRadius, 0, arcSweep, 1, innerStart.x, innerStart.y,
            "Z"
        ].join(" ");
    };

    // Helper to render SVG Donut slices
    const renderDonutSlices = (activeT, blockedT, starvedT, hoverSlice, setHoverSlice) => {
        const total = activeT + blockedT + starvedT;
        if (total <= 0.001) {
            return (
                <circle cx="90" cy="75" r="47" fill="none" stroke="#334155" strokeWidth="22" opacity="0.4" />
            );
        }
        const slices = [
            { key: 'PROCESSING', label: 'Processing (Active)', value: activeT, color: '#10b981', hoverColor: '#34d399' },
            { key: 'PAUSED_BACKPRESSURE', label: 'Blocked (Backpr.)', value: blockedT, color: '#f59e0b', hoverColor: '#fbbf24' },
            { key: 'IDLE', label: 'Starved / Idle', value: starvedT, color: '#64748b', hoverColor: '#94a3b8' }
        ].filter(s => s.value > 0.0001);

        let currentAngle = 0;
        const cx = 90, cy = 75, R = 58, r = 36;

        return slices.map(slice => {
            const fraction = slice.value / total;
            const angle = fraction * 360.0;
            const startAng = currentAngle;
            const endAng = currentAngle + angle;
            currentAngle += angle;

            const isHovered = hoverSlice && hoverSlice.key === slice.key;
            const curR = isHovered ? R + 3 : R;
            const cur_r = isHovered ? r - 2 : r;

            if (fraction >= 0.9999) {
                return (
                    <g 
                        key={slice.key} 
                        onMouseEnter={() => setHoverSlice && setHoverSlice({ ...slice, pct: (fraction * 100).toFixed(1) })} 
                        onMouseLeave={() => setHoverSlice && setHoverSlice(null)} 
                        style={{ cursor: 'pointer' }}
                    >
                        <circle cx={cx} cy={cy} r={(curR + cur_r) / 2} fill="none" stroke={slice.color} strokeWidth={curR - cur_r} />
                    </g>
                );
            }

            const d = describeArc(cx, cy, curR, cur_r, startAng, endAng);
            return (
                <path
                    key={slice.key}
                    d={d}
                    fill={isHovered ? slice.hoverColor : slice.color}
                    stroke="#090d16"
                    strokeWidth="1.5"
                    style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
                    onMouseEnter={() => setHoverSlice && setHoverSlice({ ...slice, pct: (fraction * 100).toFixed(1) })}
                    onMouseLeave={() => setHoverSlice && setHoverSlice(null)}
                >
                    <title>{`${slice.label}: ${slice.value.toFixed(1)}s (${(fraction * 100).toFixed(1)}%)`}</title>
                </path>
            );
        });
    };

    // Control simulation playback
    const sendSimCommand = useCallback(async (cmd) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(cmd));
        } else {
            try {
                await window.API.request('/api/simulation/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(cmd)
                });
            } catch (e) {
                console.warn("REST control error:", e);
            }
        }
    }, []);

    // Re-initialize / reload backend simulation state
    const reinitSimulation = useCallback(async (playAfter = true) => {
        try {
            await window.API.request('/api/simulation/init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project: project,
                    map_filename: activeMapName || 'map.json',
                    fleet_size: fleetSize,
                    strategies: strategies,
                    recipes: recipes
                })
            });
            targetSimTimeEndRef.current = null;
            if (playAfter) {
                sendSimCommand({ action: isPlaying ? 'play' : 'pause', speed: speed });
            }
        } catch (e) {
            console.error("Failed to reinit simulation:", e);
        }
    }, [project, activeMapName, fleetSize, strategies, recipes, isPlaying, speed, sendSimCommand]);

    // Load Map data
    const loadMapData = useCallback(async (forceFit = false) => {
        try {
            const targetMap = activeMapName || 'map.json';
            const data = await window.API.loadMap(project, targetMap);
            if (data && data.tracks) {
                setMapData(data);
                if (forceFit || !hasAutoFittedRef.current) {
                    fitViewToTracks(data.tracks);
                    hasAutoFittedRef.current = true;
                }
            }
        } catch (e) {
            console.warn("Could not load simulation map directly, checking Builder...", e);
            if (window.Builder && window.Builder.tracks && window.Builder.tracks.length > 0) {
                const bData = {
                    tracks: window.Builder.tracks,
                    machines: window.Builder.machines,
                    nodes: window.Builder.nodes
                };
                setMapData(bData);
                if (forceFit || !hasAutoFittedRef.current) {
                    fitViewToTracks(bData.tracks);
                    hasAutoFittedRef.current = true;
                }
            }
        }
    }, [project, activeMapName, fitViewToTracks]);

    // Initial map and simulation loading when tab is active or project/map changes
    useEffect(() => {
        if (!isActive) return;
        const currentKey = `${project}:${activeMapName || 'map.json'}`;
        if (lastInitKeyRef.current !== currentKey) {
            lastInitKeyRef.current = currentKey;
            hasAutoFittedRef.current = false;
            loadMapData(true);
            reinitSimulation(false);
        }
    }, [isActive, project, activeMapName, loadMapData, reinitSimulation]);

    // WebSocket Simulation connection
    useEffect(() => {
        let isCancelled = false;

        const connectWS = () => {
            const host = window.location.host || 'localhost:8000';
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${host}/ws/simulation`;

            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                if (!isCancelled) {
                    setConnected(true);
                    console.log("WebSocket connected to /ws/simulation");
                }
            };

            let lastUiUpdate = 0;
            ws.onmessage = (evt) => {
                if (isCancelled) return;
                try {
                    const data = JSON.parse(evt.data);
                    latestStateRef.current = {
                        agents: data.agents || [],
                        machines: data.machines || [],
                        metrics: data.metrics || null,
                        simTime: data.sim_time || 0,
                        serverTime: data.server_time || Date.now() / 1000
                    };
                    const now = Date.now();
                    if (now - lastUiUpdate > 200) {
                        lastUiUpdate = now;
                        setSimTime(data.sim_time || 0);
                        if (data.metrics) setMetrics(data.metrics);
                        if (data.agents) setAgents(data.agents);
                        if (data.machines) setMachines(data.machines);
                    }
                    if (data.strategies) {
                        setStrategies(prev => ({ ...prev, ...data.strategies }));
                    }
                    if (data.oht_specs) {
                        setOhtSpecs(prev => ({ ...prev, ...data.oht_specs }));
                    }

                    // Auto-pause if explicit timed run duration reached
                    if (isPlaying && targetSimTimeEndRef.current !== null && (data.sim_time || 0) >= targetSimTimeEndRef.current) {
                        targetSimTimeEndRef.current = null;
                        setIsPlaying(false);
                        sendSimCommand({ action: 'pause' });
                        if (data.metrics) {
                            setBenchmarkResults({
                                sim_time: data.sim_time || 0,
                                duration_run: targetDuration,
                                summary: data.metrics
                            });
                            setShowBenchmarkModal(true);
                        }
                    }

                } catch (e) {
                    console.error("WS Parse error:", e);
                }
            };

            ws.onclose = () => {
                if (!isCancelled) {
                    setConnected(false);
                    // Attempt reconnect after 1.5s
                    setTimeout(connectWS, 1500);
                }
            };

            ws.onerror = (err) => {
                console.warn("WebSocket error:", err);
            };
        };

        connectWS();

        return () => {
            isCancelled = true;
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, []);

    const handleTogglePlay = () => {
        const nextState = !isPlaying;
        setIsPlaying(nextState);
        targetSimTimeEndRef.current = null;
        sendSimCommand({ action: nextState ? 'play' : 'pause', speed: speed });
    };

    const handleStep = () => {
        sendSimCommand({ action: 'step', dt: 0.1 });
    };

    const handleReset = () => {
        targetSimTimeEndRef.current = null;
        reinitSimulation(isPlaying);
        setSimTime(0.0);
    };

    const handleSetSpeed = (newSpeed) => {
        setSpeed(newSpeed);
        if (isPlaying) {
            sendSimCommand({ action: 'set_speed', speed: newSpeed });
        }
    };

    // Fast-Forward Execution Handler
    const handleFastRun = async (targetDur = targetDuration, resetFirst = false) => {
        if (isFastForwarding) return;
        setIsFastForwarding(true);
        try {
            if (isPlaying) {
                setIsPlaying(false);
                sendSimCommand({ action: 'pause' });
            }
            const res = await window.API.fastForward({
                duration: parseFloat(targetDur) || 60.0,
                reset_first: resetFirst,
                dt: 0.05
            });
            if (res && res.status === 'ok') {
                setSimTime(res.sim_time);
                if (res.summary) {
                    setMetrics(res.summary);
                    setBenchmarkResults(res);
                    setShowBenchmarkModal(true);
                }
            }
        } catch (e) {
            console.error("Fast-forward execution failed:", e);
            alert("Fast forward failed: " + e.message);
        } finally {
            setIsFastForwarding(false);
        }
    };

    // Re-init / Apply strategy & fleet changes
    const applySimulationConfig = async () => {
        setIsApplyingConfig(true);
        try {
            await window.API.request('/api/simulation/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategies: strategies,
                    fleet_size: fleetSize,
                    oht_specs: ohtSpecs
                })
            });

        } catch (e) {
            console.error("Failed to update sim config:", e);
        } finally {
            setIsApplyingConfig(false);
        }
    };

    // Export metrics handler
    const handleExport = (format) => {
        const url = `${window.API.getBaseUrl()}/api/simulation/export_metrics?format=${format}`;
        window.open(url, '_blank');
    };

    // Curve geometry helper
    const getCurvePoints = (x, y, heading, isRight, R = 0.5) => {
        const points = [];
        const d_turn = dirVector(isRight ? heading + 90 : heading - 90);
        const cx = x + R * d_turn.x;
        const cy = y + R * d_turn.y;
        for (let i = 0; i <= 90; i += 10) {
            const ht = isRight ? heading + i : heading - i;
            const d_arm = dirVector(isRight ? ht + 90 : ht - 90);
            points.push({ x: cx - R * d_arm.x, y: cy - R * d_arm.y });
        }
        return points;
    };

    // Track points generator matching builder
    const getTrackSegments = (tr) => {
        const d_fwd = dirVector(tr.heading);
        const L = tr.length || 1.0;
        const R = 0.5;
        const subsegments = [];

        if (tr.type === "STRAIGHT") {
            subsegments.push([
                { x: tr.x, y: tr.y },
                { x: tr.x + L * d_fwd.x, y: tr.y + L * d_fwd.y }
            ]);
        } else if (tr.type === "TURN_R" || tr.type === "TURN_L") {
            subsegments.push(getCurvePoints(tr.x, tr.y, tr.heading, tr.type === "TURN_R", R));
        } else if (tr.type === "DIVERGE_R" || tr.type === "DIVERGE_L") {
            const isRight = tr.type === "DIVERGE_R";
            subsegments.push([
                { x: tr.x, y: tr.y },
                { x: tr.x + 0.5 * d_fwd.x, y: tr.y + 0.5 * d_fwd.y }
            ]);
            subsegments.push(getCurvePoints(tr.x, tr.y, tr.heading, isRight, R));
        } else if (tr.type === "MERGE_R" || tr.type === "MERGE_L") {
            const isRight = tr.type === "MERGE_R";
            subsegments.push([
                { x: tr.x, y: tr.y },
                { x: tr.x + 0.5 * d_fwd.x, y: tr.y + 0.5 * d_fwd.y }
            ]);
            const d_side = dirVector(isRight ? tr.heading + 90 : tr.heading - 90);
            const in2X = tr.x + R * d_side.x;
            const in2Y = tr.y + R * d_side.y;
            const in2Heading = isRight ? normAng(tr.heading - 90) : normAng(tr.heading + 90);
            subsegments.push(getCurvePoints(in2X, in2Y, in2Heading, isRight, R));
        }
        return subsegments;
    };

    // Color gradient for heatmap (green -> yellow -> red)
    const getHeatColor = (heatLevel) => {
        if (!heatLevel || heatLevel <= 0.05) return '#334155'; // default cool slate track
        const t = Math.max(0, Math.min(1, heatLevel));
        if (t < 0.5) {
            // Green (#22c55e) to Yellow (#eab308)
            const factor = t / 0.5;
            const r = Math.round(34 + factor * (234 - 34));
            const g = Math.round(197 + factor * (179 - 197));
            const b = Math.round(94 + factor * (8 - 94));
            return `rgb(${r}, ${g}, ${b})`;
        } else {
            // Yellow (#eab308) to Red (#ef4444)
            const factor = (t - 0.5) / 0.5;
            const r = Math.round(234 + factor * (239 - 234));
            const g = Math.round(179 + factor * (68 - 179));
            const b = Math.round(8 + factor * (68 - 8));
            return `rgb(${r}, ${g}, ${b})`;
        }
    };

    // Canvas Render Loop
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const render = () => {
            // Handle DPI Scaling
            const rect = canvas.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
                canvas.width = rect.width * dpr;
                canvas.height = rect.height * dpr;
            }

            ctx.save();
            ctx.scale(dpr, dpr);

            const width = rect.width;
            const height = rect.height;

            // 1. Clear & Background
            ctx.fillStyle = "#090d16";
            ctx.fillRect(0, 0, width, height);

            // 2. Subtle coordinate grid
            const minW = screenToWorld(0, height);
            const maxW = screenToWorld(width, 0);

            ctx.strokeStyle = "#141c2e";
            ctx.lineWidth = 1;
            ctx.beginPath();
            for (let x = Math.floor(minW.x); x <= Math.ceil(maxW.x); x += 1.0) {
                const p = worldToScreen(x, 0);
                ctx.moveTo(p.x, 0);
                ctx.lineTo(p.x, height);
            }
            for (let y = Math.floor(minW.y); y <= Math.ceil(maxW.y); y += 1.0) {
                const p = worldToScreen(0, y);
                ctx.moveTo(0, p.y);
                ctx.lineTo(width, p.y);
            }
            ctx.stroke();

            // 3. Draw Tracks
            const tracks = mapData.tracks || [];
            const heatmapData = metrics.heatmap || {};

            tracks.forEach(tr => {
                const subsegs = getTrackSegments(tr);
                let heatInfo = heatmapData[tr.id] || null;
                if (!heatInfo) {
                    for (const [k, val] of Object.entries(heatmapData)) {
                        if (k === tr.id || k.startsWith(tr.id + '_') || k.startsWith(tr.id + '-')) {
                            heatInfo = val;
                            break;
                        }
                    }
                }
                const heatLevel = heatInfo ? heatInfo.heat_level : 0;
                const trackColor = showHeatmap && heatLevel > 0.05 ? getHeatColor(heatLevel) : "#334155";
                const trackWidth = showHeatmap && heatLevel > 0.4 ? 5 : 4;

                ctx.strokeStyle = trackColor;
                ctx.lineWidth = trackWidth;
                ctx.lineCap = "round";
                ctx.lineJoin = "round";

                if (showHeatmap && heatLevel > 0.7) {
                    ctx.shadowColor = trackColor;
                    ctx.shadowBlur = 8;
                } else {
                    ctx.shadowBlur = 0;
                }

                subsegs.forEach(pts => {
                    if (pts.length < 2) return;
                    ctx.beginPath();
                    const p0 = worldToScreen(pts[0].x, pts[0].y);
                    ctx.moveTo(p0.x, p0.y);
                    for (let i = 1; i < pts.length; i++) {
                        const pi = worldToScreen(pts[i].x, pts[i].y);
                        ctx.lineTo(pi.x, pi.y);
                    }
                    ctx.stroke();
                });

                ctx.shadowBlur = 0;

                // Subtle forward directional arrow at midpoint
                const d_fwd = dirVector(tr.heading);
                const midX = tr.x + (tr.length ? tr.length / 2 : 0.25) * d_fwd.x;
                const midY = tr.y + (tr.length ? tr.length / 2 : 0.25) * d_fwd.y;
                const midScreen = worldToScreen(midX, midY);

                ctx.save();
                ctx.translate(midScreen.x, midScreen.y);
                ctx.rotate((tr.heading * Math.PI) / 180);
                ctx.fillStyle = trackColor;
                ctx.beginPath();
                ctx.moveTo(0, -6);
                ctx.lineTo(-4, 4);
                ctx.lineTo(4, 4);
                ctx.closePath();
                ctx.fill();
                ctx.restore();
            });

            // 4. Draw Machines & Live State
            const machList = mapData.machines || [];
            const liveMachines = latestStateRef.current.machines || [];
            const machStateMap = {};
            liveMachines.forEach(lm => {
                machStateMap[lm.id] = lm;
            });

            machList.forEach(m => {
                const schema = schemas[m.schema_id] || {};
                const live = machStateMap[m.id] || null;
                const state = live ? live.state : 'IDLE';
                const processed = live ? live.processed_count : 0;
                const center = worldToScreen(m.x, m.y);
                const heading = m.heading || 0;
                const w = (schema.width || m.width || 0.8) * viewRef.current.zoom;
                const h = (schema.height || m.height || 0.8) * viewRef.current.zoom;
                const role = schema.machine_role || 'normal';

                let baseBg = "#1e293b";
                if (role === 'source') baseBg = "#064e3b";
                else if (role === 'sink') baseBg = "#7f1d1d";

                let borderColor = "#475569";
                if (state === 'PROCESSING') borderColor = "#38bdf8";
                else if (state === 'PAUSED_BACKPRESSURE') borderColor = "#f59e0b";
                else if (state === 'UNLOADING' || state === 'LOADING') borderColor = "#a855f7";

                ctx.save();
                ctx.translate(center.x, center.y);
                ctx.rotate((heading * Math.PI) / 180);

                // Glow for active/blocked
                if (state === 'PROCESSING') {
                    ctx.shadowColor = "#38bdf8";
                    ctx.shadowBlur = 10;
                } else if (state === 'PAUSED_BACKPRESSURE') {
                    ctx.shadowColor = "#f59e0b";
                    ctx.shadowBlur = 12;
                }

                // Body
                ctx.fillStyle = baseBg;
                ctx.fillRect(-w / 2, -h / 2, w, h);
                ctx.strokeStyle = borderColor;
                ctx.lineWidth = state === 'PAUSED_BACKPRESSURE' || state === 'PROCESSING' ? 3.5 : 2;
                ctx.strokeRect(-w / 2, -h / 2, w, h);

                ctx.shadowBlur = 0;

                // Orientation notch (North)
                ctx.beginPath();
                ctx.moveTo(0, -h / 2 + 2);
                ctx.lineTo(-5, -h / 2 + 8);
                ctx.lineTo(5, -h / 2 + 8);
                ctx.closePath();
                ctx.fillStyle = borderColor;
                ctx.fill();

                // Machine Name / Schema
                ctx.fillStyle = "#f8fafc";
                ctx.font = "bold 11px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(m.name || m.schema_id || "M", 0, -8);

                // State indicator pill inside machine
                if (state === 'PAUSED_BACKPRESSURE') {
                    ctx.fillStyle = "#f59e0b";
                    ctx.font = "bold 9px sans-serif";
                    ctx.fillText("PAUSED (BACKPR.)", 0, 6);
                } else if (state === 'PROCESSING') {
                    ctx.fillStyle = "#38bdf8";
                    ctx.font = "bold 9px sans-serif";
                    ctx.fillText("PROCESSING", 0, 6);
                } else {
                    ctx.fillStyle = "#94a3b8";
                    ctx.font = "9px sans-serif";
                    ctx.fillText(`OUT: ${processed}`, 0, 6);
                }

                // Ports on machine
                const schemaPorts = schema.ports || [];
                schemaPorts.forEach(sp => {
                    const pLocalX = sp.rel_x * viewRef.current.zoom;
                    const pLocalY = -sp.rel_y * viewRef.current.zoom;
                    let portBg = sp.type === "LOAD" ? "#22c55e" : (sp.type === "UNLOAD" ? "#ef4444" : "#eab308");

                    // Outer circle
                    ctx.beginPath();
                    ctx.arc(pLocalX, pLocalY, 6, 0, 2 * Math.PI);
                    ctx.fillStyle = "#0f172a";
                    ctx.fill();
                    ctx.strokeStyle = "#cbd5e1";
                    ctx.lineWidth = 1;
                    ctx.stroke();

                    // Inner color
                    ctx.beginPath();
                    ctx.arc(pLocalX, pLocalY, 4.5, 0, 2 * Math.PI);
                    ctx.fillStyle = portBg;
                    ctx.fill();

                    // Check if port has cargo carrier
                    if (live && live.ports) {
                        const lp = live.ports.find(p => p.index === sp.id || p.node_idx === sp.id);
                        if (lp && lp.cargo) {
                            // Draw gold cargo wafer inside port
                            ctx.fillStyle = "#fbbf24";
                            ctx.fillRect(pLocalX - 3, pLocalY - 3, 6, 6);
                        }
                    }
                });

                ctx.restore();
            });

            // 5. Draw OHT Vehicles with 60 FPS Kinematic Smoothing (Lerp & Slerp)
            const now = performance.now();
            const dtFrame = Math.min(0.1, (now - lastFrameTimeRef.current) / 1000.0);
            lastFrameTimeRef.current = now;

            const targetAgents = latestStateRef.current.agents || [];
            const renderedMap = renderedAgentsRef.current;

            // Prune agents no longer in fleet
            const targetIds = new Set(targetAgents.map(a => a.id));
            Object.keys(renderedMap).forEach(aid => {
                if (!targetIds.has(aid)) delete renderedMap[aid];
            });

            targetAgents.forEach(ag => {
                let rend = renderedMap[ag.id];
                if (!rend) {
                    rend = {
                        x: ag.x,
                        y: ag.y,
                        heading: ag.heading || 0,
                        speed: ag.speed || 0,
                        state: ag.state,
                        cargo: ag.cargo
                    };
                    renderedMap[ag.id] = rend;
                }

                // Interpolate position towards target
                const dx = ag.x - rend.x;
                const dy = ag.y - rend.y;
                const distSq = dx * dx + dy * dy;

                if (distSq > 4.0) {
                    // Teleport / spawn threshold
                    rend.x = ag.x;
                    rend.y = ag.y;
                    rend.heading = ag.heading || 0;
                } else {
                    const currentSimSpeed = (typeof speed === 'number' && speed > 0) ? speed : 1.0;
                    const lambda = 22.0 * Math.max(1.0, currentSimSpeed);
                    const factor = Math.min(1.0, 1.0 - Math.exp(-lambda * dtFrame));

                    rend.x += dx * factor;
                    rend.y += dy * factor;

                    // Shortest angular path heading interpolation
                    const targetHeading = ag.heading || 0;
                    let diffAngle = ((targetHeading - rend.heading + 540) % 360) - 180;
                    rend.heading = (rend.heading + diffAngle * factor + 360) % 360;
                }

                rend.speed = ag.speed;
                rend.cargo = ag.cargo;
                rend.state = ag.state;

                const screenP = worldToScreen(rend.x, rend.y);
                const heading = rend.heading;
                const vZoom = viewRef.current.zoom;

                // Vehicle dimensions based on configured OHT physical specs
                const specL = (ohtSpecs && ohtSpecs.length_m) || 1.0;
                const specW = (ohtSpecs && ohtSpecs.width_m) || 0.4;
                const botW = specW * vZoom;
                const botL = specL * vZoom;

                ctx.save();
                ctx.translate(screenP.x, screenP.y);
                ctx.rotate((heading * Math.PI) / 180);

                let botColor = rend.cargo ? "#f59e0b" : "#38bdf8"; // gold if loaded, sky blue if empty
                if (rend.state === "WAITING_TRAFFIC" || rend.state === "WAITING_BLOCK") botColor = "#f97316";

                // Shadow/Glow
                ctx.shadowColor = botColor;
                ctx.shadowBlur = rend.cargo ? 8 : 5;

                // Vehicle Chassis (rounded capsule)
                ctx.fillStyle = "#0f172a";
                ctx.beginPath();
                const radius = botW / 2;
                ctx.roundRect(-botW / 2, -botL / 2, botW, botL, radius);
                ctx.fill();

                ctx.strokeStyle = botColor;
                ctx.lineWidth = 2.5;
                ctx.stroke();

                ctx.shadowBlur = 0;

                // FOUP / Cargo on top
                if (rend.cargo) {
                    ctx.fillStyle = "#fbbf24";
                    ctx.fillRect(-botW * 0.32, -botL * 0.28, botW * 0.64, botL * 0.56);
                    ctx.strokeStyle = "#d97706";
                    ctx.lineWidth = 1.5;
                    ctx.strokeRect(-botW * 0.32, -botL * 0.28, botW * 0.64, botL * 0.56);
                } else {
                    // Forward orientation chevron
                    ctx.fillStyle = botColor;
                    ctx.beginPath();
                    ctx.moveTo(0, -botL * 0.3);
                    ctx.lineTo(-botW * 0.25, -botL * 0.05);
                    ctx.lineTo(botW * 0.25, -botL * 0.05);
                    ctx.closePath();
                    ctx.fill();
                }

                // ID label & speed badge
                if (showLabels) {
                    ctx.rotate(-(heading * Math.PI) / 180); // un-rotate text for easy reading
                    ctx.fillStyle = "#f8fafc";
                    ctx.font = "bold 10px monospace";
                    ctx.textAlign = "center";
                    ctx.textBaseline = "bottom";
                    ctx.fillText(`${ag.id} (${(ag.speed || 0).toFixed(1)}m/s)`, 0, -botL / 2 - 4);
                }

                ctx.restore();
            });

            ctx.restore();
            animFrameRef.current = requestAnimationFrame(render);
        };

        animFrameRef.current = requestAnimationFrame(render);
        return () => {
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        };
    }, [mapData, schemas, showHeatmap, showLabels, metrics.heatmap]);

    // Canvas Mouse & Wheel Interaction (Rock-Solid Pan & Smooth Zoom)
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const onMouseDown = (e) => {
            if (e.button === 0 || e.button === 1) {
                mouseRef.current.isDown = true;
                mouseRef.current.startX = e.clientX;
                mouseRef.current.startY = e.clientY;
                canvas.style.cursor = 'grabbing';
            }
        };

        const onMouseMove = (e) => {
            if (mouseRef.current.isDown) {
                const dx = e.clientX - mouseRef.current.startX;
                const dy = e.clientY - mouseRef.current.startY;
                mouseRef.current.startX = e.clientX;
                mouseRef.current.startY = e.clientY;

                viewRef.current.panX += dx;
                viewRef.current.panY += dy;
            }
        };

        const onMouseUp = () => {
            if (mouseRef.current.isDown) {
                mouseRef.current.isDown = false;
                if (canvas) canvas.style.cursor = 'grab';
            }
        };

        const onWheel = (e) => {
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            // Smooth cursor-centered zoom
            const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
            const oldZoom = viewRef.current.zoom;
            const newZoom = Math.max(25, Math.min(450, oldZoom * zoomFactor));

            viewRef.current.panX = mouseX - (mouseX - viewRef.current.panX) * (newZoom / oldZoom);
            viewRef.current.panY = mouseY - (mouseY - viewRef.current.panY) * (newZoom / oldZoom);
            viewRef.current.zoom = newZoom;
        };

        canvas.addEventListener('mousedown', onMouseDown);
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        canvas.addEventListener('wheel', onWheel, { passive: false });

        return () => {
            canvas.removeEventListener('mousedown', onMouseDown);
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
            canvas.removeEventListener('wheel', onWheel);
        };
    }, []);

    // Keyboard Spacebar to toggle Play/Pause
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (!isActive) return;
            if (e.code === "Space" && e.target.tagName !== "INPUT" && e.target.tagName !== "SELECT") {
                e.preventDefault();
                handleTogglePlay();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isActive, isPlaying, speed]);

    // Format sim clock
    const formatSimTime = (t) => {
        const sec = Math.floor(t % 60);
        const min = Math.floor(t / 60);
        const dec = Math.floor((t % 1) * 10);
        return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}.${dec}`;
    };

    return (
        <div style={{ display: 'flex', width: '100%', height: '100%', minHeight: 0, maxHeight: '100%', position: 'relative', overflow: 'hidden' }}>
            {/* Main Canvas Viewport */}
            <div className="main-content" style={{ flex: 1, position: 'relative', height: '100%', minHeight: 0, maxHeight: '100%', overflow: 'hidden' }}>
                
                {/* Floating Playback Bar */}
                <div className="sim-floating-bar">
                    {/* Play/Pause Button */}
                    <button 
                        className={`sim-pill-btn ${isPlaying ? 'primary' : ''}`}
                        onClick={handleTogglePlay}
                        title={isPlaying ? "Pause Simulation (Space)" : "Start Simulation (Space)"}
                    >
                        <span>{isPlaying ? '⏸ Pause' : '▶ Play'}</span>
                    </button>

                    {/* Step Button */}
                    <button 
                        className="sim-pill-btn" 
                        onClick={handleStep}
                        title="Step forward +0.1s"
                    >
                        <span>⏭ Step</span>
                    </button>

                    {/* Reset Button */}
                    <button 
                        className="sim-pill-btn danger" 
                        onClick={handleReset}
                        title="Reset simulation time and reload fresh state"
                    >
                        <span>↺ Reset</span>
                    </button>

                    {/* Reload Map Button */}
                    <button 
                        className="sim-pill-btn" 
                        style={{ background: '#0369a1', color: '#f8fafc', borderColor: '#38bdf8' }}
                        onClick={() => { loadMapData(); reinitSimulation(); }}
                        title="Reload latest saved map from disk and restart simulation"
                    >
                        <span>🔄 Reload Map</span>
                    </button>

                    {/* Sim Clock Display */}
                    <div className="sim-clock-badge" title="Current Simulation Time">
                        ⏱ {formatSimTime(simTime)} ({simTime.toFixed(1)}s)
                    </div>

                    {/* Speed Multipliers */}
                    <div style={{ display: 'flex', gap: '4px', alignItems: 'center', marginLeft: '6px' }}>
                        {[0.5, 1, 2, 5, 10].map(s => (
                            <button
                                key={s}
                                className={`sim-pill-btn ${speed === s ? 'active' : ''}`}
                                style={{ padding: '3px 8px', fontSize: '11px' }}
                                onClick={() => handleSetSpeed(s)}
                            >
                                {s}x
                            </button>
                        ))}
                    </div>

                    <div style={{ width: '1px', height: '18px', background: '#334155', margin: '0 4px' }} />

                    {/* Target Duration Selector & Fast Run */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>Target:</span>
                        <select
                            value={targetDuration}
                            onChange={e => setTargetDuration(parseFloat(e.target.value))}
                            style={{
                                background: '#090d16',
                                border: '1px solid #334155',
                                color: '#38bdf8',
                                borderRadius: '4px',
                                padding: '3px 6px',
                                fontSize: '11px',
                                cursor: 'pointer'
                            }}
                            title="Set simulation stop duration"
                        >
                            <option value="60">60s (1m)</option>
                            <option value="180">180s (3m)</option>
                            <option value="300">300s (5m)</option>
                            <option value="600">600s (10m)</option>
                            <option value="1800">1800s (30m)</option>
                            <option value="3600">3600s (1h)</option>
                        </select>
                    </div>

                    <button
                        className="sim-pill-btn"
                        style={{ background: '#0284c7', color: '#f8fafc', borderColor: '#38bdf8', fontWeight: 600 }}
                        onClick={() => handleFastRun(targetDuration, false)}
                        disabled={isFastForwarding}
                        title={`Run headless fast-forward to +${targetDuration}s without real-time delay`}
                    >
                        <span>{isFastForwarding ? '⚡ Running...' : '⚡ Fast Run'}</span>
                    </button>

                    {/* Live Connection Status */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '6px', fontSize: '12px' }}>
                        <span className={`status-dot ${connected ? 'clean' : 'dirty'}`} />
                        <span style={{ color: connected ? '#10b981' : '#f59e0b', fontSize: '11px', fontWeight: 600 }}>
                            {connected ? 'LIVE' : 'CONNECTING'}
                        </span>
                    </div>
                </div>

                {/* Heatmap Legend Box */}
                {showHeatmap && (
                    <div className="sim-legend-box">
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                            <span>Track Usage Heatmap</span>
                            <span style={{ color: '#f59e0b' }}>Congestion</span>
                        </div>
                        <div className="sim-heat-bar" />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
                            <span>Low (Free)</span>
                            <span>Medium</span>
                            <span>High (Jammed)</span>
                        </div>
                    </div>
                )}

                {/* Canvas View Controls (Bottom-Right) */}
                <div className="sim-view-controls">
                    <button 
                        className={`sim-pill-btn ${showHeatmap ? 'active' : ''}`}
                        onClick={() => setShowHeatmap(!showHeatmap)}
                        title="Toggle Traffic & Jam Heatmap"
                    >
                        🔥 Heatmap
                    </button>
                    <button 
                        className={`sim-pill-btn ${showLabels ? 'active' : ''}`}
                        onClick={() => setShowLabels(!showLabels)}
                        title="Toggle Vehicle & Port Labels"
                    >
                        🏷 Labels
                    </button>
                    <button 
                        className="sim-pill-btn"
                        onClick={() => fitViewToTracks(mapData.tracks)}
                        title="Fit View to Map"
                    >
                        ⤢ Center
                    </button>
                </div>

                {/* Simulation Canvas */}
                <div className="canvas-container" style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
                    <canvas 
                        ref={canvasRef}
                        style={{ width: '100%', height: '100%', display: 'block' }}
                    />
                </div>
            </div>

            {/* Sidebar Controls & Real-Time Analytics */}
            <div className="sidebar" style={{ width: '380px', display: 'flex', flexDirection: 'column', gap: '14px', height: '100%', maxHeight: '100%', minHeight: 0, overflowY: 'auto', boxSizing: 'border-box', paddingBottom: '36px', borderLeft: '1px solid #334155', borderRight: 'none' }}>
                
                {/* Sidebar Navigation Tabs */}
                <div style={{ display: 'flex', background: '#0f172a', padding: '4px', borderRadius: '8px', border: '1px solid #334155' }}>
                    <button 
                        className={`sim-pill-btn ${sidebarTab === 'kpi' ? 'active' : ''}`}
                        style={{ flex: 1, justifyContent: 'center' }}
                        onClick={() => setSidebarTab('kpi')}
                    >
                        Analytics
                    </button>
                    <button 
                        className={`sim-pill-btn ${sidebarTab === 'strategies' ? 'active' : ''}`}
                        style={{ flex: 1, justifyContent: 'center' }}
                        onClick={() => setSidebarTab('strategies')}
                    >
                        Strategies
                    </button>
                    <button 
                        className={`sim-pill-btn ${sidebarTab === 'fleet' ? 'active' : ''}`}
                        style={{ flex: 1, justifyContent: 'center' }}
                        onClick={() => setSidebarTab('fleet')}
                    >
                        Fleet ({agents.length})
                    </button>
                    <button 
                        className={`sim-pill-btn ${sidebarTab === 'machines' ? 'active' : ''}`}
                        style={{ flex: 1, justifyContent: 'center' }}
                        onClick={() => setSidebarTab('machines')}
                    >
                        Machines
                    </button>
                </div>

                {/* TAB 1: KPI & REAL-TIME METRICS */}
                {sidebarTab === 'kpi' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flexShrink: 0 }}>
                        {/* Live KPI Cards */}
                        <div className="sim-kpi-grid">
                            <div className="sim-kpi-card green">
                                <span className="sim-kpi-label">Throughput</span>
                                <span className="sim-kpi-value">{metrics.throughput}</span>
                                <span className="sim-kpi-sub">Units Delivered</span>
                            </div>
                            <div className="sim-kpi-card">
                                <span className="sim-kpi-label">Throughput Rate</span>
                                <span className="sim-kpi-value">{metrics.throughput_rate_hr}</span>
                                <span className="sim-kpi-sub">Units / hour</span>
                            </div>
                            <div className="sim-kpi-card amber">
                                <span className="sim-kpi-label">Avg Cycle Time</span>
                                <span className="sim-kpi-value">{metrics.avg_wait_time}s</span>
                                <span className="sim-kpi-sub">Source to Sink</span>
                            </div>
                            <div className="sim-kpi-card purple">
                                <span className="sim-kpi-label">Fleet Avg Utility</span>
                                <span className="sim-kpi-value">{metrics.fleet_avg_utilization}%</span>
                                <div className="sim-bar-bg" style={{ marginTop: '4px' }}>
                                    <div className="sim-bar-fill" style={{ width: `${Math.min(100, metrics.fleet_avg_utilization)}%` }} />
                                </div>
                            </div>
                        </div>

                        {/* Duration Benchmark & Fast-Forward Panel */}
                        <div className="panel">
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h3>⏱️ Duration Benchmark</h3>
                                {benchmarkResults && (
                                    <button 
                                        className="sim-pill-btn"
                                        style={{ fontSize: '11px', padding: '2px 8px', color: '#38bdf8', borderColor: '#0284c7' }}
                                        onClick={() => setShowBenchmarkModal(true)}
                                    >
                                        📊 View Report
                                    </button>
                                )}
                            </div>
                            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '0 0 10px 0' }}>
                                Run simulation to a set duration in fast-forward turbo mode.
                            </p>

                            <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
                                {[60, 180, 300, 600, 1800].map(sec => (
                                    <button
                                        key={sec}
                                        className={`sim-pill-btn ${targetDuration === sec ? 'active' : ''}`}
                                        style={{ flex: 1, padding: '4px 0', fontSize: '11px', justifyContent: 'center' }}
                                        onClick={() => setTargetDuration(sec)}
                                    >
                                        {sec < 60 ? `${sec}s` : `${sec / 60}m`}
                                    </button>
                                ))}
                            </div>

                            <div className="form-row" style={{ marginBottom: '10px' }}>
                                <span>Custom Duration:</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <input 
                                        type="number"
                                        min="5"
                                        max="7200"
                                        step="10"
                                        value={targetDuration}
                                        onChange={e => setTargetDuration(Math.max(1, parseFloat(e.target.value) || 60))}
                                        style={{ width: '70px', padding: '4px 6px', background: '#090d16', border: '1px solid #334155', color: '#38bdf8', borderRadius: '4px', textAlign: 'right' }}
                                    />
                                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>sec</span>
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: '8px' }}>
                                <button 
                                    className="action-btn"
                                    style={{ flex: 1, justifyContent: 'center', background: '#0284c7', borderColor: '#38bdf8' }}
                                    onClick={() => handleFastRun(targetDuration, false)}
                                    disabled={isFastForwarding}
                                    title="Advance from current time in turbo mode"
                                >
                                    {isFastForwarding ? '⚡ Computing...' : `⚡ Fast Run (+${targetDuration}s)`}
                                </button>
                                <button 
                                    className="sim-pill-btn danger"
                                    style={{ flex: 1, justifyContent: 'center' }}
                                    onClick={() => handleFastRun(targetDuration, true)}
                                    disabled={isFastForwarding}
                                    title="Reset simulation to 0 and run to target duration"
                                >
                                    🔄 Reset & Run
                                </button>
                            </div>
                        </div>

                        {/* Top Congestion Bottlenecks */}
                        <div className="panel">
                            <h3>🔥 Top Bottleneck Tracks</h3>
                            {metrics.top_bottlenecks && metrics.top_bottlenecks.length > 0 ? (
                                <table className="sim-table">
                                    <thead>
                                        <tr>
                                            <th>Track ID</th>
                                            <th>Jam Time</th>
                                            <th>Traversals</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {metrics.top_bottlenecks.map(b => (
                                            <tr key={b.seg_id}>
                                                <td style={{ fontWeight: 600, color: '#38bdf8' }}>{b.seg_id}</td>
                                                <td style={{ color: b.jam_seconds > 5 ? '#f87171' : '#fde047' }}>
                                                    {b.jam_seconds}s
                                                </td>
                                                <td>{b.traversals}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : (
                                <div style={{ color: '#64748b', fontSize: '12px', textAlign: 'center', padding: '10px 0' }}>
                                    No traffic jams detected yet.
                                </div>
                            )}
                        </div>

                        {/* Export Reports */}
                        <div className="panel">
                            <h3>📊 Export Reports</h3>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <button 
                                    className="sim-pill-btn" 
                                    style={{ flex: 1, justifyContent: 'center' }}
                                    onClick={() => handleExport('csv')}
                                >
                                    📥 Download CSV
                                </button>
                                <button 
                                    className="sim-pill-btn" 
                                    style={{ flex: 1, justifyContent: 'center' }}
                                    onClick={() => handleExport('json')}
                                >
                                    📥 Download JSON
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* TAB 2: MODULAR STRATEGIES */}
                {sidebarTab === 'strategies' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flexShrink: 0 }}>
                        <div className="panel">
                            <h3>⚡ Modular Strategy Registry</h3>
                            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '0 0 12px 0' }}>
                                Compare algorithm performances in real time. Backpressure and destination reservations remain active across all strategies.
                            </p>

                            {/* Pathfinding */}
                            <div className="form-row">
                                <span>Pathfinding:</span>
                                <select 
                                    value={strategies.pathfinding} 
                                    onChange={e => setStrategies({ ...strategies, pathfinding: e.target.value })}
                                >
                                    <option value="dijkstra">Dijkstra (Shortest)</option>
                                    <option value="congestion_aware">Congestion-Aware</option>
                                </select>
                            </div>

                            {/* Traffic Control */}
                            <div className="form-row">
                                <span>Traffic Control:</span>
                                <select 
                                    value={strategies.traffic} 
                                    onChange={e => setStrategies({ ...strategies, traffic: e.target.value })}
                                >
                                    <option value="block_reservation">Block Reservation</option>
                                    <option value="kinematic_merge">Kinematic Merge</option>
                                </select>
                            </div>

                            {/* Vehicle Dispatch */}
                            <div className="form-row">
                                <span>Vehicle Dispatch:</span>
                                <select 
                                    value={strategies.vehicle_assignment} 
                                    onChange={e => setStrategies({ ...strategies, vehicle_assignment: e.target.value })}
                                >
                                    <option value="nearest">Nearest Idle</option>
                                    <option value="fifo">FIFO Assignment</option>
                                </select>
                            </div>

                            {/* Machine Allocation */}
                            <div className="form-row">
                                <span>Machine Allocation:</span>
                                <select 
                                    value={strategies.machine_allocation} 
                                    onChange={e => setStrategies({ ...strategies, machine_allocation: e.target.value })}
                                >
                                    <option value="least_loaded">Least Loaded</option>
                                    <option value="closest">Closest Downstream</option>
                                    <option value="round_robin">Round Robin</option>
                                </select>
                            </div>

                            {/* Idle Strategy */}
                            <div className="form-row">
                                <span>Idle Strategy:</span>
                                <select 
                                    value={strategies.idle_strategy || "stay_and_nudge"} 
                                    onChange={e => setStrategies({ ...strategies, idle_strategy: e.target.value })}
                                >
                                    <option value="stay_and_nudge">Stay & Nudge (Park & Yield)</option>
                                    <option value="cruising">Continuous Cruising</option>
                                </select>
                            </div>

                            <button 
                                className="action-btn"
                                style={{ width: '100%', marginTop: '14px' }}
                                onClick={applySimulationConfig}
                                disabled={isApplyingConfig}
                            >
                                {isApplyingConfig ? 'Applying...' : 'Apply Strategies'}
                            </button>
                        </div>

                        {/* OHT Vehicle Specifications */}
                        <div className="panel">
                            <h3>⚙️ OHT Vehicle Specifications</h3>
                            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '0 0 10px 0' }}>
                                Physical dimensions and dynamic motor limits applied across the fleet.
                            </p>

                            <div className="form-row">
                                <span>OHT Length:</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <input 
                                        type="number" 
                                        step="0.1" 
                                        min="0.5" 
                                        max="3.0"
                                        value={ohtSpecs.length_m !== undefined ? ohtSpecs.length_m : 1.0}
                                        onChange={e => setOhtSpecs({ ...ohtSpecs, length_m: parseFloat(e.target.value) || 1.0 })}
                                        style={{ width: '65px', padding: '3px 6px', background: '#0f172a', border: '1px solid #334155', color: '#38bdf8', borderRadius: '4px', textAlign: 'right' }}
                                    />
                                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>m</span>
                                </div>
                            </div>

                            <div className="form-row">
                                <span>Safety Buffer:</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <input 
                                        type="number" 
                                        step="0.05" 
                                        min="0.05" 
                                        max="1.0"
                                        value={ohtSpecs.buffer_m !== undefined ? ohtSpecs.buffer_m : 0.2}
                                        onChange={e => setOhtSpecs({ ...ohtSpecs, buffer_m: parseFloat(e.target.value) || 0.2 })}
                                        style={{ width: '65px', padding: '3px 6px', background: '#0f172a', border: '1px solid #334155', color: '#38bdf8', borderRadius: '4px', textAlign: 'right' }}
                                    />
                                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>m</span>
                                </div>
                            </div>

                            <div className="form-row">
                                <span>Max Speed:</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <input 
                                        type="number" 
                                        step="0.1" 
                                        min="0.5" 
                                        max="4.0"
                                        value={ohtSpecs.speed_max ? (ohtSpecs.speed_max / 1000.0).toFixed(1) : "2.0"}
                                        onChange={e => setOhtSpecs({ ...ohtSpecs, speed_max: (parseFloat(e.target.value) || 2.0) * 1000.0 })}
                                        style={{ width: '65px', padding: '3px 6px', background: '#0f172a', border: '1px solid #334155', color: '#38bdf8', borderRadius: '4px', textAlign: 'right' }}
                                    />
                                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>m/s</span>
                                </div>
                            </div>

                            <div className="form-row">
                                <span>Acceleration:</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <input 
                                        type="number" 
                                        step="0.1" 
                                        min="0.5" 
                                        max="3.0"
                                        value={ohtSpecs.accel ? (ohtSpecs.accel / 1000.0).toFixed(1) : "1.5"}
                                        onChange={e => setOhtSpecs({ ...ohtSpecs, accel: (parseFloat(e.target.value) || 1.5) * 1000.0 })}
                                        style={{ width: '65px', padding: '3px 6px', background: '#0f172a', border: '1px solid #334155', color: '#38bdf8', borderRadius: '4px', textAlign: 'right' }}
                                    />
                                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>m/s²</span>
                                </div>
                            </div>

                            <div className="form-row">
                                <span>Deceleration:</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <input 
                                        type="number" 
                                        step="0.1" 
                                        min="0.5" 
                                        max="4.0"
                                        value={ohtSpecs.decel ? (ohtSpecs.decel / 1000.0).toFixed(1) : "2.0"}
                                        onChange={e => setOhtSpecs({ ...ohtSpecs, decel: (parseFloat(e.target.value) || 2.0) * 1000.0 })}
                                        style={{ width: '65px', padding: '3px 6px', background: '#0f172a', border: '1px solid #334155', color: '#38bdf8', borderRadius: '4px', textAlign: 'right' }}
                                    />
                                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>m/s²</span>
                                </div>
                            </div>

                            <button 
                                className="action-btn"
                                style={{ width: '100%', marginTop: '10px' }}
                                onClick={applySimulationConfig}
                                disabled={isApplyingConfig}
                            >
                                {isApplyingConfig ? 'Saving Specs...' : 'Save OHT Specifications'}
                            </button>
                        </div>

                        {/* Fleet Size Controller */}
                        <div className="panel">
                            <h3>🚗 Fleet Configuration</h3>
                            <div className="form-row">
                                <span>Fleet Count:</span>
                                <span style={{ fontWeight: 700, color: '#38bdf8' }}>{fleetSize} Vehicles</span>
                            </div>
                            <input 
                                type="range" 
                                min="1" 
                                max="20" 
                                value={fleetSize}
                                onChange={e => setFleetSize(parseInt(e.target.value))}
                                style={{ width: '100%', marginTop: '10px' }}
                            />

                            <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                                <button 
                                    className="action-btn" 
                                    style={{ flex: 1 }}
                                    onClick={applySimulationConfig}
                                >
                                    Update Fleet Size
                                </button>
                                <button 
                                    className="sim-pill-btn danger" 
                                    style={{ flex: 1, justifyContent: 'center' }}
                                    onClick={reinitSimulation}
                                    title="Reload factory state with new fleet and active map"
                                >
                                    Restart Sim
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* TAB 3: OHT FLEET STATUS */}
                {sidebarTab === 'fleet' && (
                    <div className="panel" style={{ flexShrink: 0 }}>
                        <h3>🚗 Fleet Overview ({agents.length} Vehicles)</h3>
                        <table className="sim-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>State</th>
                                    <th>Speed</th>
                                    <th>Cargo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {agents.map(ag => (
                                    <tr key={ag.id}>
                                        <td style={{ fontWeight: 700, color: '#38bdf8' }}>{ag.id}</td>
                                        <td>
                                            <span className={`state-badge ${ag.state}`}>
                                                {ag.state.replace('MOVING_TO_', '')}
                                            </span>
                                        </td>
                                        <td>{ag.speed.toFixed(1)}m/s</td>
                                        <td>
                                            {ag.cargo ? (
                                                <span style={{ color: '#fbbf24', fontWeight: 600 }}>FOUP</span>
                                            ) : (
                                                <span style={{ color: '#64748b' }}>Empty</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* TAB 4: MACHINES & BACKPRESSURE */}
                {sidebarTab === 'machines' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flexShrink: 0 }}>
                        {/* Machine State Time Distribution Donut/Pie Chart */}
                        <div className="panel">
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                <h3>🥧 State Time Distribution</h3>
                            </div>

                            {/* Machine Selector */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                                <span style={{ fontSize: '11px', color: '#94a3b8' }}>Target:</span>
                                <select
                                    value={selectedMachinePie}
                                    onChange={e => setSelectedMachinePie(e.target.value)}
                                    style={{
                                        background: '#090d16',
                                        border: '1px solid #334155',
                                        color: '#38bdf8',
                                        borderRadius: '4px',
                                        padding: '3px 8px',
                                        fontSize: '11px',
                                        maxWidth: '190px'
                                    }}
                                >
                                    <option value="ALL">🏭 All Machines (Factory Total)</option>
                                    {machines.map(m => (
                                        <option key={m.id} value={m.id}>
                                            {m.name || m.id} ({m.role.toUpperCase()})
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {(() => {
                                const machList = metrics.machines || [];
                                const totalAct = machList.reduce((acc, mm) => acc + (mm.active_time || 0), 0);
                                const totalBlk = machList.reduce((acc, mm) => acc + (mm.blocked_time || 0), 0);
                                const totalStr = machList.reduce((acc, mm) => acc + (mm.starved_time || 0), 0);

                                const curM = selectedMachinePie !== "ALL"
                                    ? machList.find(mm => mm.id === selectedMachinePie)
                                    : null;

                                const actT = curM ? (curM.active_time || 0) : totalAct;
                                const blkT = curM ? (curM.blocked_time || 0) : totalBlk;
                                const strT = curM ? (curM.starved_time || 0) : totalStr;
                                const totT = actT + blkT + strT;

                                const pAct = totT > 0 ? ((actT / totT) * 100).toFixed(1) : "0.0";
                                const pBlk = totT > 0 ? ((blkT / totT) * 100).toFixed(1) : "0.0";
                                const pStr = totT > 0 ? ((strT / totT) * 100).toFixed(1) : (totT === 0 ? "100.0" : "0.0");

                                return (
                                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                        {/* Donut Chart SVG */}
                                        <div style={{ width: '180px', height: '150px', position: 'relative' }}>
                                            <svg viewBox="0 0 180 150" width="100%" height="100%">
                                                {renderDonutSlices(actT, blkT, strT, pieHoverSlice, setPieHoverSlice)}
                                                <text x="90" y="70" textAnchor="middle" fill="#f8fafc" fontSize="15" fontWeight="bold">
                                                    {pAct}%
                                                </text>
                                                <text x="90" y="84" textAnchor="middle" fill="#94a3b8" fontSize="8" fontWeight="600">
                                                    ACTIVE UTIL
                                                </text>
                                            </svg>
                                        </div>

                                        {/* Interactive Hover Tooltip */}
                                        <div style={{ minHeight: '18px', fontSize: '11px', textAlign: 'center', marginTop: '2px', color: pieHoverSlice ? pieHoverSlice.color : '#94a3b8', fontWeight: 600 }}>
                                            {pieHoverSlice 
                                                ? `${pieHoverSlice.label}: ${pieHoverSlice.value.toFixed(1)}s (${pieHoverSlice.pct}%)`
                                                : (selectedMachinePie === "ALL" ? "Factory Aggregate State Time" : `${curM ? (curM.name || curM.id) : selectedMachinePie} State Time`)
                                            }
                                        </div>

                                        {/* Legend Chips */}
                                        <div style={{ display: 'flex', gap: '8px', marginTop: '8px', width: '100%', justifyContent: 'space-between', fontSize: '10px' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />
                                                <span style={{ color: '#cbd5e1' }}>Active: <b>{pAct}%</b></span>
                                            </div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
                                                <span style={{ color: '#cbd5e1' }}>Blocked: <b>{pBlk}%</b></span>
                                            </div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#64748b', display: 'inline-block' }} />
                                                <span style={{ color: '#cbd5e1' }}>Starved: <b>{pStr}%</b></span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })()}
                        </div>

                        {/* Machine Cards List */}
                        <div className="panel">
                            <h3>🏭 Machine Status & Backpressure</h3>
                            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '0 0 10px 0' }}>
                                Click a machine to focus pie chart. Machines pause when downstream ports are full.
                            </p>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                {machines.map(m => {
                                    const machMetric = metrics.machines ? metrics.machines.find(mm => mm.id === m.id) : null;
                                    const utilRate = machMetric ? machMetric.utilization_rate : 0;
                                    const mAct = machMetric ? (machMetric.active_time || 0) : 0;
                                    const mBlk = machMetric ? (machMetric.blocked_time || 0) : 0;
                                    const mStr = machMetric ? (machMetric.starved_time || 0) : 0;
                                    const mTot = mAct + mBlk + mStr;
                                    const mActPct = mTot > 0 ? (mAct / mTot) * 100 : 0;
                                    const mBlkPct = mTot > 0 ? (mBlk / mTot) * 100 : 0;
                                    const mStrPct = mTot > 0 ? (mStr / mTot) * 100 : (mTot === 0 ? 100 : 0);
                                    const isSelected = selectedMachinePie === m.id;

                                    return (
                                        <div 
                                            key={m.id} 
                                            onClick={() => setSelectedMachinePie(selectedMachinePie === m.id ? "ALL" : m.id)}
                                            style={{ 
                                                background: '#090d16', 
                                                border: isSelected ? '1.5px solid #38bdf8' : '1px solid #1e293b', 
                                                borderRadius: '8px', 
                                                padding: '10px',
                                                cursor: 'pointer',
                                                transition: 'border-color 0.15s'
                                            }}
                                            title="Click to view state distribution in pie chart"
                                        >
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <div>
                                                    <span style={{ fontWeight: 700, color: isSelected ? '#38bdf8' : '#f8fafc' }}>
                                                        {m.name || m.id}
                                                    </span>
                                                    <span style={{ fontSize: '11px', color: '#94a3b8', marginLeft: '6px' }}>
                                                        ({m.role.toUpperCase()})
                                                    </span>
                                                </div>
                                                <span className={`state-badge ${m.state}`}>
                                                    {m.state === 'PAUSED_BACKPRESSURE' ? 'BACKPRESSURE' : m.state}
                                                </span>
                                            </div>

                                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginTop: '8px', color: '#cbd5e1' }}>
                                                <span>Processed: <b>{m.processed_count}</b></span>
                                                <span>Utilization: <b>{utilRate}%</b></span>
                                            </div>

                                            {/* Segmented State Time Distribution Bar */}
                                            <div style={{ display: 'flex', height: '6px', borderRadius: '3px', overflow: 'hidden', background: '#334155', marginTop: '6px' }}>
                                                <div style={{ width: `${mActPct}%`, background: '#10b981' }} title={`Active: ${mAct.toFixed(1)}s (${mActPct.toFixed(1)}%)`} />
                                                <div style={{ width: `${mBlkPct}%`, background: '#f59e0b' }} title={`Blocked: ${mBlk.toFixed(1)}s (${mBlkPct.toFixed(1)}%)`} />
                                                <div style={{ width: `${mStrPct}%`, background: '#64748b' }} title={`Starved: ${mStr.toFixed(1)}s (${mStrPct.toFixed(1)}%)`} />
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                )}

            </div>

            {/* Simulation Benchmark & Statistics Report Modal */}
            {showBenchmarkModal && benchmarkResults && (
                <div 
                    className="modal-overlay" 
                    onClick={() => setShowBenchmarkModal(false)}
                    style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                    <div 
                        className="modal-box" 
                        onClick={e => e.stopPropagation()}
                        style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '12px', width: '92%', maxWidth: '820px', maxHeight: '88vh', overflowY: 'auto', padding: '24px', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1e293b', paddingBottom: '12px', marginBottom: '16px' }}>
                            <div>
                                <h2 style={{ margin: 0, color: '#f8fafc', fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <span>⏱️ Simulation Duration Benchmark</span>
                                    <span style={{ fontSize: '12px', background: '#0284c7', color: '#fff', padding: '2px 8px', borderRadius: '12px' }}>
                                        {benchmarkResults.sim_time ? benchmarkResults.sim_time.toFixed(1) : 0}s Simulated
                                    </span>
                                </h2>
                                <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#94a3b8' }}>
                                    Comprehensive analytical performance metrics collected during the run.
                                </p>
                            </div>
                            <button 
                                onClick={() => setShowBenchmarkModal(false)}
                                style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '20px', cursor: 'pointer', padding: '4px 8px' }}
                            >
                                ✕
                            </button>
                        </div>

                        {/* Top KPI Cards */}
                        <div className="sim-kpi-grid" style={{ marginBottom: '16px' }}>
                            <div className="sim-kpi-card green">
                                <span className="sim-kpi-label">Throughput</span>
                                <span className="sim-kpi-value">{benchmarkResults.summary?.throughput || 0}</span>
                                <span className="sim-kpi-sub">Units Finished</span>
                            </div>
                            <div className="sim-kpi-card">
                                <span className="sim-kpi-label">Throughput Rate</span>
                                <span className="sim-kpi-value">{benchmarkResults.summary?.throughput_rate_hr || 0}</span>
                                <span className="sim-kpi-sub">Units / hour</span>
                            </div>
                            <div className="sim-kpi-card amber">
                                <span className="sim-kpi-label">Avg Wait / Cycle Time</span>
                                <span className="sim-kpi-value">{(benchmarkResults.summary?.avg_wait_time || 0).toFixed(1)}s</span>
                                <span className="sim-kpi-sub">Lot Cycle Duration</span>
                            </div>
                            <div className="sim-kpi-card purple">
                                <span className="sim-kpi-label">Fleet Avg Utility</span>
                                <span className="sim-kpi-value">{benchmarkResults.summary?.fleet_avg_utilization || 0}%</span>
                                <span className="sim-kpi-sub">Active Working %</span>
                            </div>
                        </div>

                        {/* Machine State Breakdown Section with Donut Chart */}
                        <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
                            <h3 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#f8fafc' }}>
                                🏭 Machine State Time Distribution
                            </h3>
                            <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
                                {/* Donut Chart */}
                                <div style={{ width: '160px', height: '140px', flexShrink: 0 }}>
                                    {(() => {
                                        const bMachines = benchmarkResults.summary?.machines || [];
                                        const bAct = bMachines.reduce((acc, m) => acc + (m.active_time || 0), 0);
                                        const bBlk = bMachines.reduce((acc, m) => acc + (m.blocked_time || 0), 0);
                                        const bStr = bMachines.reduce((acc, m) => acc + (m.starved_time || 0), 0);
                                        const bTot = bAct + bBlk + bStr;
                                        return (
                                            <svg viewBox="0 0 180 150" width="100%" height="100%">
                                                {renderDonutSlices(bAct, bBlk, bStr, null, null)}
                                                <text x="90" y="70" textAnchor="middle" fill="#f8fafc" fontSize="15" fontWeight="bold">
                                                    {bTot > 0 ? ((bAct / bTot) * 100).toFixed(1) : 0}%
                                                </text>
                                                <text x="90" y="84" textAnchor="middle" fill="#94a3b8" fontSize="8" fontWeight="600">
                                                    UTILIZATION
                                                </text>
                                            </svg>
                                        );
                                    })()}
                                </div>

                                {/* Machine Detail Table */}
                                <div style={{ flex: 1, minWidth: '280px', overflowX: 'auto' }}>
                                    <table className="sim-table" style={{ fontSize: '11px' }}>
                                        <thead>
                                            <tr>
                                                <th>Machine</th>
                                                <th>Role</th>
                                                <th>Processed</th>
                                                <th>Active (s)</th>
                                                <th>Blocked (s)</th>
                                                <th>Starved (s)</th>
                                                <th>Util %</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(benchmarkResults.summary?.machines || []).map(bm => (
                                                <tr key={bm.id}>
                                                    <td style={{ fontWeight: 600, color: '#38bdf8' }}>{bm.name || bm.id}</td>
                                                    <td>{bm.role.toUpperCase()}</td>
                                                    <td><b>{bm.processed_count}</b></td>
                                                    <td style={{ color: '#10b981' }}>{(bm.active_time || 0).toFixed(1)}s</td>
                                                    <td style={{ color: '#f59e0b' }}>{(bm.blocked_time || 0).toFixed(1)}s</td>
                                                    <td style={{ color: '#94a3b8' }}>{(bm.starved_time || 0).toFixed(1)}s</td>
                                                    <td style={{ fontWeight: 600 }}>{bm.utilization_rate}%</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>

                        {/* Fleet Breakdown Table */}
                        <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
                            <h3 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#f8fafc' }}>
                                🚗 OHT Fleet Performance Breakdown
                            </h3>
                            <div style={{ overflowX: 'auto' }}>
                                <table className="sim-table" style={{ fontSize: '11px' }}>
                                    <thead>
                                        <tr>
                                            <th>Vehicle ID</th>
                                            <th>Loaded Travel (s)</th>
                                            <th>Empty Travel (s)</th>
                                            <th>Traffic Waiting (s)</th>
                                            <th>Idle (s)</th>
                                            <th>Total Dist (m)</th>
                                            <th>Utility %</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(benchmarkResults.summary?.agents || []).map(ba => (
                                            <tr key={ba.id}>
                                                <td style={{ fontWeight: 700, color: '#38bdf8' }}>{ba.id}</td>
                                                <td style={{ color: '#fbbf24' }}>{(ba.loaded_time || 0).toFixed(1)}s</td>
                                                <td style={{ color: '#38bdf8' }}>{(ba.empty_time || 0).toFixed(1)}s</td>
                                                <td style={{ color: '#f97316' }}>{(ba.waiting_traffic_time || 0).toFixed(1)}s</td>
                                                <td style={{ color: '#64748b' }}>{(ba.idle_time || 0).toFixed(1)}s</td>
                                                <td>{(ba.total_distance_m || 0).toFixed(1)}m</td>
                                                <td style={{ fontWeight: 600 }}>{ba.utilization_rate}%</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* Modal Actions */}
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', borderTop: '1px solid #1e293b', paddingTop: '16px' }}>
                            <button
                                className="sim-pill-btn"
                                onClick={() => handleExport('csv')}
                                style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                            >
                                📥 Export CSV
                            </button>
                            <button
                                className="sim-pill-btn"
                                onClick={() => handleExport('json')}
                                style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                            >
                                📥 Export JSON
                            </button>
                            <button
                                className="action-btn"
                                onClick={() => setShowBenchmarkModal(false)}
                                style={{ background: '#334155' }}
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}

            </div>
    );
}
