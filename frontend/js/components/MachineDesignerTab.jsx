const { useState } = React;

function MachineDesignerTab({ schemas, saveSchemas, recipes = {} }) {
    const [selectedId, setSelectedId] = useState(null);
    const [newId, setNewId] = useState("");
    const [previewPort, setPreviewPort] = useState(null);

    const handleCreate = () => {
        if (!newId.trim() || schemas[newId.trim()]) return;
        const updated = { 
            ...schemas, 
            [newId.trim()]: { 
                id: newId.trim(),
                width: 2, height: 2, ports: [],
                capacity: 1, process_mode: 'batch', intake_mode: 'continuous',
                process_time: 5.0, intake_time: 1.0, port_lots_load: 1, port_lots_unload: 1,
                machine_role: 'normal', generation_interval: 5.0, generation_random: false, generators: [],
                is_stub: false 
            } 
        };
        saveSchemas(updated);
        setNewId("");
        setSelectedId(newId.trim());
    };

    const handleDelete = (id) => {
        const updated = { ...schemas };
        delete updated[id];
        saveSchemas(updated);
        if (selectedId === id) setSelectedId(null);
    };

    const activeSchema = selectedId ? schemas[selectedId] : null;

    const updateProp = (key, val) => {
        const updated = { ...schemas };
        updated[selectedId][key] = val;
        if (updated[selectedId].is_stub) {
            updated[selectedId].is_stub = false; // Mark as configured once they edit it
        }
        saveSchemas(updated);
    };

    const UNIT = 50; // pixels per physical unit

    const getSnappedPos = (e) => {
        if (!activeSchema) return null;
        const rect = e.currentTarget.getBoundingClientRect();
        const mx = e.clientX - rect.left - rect.width / 2;
        const my = e.clientY - rect.top - rect.height / 2;
        
        let rel_x = mx / UNIT;
        let rel_y = -my / UNIT;

        const hw = activeSchema.width / 2;
        const hh = activeSchema.height / 2;

        const snapPoints = [
            { x: 0, y: 0 },
            { x: hw, y: hh }, { x: -hw, y: hh }, { x: hw, y: -hh }, { x: -hw, y: -hh },
            { x: 0, y: hh }, { x: 0, y: -hh }, { x: hw, y: 0 }, { x: -hw, y: 0 }
        ];

        let bestDist = Infinity;
        let bestSnap = null;
        for (let p of snapPoints) {
            const d = Math.sqrt((rel_x - p.x)**2 + (rel_y - p.y)**2);
            if (d < bestDist) { bestDist = d; bestSnap = p; }
        }

        if (bestDist < 0.5) {
            rel_x = bestSnap.x;
            rel_y = bestSnap.y;
        }
        return { rel_x, rel_y };
    };

    // Handle Canvas Click for Ports
    const handleCanvasClick = (e) => {
        const pos = getSnappedPos(e);
        if (!pos) return;

        const newPort = {
            id: 'p' + Date.now(),
            rel_x: pos.rel_x,
            rel_y: pos.rel_y,
            type: 'LOAD'
        };

        const updated = { ...schemas };
        updated[selectedId].ports.push(newPort);
        saveSchemas(updated);
    };

    const handleRemovePort = (idx) => {
        const updated = { ...schemas };
        updated[selectedId].ports.splice(idx, 1);
        saveSchemas(updated);
    };

    const handleTogglePort = (idx) => {
        const updated = { ...schemas };
        const p = updated[selectedId].ports[idx];
        if (p.type === 'LOAD') p.type = 'UNLOAD';
        else if (p.type === 'UNLOAD') p.type = 'BOTH';
        else p.type = 'LOAD';
        saveSchemas(updated);
    };

    return (
        <div style={{ display: 'flex', width: '100%', height: '100%' }}>
            <div className="sidebar" style={{ width: '300px' }}>
                <h3 style={{color: '#94a3b8', margin: 0, textTransform: 'uppercase', fontSize: '13px'}}>Machine Schemas</h3>
                
                <div style={{ display: 'flex', gap: '8px' }}>
                    <input 
                        type="text" 
                        placeholder="New Machine ID" 
                        value={newId} 
                        onChange={e => setNewId(e.target.value)}
                        style={{ flex: 1 }}
                    />
                    <button className="action-btn" onClick={handleCreate}>Add</button>
                </div>

                <div style={{ marginTop: '16px', overflowY: 'auto' }}>
                    {Object.values(schemas).map(s => (
                        <div 
                            key={s.id} 
                            className={`list-item ${selectedId === s.id ? 'selected' : ''}`}
                            onClick={() => setSelectedId(s.id)}
                            style={{ borderLeft: s.is_stub ? '4px solid #ef4444' : '4px solid transparent' }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{fontWeight: 'bold', fontSize: '14px'}}>{s.id}</span>
                                {s.machine_role && s.machine_role !== 'normal' && (
                                    <span style={{ 
                                        fontSize: '10px', 
                                        fontWeight: 600,
                                        padding: '1px 6px',
                                        borderRadius: '3px',
                                        background: s.machine_role === 'source' ? 'rgba(74, 222, 128, 0.18)' : 'rgba(248, 113, 113, 0.18)',
                                        color: s.machine_role === 'source' ? '#4ade80' : '#f87171', 
                                        textTransform: 'uppercase' 
                                    }}>{s.machine_role}</span>
                                )}
                            </div>
                            <div style={{ display: 'flex', gap: '4px', marginTop: '2px' }}>
                                {s.is_stub && <span className="badge">STUB</span>}
                                <span style={{fontSize: '11px', color: '#64748b'}}>{s.ports?.length || 0} Ports</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {activeSchema ? (
                <div style={{ display: 'flex', flex: 1, height: '100%', minWidth: 0, overflow: 'hidden' }}>
                    <div 
                        className="designer-grid-container" 
                        onClick={handleCanvasClick}
                        onMouseMove={(e) => setPreviewPort(getSnappedPos(e))}
                        onMouseLeave={() => setPreviewPort(null)}
                    >
                        {/* Machine Footprint */}
                        <div 
                            className="machine-block"
                            style={{
                                width: activeSchema.width * UNIT,
                                height: activeSchema.height * UNIT,
                                backgroundColor: activeSchema.machine_role === 'source' ? '#166534' : activeSchema.machine_role === 'sink' ? '#7f1d1d' : '#1e293b',
                                borderColor: activeSchema.machine_role === 'source' ? '#4ade80' : activeSchema.machine_role === 'sink' ? '#f87171' : '#3b82f6'
                            }}
                        >
                            <div style={{
                                position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                                color: '#f8fafc', fontWeight: 'bold', fontSize: '14px', pointerEvents: 'none',
                                display: 'flex', flexDirection: 'column', alignItems: 'center'
                            }}>
                                <span>{activeSchema.id}</span>
                                {activeSchema.machine_role && activeSchema.machine_role !== 'normal' && (
                                    <span style={{ fontSize: '11px', color: activeSchema.machine_role === 'source' ? '#4ade80' : '#f87171', textTransform: 'uppercase' }}>
                                        {activeSchema.machine_role}
                                    </span>
                                )}
                            </div>
                        </div>
                        
                        {/* Ports Overlay (absolute relative to center of the container) */}
                        {activeSchema.ports.map((p, idx) => (
                            <div 
                                key={idx}
                                className={`port-node ${p.type}`}
                                style={{
                                    left: `calc(50% + ${p.rel_x * UNIT}px)`,
                                    top: `calc(50% - ${p.rel_y * UNIT}px)`
                                }}
                                onClick={(e) => { e.stopPropagation(); handleTogglePort(idx); }}
                                onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); handleRemovePort(idx); }}
                                title={`${p.type} (Right click to remove)`}
                            />
                        ))}
                        {/* Preview Port */}
                        {previewPort && (
                            <div 
                                className="port-node LOAD"
                                style={{
                                    left: `calc(50% + ${previewPort.rel_x * UNIT}px)`,
                                    top: `calc(50% - ${previewPort.rel_y * UNIT}px)`,
                                    opacity: 0.5,
                                    pointerEvents: 'none'
                                }}
                            />
                        )}
                    </div>

                    <div className="sidebar" style={{ width: '380px', flexShrink: 0, borderLeft: '1px solid #334155', borderRight: 'none' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h3 style={{ margin: 0, color: '#f8fafc' }}>Properties</h3>
                            <button className="action-btn" style={{ background: '#ef4444', padding: '4px 8px' }} onClick={() => handleDelete(activeSchema.id)}>Delete</button>
                        </div>
                        
                        <div className="panel">
                            <h3>Dimensions</h3>
                            <div className="form-row">
                                <span>Width:</span>
                                <input type="number" min="0.5" step="0.5" value={activeSchema.width} onChange={e => updateProp('width', parseFloat(e.target.value) || 1)} />
                            </div>
                            <div className="form-row">
                                <span>Height:</span>
                                <input type="number" min="0.5" step="0.5" value={activeSchema.height} onChange={e => updateProp('height', parseFloat(e.target.value) || 1)} />
                            </div>
                        </div>

                        <div className="panel">
                            <h3>Processing</h3>
                            <div className="form-row">
                                <span>Capacity:</span>
                                <input type="number" min="1" value={activeSchema.capacity} onChange={e => updateProp('capacity', parseInt(e.target.value) || 1)} />
                            </div>
                            <div className="form-row">
                                <span>Process Mode:</span>
                                <select value={activeSchema.process_mode} onChange={e => updateProp('process_mode', e.target.value)}>
                                    <option value="batch">Batch</option>
                                    <option value="continuous">Continuous</option>
                                </select>
                            </div>
                            <div className="form-row">
                                <span>Intake Mode:</span>
                                <select value={activeSchema.intake_mode} onChange={e => updateProp('intake_mode', e.target.value)}>
                                    <option value="batch">1-by-1 (Batch)</option>
                                    <option value="continuous">Pour (Continuous)</option>
                                </select>
                            </div>
                            <div className="form-row">
                                <span>Process Time (s):</span>
                                <input type="number" min="0.1" step="0.1" value={activeSchema.process_time} onChange={e => updateProp('process_time', parseFloat(e.target.value) || 5.0)} />
                            </div>
                            <div className="form-row">
                                <span>Intake Time (s):</span>
                                <input type="number" min="0.1" step="0.1" value={activeSchema.intake_time || 1.0} onChange={e => updateProp('intake_time', parseFloat(e.target.value) || 1.0)} />
                            </div>
                        </div>

                        <div className="panel">
                            <h3>Port Capacity</h3>
                            <div className="form-row">
                                <span>Load Lots:</span>
                                <input type="number" min="1" value={activeSchema.port_lots_load || 1} onChange={e => updateProp('port_lots_load', parseInt(e.target.value) || 1)} />
                            </div>
                            <div className="form-row">
                                <span>Unload Lots:</span>
                                <input type="number" min="1" value={activeSchema.port_lots_unload || 1} onChange={e => updateProp('port_lots_unload', parseInt(e.target.value) || 1)} />
                            </div>
                        </div>

                        <div className="panel">
                            <h3>Machine Role</h3>
                            <div className="form-row">
                                <span>Role:</span>
                                <select value={activeSchema.machine_role || 'normal'} onChange={e => updateProp('machine_role', e.target.value)}>
                                    <option value="normal">Normal</option>
                                    <option value="source">Source</option>
                                    <option value="sink">Sink</option>
                                </select>
                            </div>
                        </div>

                        {activeSchema.machine_role === 'source' && (
                            <div className="panel">
                                <h3>Source Generator</h3>
                                <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '10px', lineHeight: '1.4' }}>
                                    Spawns cargo containers into empty ports based on the time interval and weighted recipe distribution below.
                                </div>
                                <div className="form-row">
                                    <span title="Interval between container generation attempts">Time Gap (s):</span>
                                    <input 
                                        type="number" 
                                        min="0.1" 
                                        step="0.1" 
                                        value={activeSchema.generation_interval || 5.0} 
                                        onChange={e => updateProp('generation_interval', parseFloat(e.target.value) || 5.0)} 
                                        style={{ width: '100px' }} 
                                    />
                                </div>
                                <div className="form-row">
                                    <span title="Add ±50% random variation to the generation interval">Randomized Gap:</span>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '12px', color: '#cbd5e1' }}>
                                        <input 
                                            type="checkbox" 
                                            checked={!!activeSchema.generation_random} 
                                            onChange={e => updateProp('generation_random', e.target.checked)} 
                                            style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                                        />
                                        <span>±50% jitter</span>
                                    </label>
                                </div>

                                <div style={{ marginTop: '12px', borderTop: '1px solid #334155', paddingTop: '10px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', padding: '0 4px' }}>
                                        <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Spawn Recipe</span>
                                        <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginRight: '34px' }}>Ratio (Weight)</span>
                                    </div>

                                    {(!activeSchema.generators || activeSchema.generators.length === 0) && (
                                        <div style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic', padding: '6px 4px', textAlign: 'center', background: 'rgba(0,0,0,0.2)', borderRadius: '4px', marginBottom: '6px' }}>
                                            No recipe rules added (spawns UNKNOWN)
                                        </div>
                                    )}

                                    {(activeSchema.generators || []).map((gen, gIdx) => (
                                        <div key={gIdx} style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(0,0,0,0.25)', padding: '6px 8px', borderRadius: '6px', marginBottom: '6px', border: '1px solid #334155' }}>
                                            <select 
                                                value={gen.recipe_id} 
                                                onChange={e => {
                                                    const newGens = [...(activeSchema.generators || [])];
                                                    newGens[gIdx].recipe_id = e.target.value;
                                                    updateProp('generators', newGens);
                                                }}
                                                style={{ flex: 1, minWidth: 0, fontSize: '13px' }}
                                            >
                                                <option value="">Select Recipe...</option>
                                                {Object.keys(recipes).map(rid => <option key={rid} value={rid}>{rid}</option>)}
                                            </select>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                <input 
                                                    type="number" 
                                                    min="0" step="0.1" 
                                                    value={gen.ratio} 
                                                    placeholder="1.0"
                                                    title="Relative spawn ratio/weight"
                                                    style={{ width: '70px', fontSize: '13px', textAlign: 'center' }}
                                                    onChange={e => {
                                                        const newGens = [...(activeSchema.generators || [])];
                                                        newGens[gIdx].ratio = parseFloat(e.target.value) || 0;
                                                        updateProp('generators', newGens);
                                                    }} 
                                                />
                                                <button 
                                                    className="action-btn" 
                                                    style={{ background: '#ef4444', padding: '5px 8px', fontSize: '11px', lineHeight: 1 }} 
                                                    title="Remove generator"
                                                    onClick={() => {
                                                        const newGens = [...(activeSchema.generators || [])];
                                                        newGens.splice(gIdx, 1);
                                                        updateProp('generators', newGens);
                                                    }}>✕</button>
                                            </div>
                                        </div>
                                    ))}
                                    <button className="action-btn" style={{ width: '100%', marginTop: '6px', padding: '7px 12px' }} 
                                        onClick={() => {
                                            const newGens = [...(activeSchema.generators || []), { recipe_id: '', ratio: 1.0 }];
                                            updateProp('generators', newGens);
                                        }}>+ Add Recipe Generator</button>
                                </div>
                            </div>
                        )}

                        <div className="helper-banner" style={{position: 'static', marginTop: 'auto', flexDirection: 'column'}}>
                            <span className="helper-item">
                                <b>Port Colors:</b> <span style={{color: '#4ade80'}}>● Load</span>, <span style={{color: '#ef4444'}}>● Unload</span>, <span style={{color: '#fbbf24'}}>● Both</span>
                            </span>
                            <div style={{ height: '1px', background: '#334155', margin: '4px 0' }} />
                            <span className="helper-item"><b>Left Click Canvas:</b> Place Port</span>
                            <span className="helper-item"><b>Left Click Port:</b> Toggle Type</span>
                            <span className="helper-item"><b>Right Click Port:</b> Remove</span>
                        </div>
                    </div>
                </div>
            ) : (
                <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
                    Select or create a machine schema from the sidebar.
                </div>
            )}
        </div>
    );
}