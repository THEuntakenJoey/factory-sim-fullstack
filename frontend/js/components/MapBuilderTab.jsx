const { useState, useEffect, useRef } = React;

function MapBuilderTab({ project, schemas }) {
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

    useEffect(() => {
        // Initialize Map Builder on canvas
        if (canvasRef.current && window.Builder) {
            window.Builder.init(canvasRef.current);
            window.Builder.setProjectSchemas(schemas); // pass schemas down
            
            const renderLoop = () => {
                setBuilderState(prev => ({
                    ...prev,
                    selectedTrack: window.Builder.getSelectedTrack(),
                    selectedMachine: window.Builder.getSelectedMachine(),
                    trackCount: window.Builder.getTrackCount(),
                    activeTool: window.Builder.getActiveTool(),
                    toolHeading: window.Builder.getToolHeading()
                }));
                requestAnimationFrame(renderLoop);
            };
            renderLoop();
            
            // Load map for this project
            window.API.request(`/api/maps/${project}.json`).then(data => {
                if (data && !data.error) window.Builder.loadGraph(data);
            }).catch(e => console.log("Map not found, starting fresh."));
        }
    }, [project]);

    // Push schemas down whenever they change
    useEffect(() => {
        if (window.Builder) window.Builder.setProjectSchemas(schemas);
    }, [schemas]);

    const setTool = (t) => {
        window.Builder.setActiveTool(t);
        setBuilderState(prev => ({ ...prev, activeTool: t }));
    };

    const handleSave = async () => {
        const graph = window.Builder.saveGraph();
        await window.API.request(`/api/save_map/${project}`, {
            method: 'POST',
            body: JSON.stringify(graph)
        });
        alert(`Saved map to ${project}.json`);
    };

    const handleVerify = async () => {
        const graph = window.Builder.saveGraph();
        const res = await window.API.verifyGraph(graph);
        setVerifyResults(res);
        if (res.is_valid) {
            window.Builder.clearErrors();
            alert("Map is valid!");
        } else {
            window.Builder.highlightErrors(res.errored_pieces, res.loose_ends);
            alert(`Map has ${res.errored_pieces.length} overlap errors and ${res.loose_ends.length} loose ends.`);
        }
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
                        <button className={`tool-btn ${builderState.activeTool === 'CURVE' ? 'active' : ''}`} onClick={() => setTool('CURVE')}>
                            <span style={{fontSize: '18px'}}>↗</span> Curve
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'DIVERGE' ? 'active' : ''}`} onClick={() => setTool('DIVERGE')}>
                            <span style={{fontSize: '18px'}}>Y</span> Diverge
                        </button>
                        <button className={`tool-btn ${builderState.activeTool === 'MERGE' ? 'active' : ''}`} onClick={() => setTool('MERGE')}>
                            <span style={{fontSize: '18px'}}>⑃</span> Merge
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

                <div className="panel">
                    <h3>Map Actions</h3>
                    <div className="btn-group">
                        <button className="action-btn" onClick={handleSave}>Save</button>
                        <button className="action-btn" onClick={handleVerify} style={{background: '#059669'}}>Verify</button>
                    </div>
                </div>

                {builderState.selectedMachine && (
                    <div className="panel">
                        <h3>Selected Machine</h3>
                        <div className="form-row">
                            <span>Type:</span>
                            <span style={{fontWeight: 'bold'}}>{builderState.selectedMachine.type}</span>
                        </div>
                        <div className="form-row">
                            <span>Heading:</span>
                            <span style={{fontWeight: 'bold'}}>{builderState.selectedMachine.heading}°</span>
                        </div>
                        <div className="form-row">
                            <span>Connected Ports:</span>
                            <span style={{fontWeight: 'bold'}}>{builderState.selectedMachine.connected_ports?.length || 0}</span>
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
                    <span className="helper-item"><b>Right Click:</b> Rotate</span>
                    <span className="helper-item"><b>Scroll:</b> Zoom</span>
                    <span className="helper-item"><b>Left Click / Middle Drag:</b> Pan</span>
                    <span className="helper-item"><b>ESC:</b> Deselect</span>
                </div>
                <div className="canvas-container">
                    <canvas ref={canvasRef}></canvas>
                </div>
            </div>
        </div>
    );
}