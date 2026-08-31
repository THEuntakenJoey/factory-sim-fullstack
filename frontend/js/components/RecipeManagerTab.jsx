const { useState } = React;

function RecipeManagerTab({ recipes, saveRecipes, schemas, saveSchemas }) {
    const [selectedId, setSelectedId] = useState(null);
    const [newId, setNewId] = useState("");

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

    const handleAddStep = () => {
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

    const handleRemoveStep = (idx) => {
        const updated = { ...recipes };
        updated[selectedId].steps.splice(idx, 1);
        saveRecipes(updated);
    };

    return (
        <div style={{ display: 'flex', width: '100%', height: '100%' }}>
            <div className="sidebar" style={{ width: '300px' }}>
                <h3 style={{color: '#94a3b8', margin: 0, textTransform: 'uppercase', fontSize: '13px'}}>Recipes</h3>
                
                <div style={{ display: 'flex', gap: '8px' }}>
                    <input 
                        type="text" 
                        placeholder="New Recipe Name" 
                        value={newId} 
                        onChange={e => setNewId(e.target.value)}
                        style={{ flex: 1 }}
                    />
                    <button className="action-btn" onClick={handleCreate}>Add</button>
                </div>

                <div style={{ marginTop: '16px', overflowY: 'auto' }}>
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

            <div className="main-content" style={{ padding: '24px', overflowY: 'auto' }}>
                {activeRecipe ? (
                    <div style={{ maxWidth: '600px', margin: '0 auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                            <h2 style={{ margin: 0 }}>Recipe: {activeRecipe.id}</h2>
                            <button className="action-btn" style={{ background: '#ef4444' }} onClick={() => handleDelete(activeRecipe.id)}>Delete Recipe</button>
                        </div>
                        
                        <div className="panel">
                            <h3>Process Steps</h3>
                            {activeRecipe.steps.length === 0 ? (
                                <p style={{ color: '#64748b', fontSize: '14px', textAlign: 'center', padding: '20px 0' }}>No steps added yet.</p>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    {activeRecipe.steps.map((step, idx) => (
                                        <div key={idx} style={{ 
                                            background: '#1e293b', 
                                            padding: '12px 16px', 
                                            borderRadius: '6px',
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            alignItems: 'center',
                                            borderLeft: '4px solid #38bdf8'
                                        }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
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
                            
                            <button 
                                className="action-btn" 
                                style={{ marginTop: '16px', width: '100%', padding: '12px', background: '#0f172a', border: '1px dashed #38bdf8', color: '#38bdf8' }}
                                onClick={handleAddStep}
                            >
                                + Add Step
                            </button>
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