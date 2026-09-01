const { useState } = React;

function RecipeManagerTab({ recipes, saveRecipes, schemas, saveSchemas }) {
    const [selectedId, setSelectedId] = useState(null);
    const [newId, setNewId] = useState("");
    
    // Drag state for reordering
    const [draggedIdx, setDraggedIdx] = useState(null);
    const [dragOverIdx, setDragOverIdx] = useState(null);

    const handleCreate = () => {
        if (!newId.trim() || recipes[newId.trim()]) return;
        const updated = { ...recipes, [newId.trim()]: { id: newId.trim(), steps: [] } };
        saveRecipes(updated);
        setNewId("");
        setSelectedId(newId.trim());
    };

    const handleDelete = (id) => {
        const updated = { ...recipes };
        delete updated[id];
        saveRecipes(updated);
        if (selectedId === id) setSelectedId(null);
    };

    const activeRecipe = selectedId ? recipes[selectedId] : null;

    const handleAddCustomStep = () => {
        const machineId = prompt("Enter Machine Schema ID for this step:");
        if (!machineId) return;

        // Auto-stub check
        if (!schemas[machineId]) {
            if (confirm(`Schema '${machineId}' does not exist. Auto-create a stub?`)) {
                const updatedSchemas = {
                    ...schemas,
                    [machineId]: {
                        id: machineId,
                        width: 2,
                        height: 2,
                        ports: [],
                        capacity: 1,
                        process_mode: 'batch',
                        intake_mode: 'continuous',
                        process_time: 5.0,
                        intake_time: 1.0,
                        port_lots_load: 1,
                        port_lots_unload: 1,
                        is_stub: true
                    }
                };
                saveSchemas(updatedSchemas);
            } else {
                return; // Cancel step addition if they don't want to stub
            }
        }

        const updated = { ...recipes };
        updated[selectedId].steps.push(machineId);
        saveRecipes(updated);
    };

    const handleSelectMachine = (value) => {
        if (value === "__CUSTOM__") {
            handleAddCustomStep();
        } else {
            const updated = { ...recipes };
            updated[selectedId].steps.push(value);
            saveRecipes(updated);
        }
    };

    const handleRemoveStep = (idx) => {
        const updated = { ...recipes };
        updated[selectedId].steps.splice(idx, 1);
        saveRecipes(updated);
    };

    // Drag and Drop handlers
    const handleDragStartMachine = (e, machineId) => {
        e.dataTransfer.setData('machineId', machineId);
        e.dataTransfer.effectAllowed = 'copy';
    };

    const handleDragStartItem = (e, idx) => {
        setDraggedIdx(idx);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', idx);
    };

    const handleDragOverItem = (e, idx) => {
        e.preventDefault();
        setDragOverIdx(idx);
    };

    const handleDropItem = (e, idx) => {
        e.preventDefault();
        e.stopPropagation(); // prevent dropping on area
        setDragOverIdx(null);
        
        const machineId = e.dataTransfer.getData('machineId');
        if (machineId) {
            const updated = { ...recipes };
            updated[selectedId].steps.splice(idx, 0, machineId);
            saveRecipes(updated);
            return;
        }

        if (draggedIdx === null || draggedIdx === idx) return;

        const updated = { ...recipes };
        const steps = [...updated[selectedId].steps];
        const [draggedStep] = steps.splice(draggedIdx, 1);
        steps.splice(idx, 0, draggedStep);
        updated[selectedId].steps = steps;
        saveRecipes(updated);
        setDraggedIdx(null);
    };
    
    const handleDragEndItem = (e) => {
        setDraggedIdx(null);
        setDragOverIdx(null);
    };

    const handleDragOverArea = (e) => {
        e.preventDefault();
    };

    const handleDropArea = (e) => {
        e.preventDefault();
        const machineId = e.dataTransfer.getData('machineId');
        if (machineId && activeRecipe) {
            const updated = { ...recipes };
            updated[selectedId].steps.push(machineId);
            saveRecipes(updated);
            return;
        }
        
        // if reordering to the end
        if (draggedIdx !== null && activeRecipe) {
            const updated = { ...recipes };
            const steps = [...updated[selectedId].steps];
            const [draggedStep] = steps.splice(draggedIdx, 1);
            steps.push(draggedStep);
            updated[selectedId].steps = steps;
            saveRecipes(updated);
            setDraggedIdx(null);
        }
    };

    return (
        <div style={{ display: 'flex', width: '100%', height: '100%' }}>
            <div className="sidebar" style={{ width: '300px', display: 'flex', flexDirection: 'column' }}>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'hidden', minHeight: 0 }}>
                    <h3 style={{color: '#94a3b8', margin: 0, textTransform: 'uppercase', fontSize: '13px', marginBottom: '12px'}}>Recipes</h3>
                    
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                        <input 
                            type="text" 
                            placeholder="New Recipe Name" 
                            value={newId} 
                            onChange={e => setNewId(e.target.value)}
                            style={{ flex: 1 }}
                        />
                        <button className="action-btn" onClick={handleCreate}>Add</button>
                    </div>

                    <div style={{ overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
                        {Object.values(recipes).map(r => (
                            <div 
                                key={r.id} 
                                className={`list-item ${selectedId === r.id ? 'selected' : ''}`}
                                onClick={() => setSelectedId(r.id)}
                            >
                                <span style={{fontWeight: 'bold', fontSize: '14px'}}>{r.id}</span>
                                <span style={{fontSize: '11px', color: '#64748b'}}>{r.steps.length} steps</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'hidden', marginTop: '16px', borderTop: '1px solid #334155', paddingTop: '16px', minHeight: 0 }}>
                    <h3 style={{color: '#94a3b8', margin: 0, textTransform: 'uppercase', fontSize: '13px', marginBottom: '12px'}}>Machines (Drag to Recipe)</h3>
                    <div style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '4px' }}>
                        {Object.keys(schemas).map(machineId => (
                            <div 
                                key={machineId}
                                draggable
                                onDragStart={(e) => handleDragStartMachine(e, machineId)}
                                style={{ 
                                    background: '#1e293b', 
                                    padding: '10px 12px', 
                                    borderRadius: '6px', 
                                    cursor: 'grab', 
                                    border: '1px solid #334155', 
                                    color: '#e2e8f0', 
                                    fontSize: '14px',
                                    userSelect: 'none'
                                }}
                            >
                                <span style={{ marginRight: '8px', opacity: 0.5 }}>≡</span>
                                {machineId}
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="main-content" style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
                {activeRecipe ? (
                    <div style={{ maxWidth: '600px', margin: '0 auto', height: '100%', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                            <h2 style={{ margin: 0 }}>Recipe: {activeRecipe.id}</h2>
                            <button className="action-btn" style={{ background: '#ef4444' }} onClick={() => handleDelete(activeRecipe.id)}>Delete Recipe</button>
                        </div>
                        
                        <div 
                            className="panel" 
                            style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
                            onDragOver={handleDragOverArea}
                            onDrop={handleDropArea}
                        >
                            <h3>Process Steps</h3>
                            {activeRecipe.steps.length === 0 ? (
                                <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '2px dashed #334155', borderRadius: '8px', margin: '20px 0' }}>
                                    <p style={{ color: '#64748b', fontSize: '14px', textAlign: 'center' }}>No steps added yet.<br/>Drag a machine here or add from below.</p>
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minHeight: '50px' }}>
                                    {activeRecipe.steps.map((step, idx) => (
                                        <div 
                                            key={`${idx}-${step}`} 
                                            draggable
                                            onDragStart={(e) => handleDragStartItem(e, idx)}
                                            onDragOver={(e) => handleDragOverItem(e, idx)}
                                            onDrop={(e) => handleDropItem(e, idx)}
                                            onDragEnd={handleDragEndItem}
                                            style={{ 
                                                background: '#1e293b', 
                                                padding: '12px 16px', 
                                                borderRadius: '6px',
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                alignItems: 'center',
                                                borderLeft: '4px solid #38bdf8',
                                                cursor: 'grab',
                                                opacity: draggedIdx === idx ? 0.5 : 1,
                                                borderTop: dragOverIdx === idx ? '2px solid #38bdf8' : '1px solid transparent',
                                                borderBottom: '1px solid transparent',
                                                transform: 'translateZ(0)',
                                                userSelect: 'none'
                                            }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                                <span style={{ cursor: 'grab', opacity: 0.5 }}>≡</span>
                                                <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#94a3b8' }}>{idx + 1}.</span>
                                                <span style={{ fontSize: '16px', fontWeight: 'bold' }}>{step}</span>
                                            </div>
                                            <button 
                                                style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 'bold' }}
                                                onClick={() => handleRemoveStep(idx)}
                                            >
                                                ✕
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            
                            <select 
                                style={{ 
                                    marginTop: '16px', 
                                    width: '100%', 
                                    padding: '12px', 
                                    background: '#0f172a', 
                                    border: '1px dashed #38bdf8', 
                                    color: '#38bdf8', 
                                    outline: 'none', 
                                    borderRadius: '4px', 
                                    fontSize: '14px', 
                                    fontWeight: 'bold',
                                    cursor: 'pointer'
                                }}
                                value=""
                                onChange={(e) => { if(e.target.value) handleSelectMachine(e.target.value); }}
                            >
                                <option value="" disabled>+ Add Step (Select Machine)</option>
                                {Object.keys(schemas).map(machineId => (
                                    <option key={machineId} value={machineId}>{machineId}</option>
                                ))}
                                <option value="__CUSTOM__">+ Add Custom Step...</option>
                            </select>
                        </div>
                    </div>
                ) : (
                    <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
                        Select or create a recipe from the sidebar.
                    </div>
                )}
            </div>
        </div>
    );
}