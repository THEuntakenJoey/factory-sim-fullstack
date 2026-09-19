const { useState, useEffect, useRef } = React;

function MapBuilderTab({ project, schemas, recipes, onMapChange, activeMapName, setActiveMapName, onSaveProject }) {
    const [builderState, setBuilderState] = useState({
        activeTool: "STRAIGHT",
        toolHeading: 0,
        selectedTrack: null,
        selectedMachine: null,
        trackCount: 0,
        machineSchema: ""
    });

    const [metrics, setMetrics] = useState({ throughput: 0, active_vehicles: 0, average_wait_time: 0 });
    const [verifyResults, setVerifyResults] = useState(null);
    const canvasRef = useRef(null);
    const [mapList, setMapList] = useState([]);
    const [selectedMap, setSelectedMap] = useState(activeMapName || "map.json");

    // Keep activeMapName in sync
    useEffect(() => {
        if (activeMapName && activeMapName !== selectedMap) {
            setSelectedMap(activeMapName);
        }
    }, [activeMapName]);

    const fetchMaps = () => {
        window.API.listMaps(project).then(maps => {
            const list = maps || [];
            setMapList(list);
            if (list.length > 0) {
                const current = (activeMapName && list.includes(activeMapName)) ? activeMapName : list[0];
                setSelectedMap(current);
                if (setActiveMapName) setActiveMapName(current);
            }
        }).catch(e => console.error("Failed to list maps", e));
    };

    useEffect(() => {
        fetchMaps();
    }, [project]);

    useEffect(() => {
        // Initialize Map Builder on canvas
        if (canvasRef.current && window.Builder) {
            window.Builder.init(canvasRef.current);
            window.Builder.setProjectSchemas(schemas); // pass schemas down
            
            // Connect change listener for dirty tracking
            window.Builder.onChange = () => {
                if (onMapChange) onMapChange();
            };

            const renderLoop = () => {
                setBuilderState(prev => ({
                    ...prev,
                    selectedTrack: window.Builder.tracks.find(t => t.id === window.Builder.selectedTrackId) || null,
                    selectedMachine: window.Builder.machines.find(m => m.id === window.Builder.selectedMachineId) || null,
                    trackCount: window.Builder.tracks.length,
                    activeTool: window.Builder.activeTool,
                    toolHeading: window.Builder.toolHeading
                }));
                requestAnimationFrame(renderLoop);
            };
            renderLoop();
            
            // Load default map for this project
            const targetMap = activeMapName || 'map.json';
            window.API.loadMap(project, targetMap).then(data => {
                if (data && !data.error) window.Builder.loadGraph(data);
            }).catch(e => console.log("Map not found, starting fresh."));
        }
    }, [project]);

    // Push schemas down whenever they change
    useEffect(() => {
        if (window.Builder) window.Builder.setProjectSchemas(schemas);
    }, [schemas]);

    const setTool = (t) => {
        window.Builder.setTool(t === 'SELECT' ? null : t);
        setBuilderState(prev => ({ ...prev, activeTool: t === 'SELECT' ? null : t }));
    };

    const handleSave = async () => {
        if (onSaveProject) {
            await onSaveProject();
            fetchMaps();
            return;
        }
        const graph = window.Builder.saveGraph();
        try {
            await window.API.saveMap(project, selectedMap || 'map.json', graph);
            alert(`Saved map to ${selectedMap || 'map.json'}`);
            if (window.Builder) window.Builder.isDirty = false;
            fetchMaps();
        } catch (e) {
            alert("Error saving map: " + e.message);
        }
    };

    const handleVerify = async () => {
        const res = window.Builder.verifyMap();
        setVerifyResults(res);
        if (res.errors.length === 0) {
            alert("Map is valid!" + (res.warnings.length ? ` (${res.warnings.length} warnings)` : ""));
        } else {
            alert(`Map has ${res.errors.length} errors and ${res.warnings.length} warnings.`);
        }
        window.Builder._notify();
    };

    return (
        <div style={{ display: 'flex', width: '100%', height: '100%' }}>
            <div className="sidebar">
                <div className="panel">
                    <h3>Tools</h3>
                    <div className="tool-grid">
                        <button className={`tool-btn ${builderState.activeTool === 'SELECT' ? 'active' : ''}`} onClick={() => setTool('SELECT')}>
                            <span style={{fontSize: '18px'}}>↖</span> Select
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'STRAIGHT' ? 'active' : ''}`} onClick={() => setTool('STRAIGHT')}>
                            <span style={{fontSize: '18px'}}>↑</span> Straight
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'TURN_L' ? 'active' : ''}`} onClick={() => setTool('TURN_L')}>
                            <span style={{fontSize: '18px'}}>↖</span> Turn L
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'TURN_R' ? 'active' : ''}`} onClick={() => setTool('TURN_R')}>
                            <span style={{fontSize: '18px'}}>↗</span> Turn R
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'DIVERGE_L' ? 'active' : ''}`} onClick={() => setTool('DIVERGE_L')}>
                            <span style={{fontSize: '18px'}}>Y</span> Div L
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'DIVERGE_R' ? 'active' : ''}`} onClick={() => setTool('DIVERGE_R')}>
                            <span style={{fontSize: '18px'}}>Y</span> Div R
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'MERGE_L' ? 'active' : ''}`} onClick={() => setTool('MERGE_L')}>
                            <span style={{fontSize: '18px'}}>⑃</span> Merge L
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'MERGE_R' ? 'active' : ''}`} onClick={() => setTool('MERGE_R')}>
                            <span style={{fontSize: '18px'}}>⑃</span> Merge R
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'MACHINE' ? 'active' : ''}`} onClick={() => setTool('MACHINE')}>
                            <span style={{fontSize: '18px'}}>■</span> Machine
                        </button>
                    </div>
                </div>

                {builderState.activeTool === 'MACHINE' && (
                    <div className="panel">
                        <h3>Machine Placement</h3>
                        <div className="form-row">
                            <span>Schema:</span>
                            <select 
                                value={builderState.machineSchema} 
                                onChange={e => {
                                    setBuilderState(p => ({...p, machineSchema: e.target.value}));
                                    window.Builder.setMachineSchema(e.target.value);
                                }}
                                style={{width: '100%'}}
                            >
                                <option value="">-- Select Schema --</option>
                                {Object.values(schemas).map(s => (
                                    <option key={s.id} value={s.id}>{s.id}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                )}

                {(builderState.activeTool === 'STRAIGHT' || (builderState.selectedTrack && builderState.selectedTrack.type === 'STRAIGHT')) && (
                    <div className="panel">
                        <h3>Straight Track Settings</h3>
                        <div className="form-row">
                            <span>Length:</span>
                            <input 
                                type="number" 
                                step="0.1" 
                                min="0.2" 
                                max="20.0"
                                value={builderState.selectedTrack ? builderState.selectedTrack.length : (window.Builder.straightLength || 1.0)} 
                                onChange={e => {
                                    const val = parseFloat(e.target.value);
                                    if (builderState.selectedTrack) {
                                        window.Builder.setStraightLength(builderState.selectedTrack.id, val);
                                    } else {
                                        window.Builder.straightLength = val;
                                        setBuilderState(prev => ({...prev}));
                                    }
                                }}
                                style={{width: '80px', textAlign: 'right'}}
                            />
                        </div>
                    </div>
                )}

                <div className="panel">
                    <h3>Map Actions</h3>
                    <div className="btn-group">
                        <button className="action-btn" onClick={handleSave}>Save</button>
                        <button className="action-btn" onClick={() => {
                            const name = prompt("Enter map name to save as:");
                            if (name && name.trim()) {
                                const cleanName = name.trim().endsWith('.json') ? name.trim() : name.trim() + '.json';
                                const graph = window.Builder.saveGraph();
                                window.API.saveMap(project, cleanName, graph).then(() => {
                                    alert(`Saved map to ${cleanName}`);
                                    setSelectedMap(cleanName);
                                    if (setActiveMapName) setActiveMapName(cleanName);
                                    if (window.Builder) window.Builder.isDirty = false;
                                    fetchMaps();
                                }).catch(e => alert("Error saving map: " + e));
                            }
                        }}>Save As</button>
                        <button className="action-btn" onClick={() => {
                            if (confirm("Are you sure you want to clear the map?")) {
                                window.Builder.clear();
                            }
                        }} style={{background: '#ef4444'}}>Clear</button>
                        <button className="action-btn" onClick={handleVerify} style={{background: '#059669'}}>Verify</button>
                    </div>
                    <div className="form-row" style={{marginTop: '8px', gap: '8px', justifyContent: 'flex-start'}}>
                        <select 
                            value={selectedMap} 
                            onChange={e => {
                                setSelectedMap(e.target.value);
                                if (setActiveMapName) setActiveMapName(e.target.value);
                            }}
                            style={{flex: 1}}
                        >
                            {mapList.map(m => (
                                <option key={m} value={m}>{m}</option>
                            ))}
                        </select>
                        <button className="action-btn" onClick={() => {
                            if (selectedMap) {
                                window.API.loadMap(project, selectedMap)
                                    .then(data => { 
                                        window.Builder.loadGraph(data); 
                                        if (setActiveMapName) setActiveMapName(selectedMap);
                                        alert(`Loaded ${selectedMap}`); 
                                    })
                                    .catch(e => alert("Error loading map: " + e));
                            }
                        }}>Load</button>
                    </div>
                </div>

                {builderState.selectedMachine && (
                    <div className="panel">
                        <h3>Selected Machine</h3>
                        <div className="form-row">
                            <span>Type:</span>
                            <span style={{fontWeight: 'bold'}}>{builderState.selectedMachine.schema_id || builderState.selectedMachine.type}</span>
                        </div>
                        <div className="form-row">
                            <span>Heading:</span>
                            <span style={{fontWeight: 'bold'}}>{builderState.selectedMachine.heading || 0}°</span>
                        </div>
                        <div className="form-row">
                            <span>Connected Ports:</span>
                            <span style={{fontWeight: 'bold'}}>{builderState.selectedMachine.connected_ports?.length || 0}</span>
                        </div>
                        <div className="form-row" style={{marginTop: '8px'}}>
                            <button className="action-btn" onClick={() => window.Builder.rotateSelected()} style={{width: '100%'}}>
                                Rotate 90°
                            </button>
                        </div>
                    </div>
                )}

                <div className="panel" style={{marginTop: 'auto'}}>
                    <h3>Stats</h3>
                    <div className="form-row">
                        <span>Total Tracks:</span>
                        <span className="metric-value" style={{fontSize: '16px'}}>{builderState.trackCount}</span>
                    </div>
                </div>
            </div>

            <div className="main-content">
                <div className="helper-banner">
                    <span className="helper-item"><b>Left Drag:</b> Move Object / Pan</span>
                    <span className="helper-item"><b>Right Click / R:</b> Rotate</span>
                    <span className="helper-item"><b>Scroll:</b> Zoom</span>
                    <span className="helper-item"><b>ESC:</b> Deselect / Cancel Drag</span>
                    <span className="helper-item"><b>Del:</b> Delete</span>
                </div>
                <div className="canvas-container">
                    <canvas ref={canvasRef}></canvas>
                </div>
            </div>
        </div>
    );
}