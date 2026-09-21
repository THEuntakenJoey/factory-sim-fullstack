
const { useState, useEffect, useRef, useCallback } = React;

function App() {
    const [activeTab, setActiveTab] = useState('map');
    const [project, setProject] = useState('factory1');
    const [projectList, setProjectList] = useState(['factory1']);
    const [schemas, setSchemas] = useState({});
    const [recipes, setRecipes] = useState({});
    const [activeMapName, setActiveMapName] = useState('map.json');
    
    // Save & Dirty Tracking
    const [isDirty, setIsDirty] = useState(false);
    const [saveStatus, setSaveStatus] = useState('idle'); // 'idle' | 'saving' | 'saved' | 'error'
    const [toast, setToast] = useState(null);
    const toastTimerRef = useRef(null);

    // Project Switching Modal
    const [showSwitchModal, setShowSwitchModal] = useState(false);
    const [pendingProject, setPendingProject] = useState(null);

    // Show toast notification
    const showToast = useCallback((message, type = 'success', duration = 3000) => {
        if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
        setToast({ message, type });
        toastTimerRef.current = setTimeout(() => {
            setToast(null);
        }, duration);
    }, []);

    // Load project list on mount
    useEffect(() => {
        window.API.request('/api/projects').then(data => {
            if (data && data.projects && data.projects.length > 0) {
                setProjectList(data.projects);
                if (!data.projects.includes(project)) {
                    setProject(data.projects[0]);
                }
            }
        }).catch(e => console.error("Failed to load projects list", e));
    }, []);

    // Load data when project changes
    const loadProjectData = async (projName) => {
        try {
            const schemasData = await window.API.request(`/api/schemas/${projName}`);
            const recipesData = await window.API.request(`/api/recipes/${projName}`);
            setSchemas(schemasData || {});
            setRecipes(recipesData || {});
            setIsDirty(false);
            if (window.Builder) window.Builder.isDirty = false;
        } catch (e) {
            console.error("Failed to load project data", e);
            showToast(`Failed to load data for project "${projName}"`, 'error');
        }
    };
    
    useEffect(() => {
        loadProjectData(project);
    }, [project]);

    // Track beforeunload to warn user of unsaved changes
    useEffect(() => {
        const handleBeforeUnload = (e) => {
            if (isDirty) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, [isDirty]);

    // Schemas change handler: updates in-memory schemas and marks project dirty
    const saveSchemas = (newSchemas) => {
        setSchemas(newSchemas);
        setIsDirty(true);
    };

    // Recipes change handler: updates in-memory recipes, marks project dirty, and syncs to backend
    const saveRecipes = (newRecipes) => {
        setRecipes(newRecipes);
        setIsDirty(true);
        if (window.API && window.API.saveRecipes) {
            window.API.saveRecipes(project, newRecipes).catch(e => console.warn("Notice: could not auto-sync recipes:", e));
        }
    };

    // Map change handler from MapBuilderTab/Builder
    const handleMapChange = () => {
        setIsDirty(true);
    };

    // Save all project changes (Map, Schemas, Recipes)
    const handleSaveProject = async (targetProj = project) => {
        if (saveStatus === 'saving') return;
        setSaveStatus('saving');

        try {
            const mapGraph = window.Builder ? window.Builder.saveGraph() : null;
            const payload = {
                map: mapGraph,
                map_filename: activeMapName || 'map.json',
                schemas: schemas,
                recipes: recipes
            };

            await window.API.saveProject(targetProj, payload);

            setSaveStatus('saved');
            setIsDirty(false);
            if (window.Builder) window.Builder.isDirty = false;
            showToast(`Project "${targetProj}" saved successfully!`, 'success');

            setTimeout(() => {
                setSaveStatus('idle');
            }, 2200);
            return true;
        } catch (err) {
            console.error("Failed to save project", err);
            setSaveStatus('error');
            showToast(`Failed to save project: ${err.message}`, 'error', 4000);
            setTimeout(() => {
                setSaveStatus('idle');
            }, 3000);
            return false;
        }
    };

    // Keyboard shortcut: Ctrl+S / Cmd+S
    useEffect(() => {
        const handleKeyDown = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                e.preventDefault();
                handleSaveProject();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [project, schemas, recipes, activeMapName, saveStatus]);

    // Project switching guard
    const requestProjectChange = (newProj) => {
        if (newProj === project) return;
        if (isDirty) {
            setPendingProject(newProj);
            setShowSwitchModal(true);
        } else {
            setProject(newProj);
        }
    };

    const handleConfirmSwitchSave = async () => {
        const ok = await handleSaveProject(project);
        if (ok && pendingProject) {
            setProject(pendingProject);
            setPendingProject(null);
            setShowSwitchModal(false);
        }
    };

    const handleConfirmSwitchDiscard = () => {
        if (pendingProject) {
            setProject(pendingProject);
            setPendingProject(null);
            setShowSwitchModal(false);
            setIsDirty(false);
            if (window.Builder) window.Builder.isDirty = false;
        }
    };

    const handleCancelSwitch = () => {
        setPendingProject(null);
        setShowSwitchModal(false);
    };

    // New project creation
    const promptNewProject = async () => {
        const name = prompt("Enter new project name:");
        if (!name || !name.trim()) return;
        const cleanName = name.trim().replace(/[^a-zA-Z0-9_-]/g, '');
        if (!cleanName) {
            alert("Invalid project name. Use letters, numbers, dashes or underscores.");
            return;
        }

        if (projectList.includes(cleanName)) {
            requestProjectChange(cleanName);
            return;
        }

        if (isDirty) {
            const confirmSave = confirm(`You have unsaved changes in "${project}".\nClick OK to save changes first, or Cancel to discard.`);
            if (confirmSave) {
                await handleSaveProject(project);
            }
        }

        try {
            await window.API.createProject(cleanName);
            setProjectList(prev => [...new Set([...prev, cleanName])]);
            setProject(cleanName);
            setIsDirty(false);
            if (window.Builder) window.Builder.isDirty = false;
            showToast(`Created new project "${cleanName}"`, 'success');
        } catch (e) {
            alert("Failed to create project: " + e.message);
        }
    };
    
    // Count stubs
    const stubCount = Object.values(schemas).filter(s => s.is_stub).length;

    return (
        <React.Fragment>
            <div className="topbar">
                <div style={{fontWeight: 'bold', color: 'white', marginRight: '24px', display: 'flex', alignItems: 'center', gap: '8px'}}>
                    <span style={{color: '#38bdf8', fontSize: '18px'}}>⚡</span>
                    <span>FactorySim</span>
                    <span style={{fontSize: '10px', background: '#0284c7', color: '#f0f9ff', padding: '2px 6px', borderRadius: '4px', textTransform: 'uppercase', letterSpacing: '0.05em'}}>Full Stack</span>
                </div>
                
                <button className={`tab-btn ${activeTab === 'map' ? 'active' : ''}`} onClick={() => setActiveTab('map')}>
                    Map Builder
                </button>
                <button className={`tab-btn ${activeTab === 'machine' ? 'active' : ''}`} onClick={() => setActiveTab('machine')}>
                    Machine Designer {stubCount > 0 && <span className="badge">{stubCount}</span>}
                </button>
                <button className={`tab-btn ${activeTab === 'recipe' ? 'active' : ''}`} onClick={() => setActiveTab('recipe')}>
                    Recipe Manager
                </button>
                <button className={`tab-btn ${activeTab === 'simulation' ? 'active' : ''}`} onClick={() => setActiveTab('simulation')}>
                    Simulation
                </button>
                
                {/* Top-Right Controls */}
                <div style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px'}}>
                    {/* Status Indicator */}
                    <div className="status-badge" title={isDirty ? "Unsaved changes in this project" : "All changes saved"}>
                        <span className={`status-dot ${isDirty ? 'dirty' : 'clean'}`} />
                        <span style={{color: isDirty ? '#f59e0b' : '#94a3b8', fontSize: '11px', fontWeight: 600}}>
                            {isDirty ? 'Unsaved' : 'Saved'}
                        </span>
                    </div>

                    {/* Project Selector */}
                    <div style={{display: 'flex', alignItems: 'center', gap: '6px'}}>
                        <span style={{fontSize: '12px', color: '#94a3b8'}}>Project:</span>
                        <select 
                            value={project} 
                            onChange={e => requestProjectChange(e.target.value)}
                            style={{width: '130px', padding: '5px 8px', fontSize: '13px'}}
                        >
                            {projectList.map(p => (
                                <option key={p} value={p}>{p}</option>
                            ))}
                        </select>
                    </div>

                    {/* New Project Button */}
                    <button 
                        className="action-btn" 
                        style={{padding: '5px 10px', fontSize: '12px', background: '#334155', border: '1px solid #475569'}}
                        onClick={promptNewProject}
                        title="Create a new project"
                    >
                        + New
                    </button>

                    {/* SAVE PROJECT BUTTON */}
                    <button 
                        className={`save-btn ${saveStatus === 'saving' ? 'saving' : saveStatus === 'saved' ? 'saved' : saveStatus === 'error' ? 'error' : isDirty ? 'dirty' : 'clean'}`}
                        onClick={() => handleSaveProject()}
                        disabled={saveStatus === 'saving'}
                        title={`Save changes to "${project}" (Ctrl+S)`}
                        id="save-project-btn"
                    >
                        {saveStatus === 'saving' && <span className="spinner" />}
                        {saveStatus === 'saved' && <span style={{fontSize: '13px'}}>✓</span>}
                        {saveStatus === 'error' && <span style={{fontSize: '13px'}}>⚠</span>}
                        {saveStatus === 'idle' && <span style={{fontSize: '13px'}}>💾</span>}
                        <span>
                            {saveStatus === 'saving' ? 'Saving...' : 
                             saveStatus === 'saved' ? 'Saved!' : 
                             saveStatus === 'error' ? 'Save Failed' : 
                             isDirty ? 'Save Project *' : 'Save Project'}
                        </span>
                    </button>
                </div>
            </div>

            {/* Tab Contents - Keep all mounted to avoid canvas reload */}
            <div className="workspace">
                <div style={{ flex: 1, display: activeTab === 'map' ? 'block' : 'none', height: '100%' }}>
                    <MapBuilderTab 
                        project={project} 
                        schemas={schemas} 
                        recipes={recipes} 
                        onMapChange={handleMapChange}
                        activeMapName={activeMapName}
                        setActiveMapName={setActiveMapName}
                        onSaveProject={handleSaveProject}
                    />
                </div>
                <div style={{ flex: 1, display: activeTab === 'machine' ? 'block' : 'none', height: '100%' }}>
                    <MachineDesignerTab 
                        schemas={schemas} 
                        saveSchemas={saveSchemas} 
                        recipes={recipes} 
                    />
                </div>
                <div style={{ flex: 1, display: activeTab === 'recipe' ? 'block' : 'none', height: '100%' }}>
                    <RecipeManagerTab 
                        recipes={recipes} 
                        saveRecipes={saveRecipes} 
                        schemas={schemas} 
                        saveSchemas={saveSchemas} 
                    />
                </div>
                <div style={{ flex: 1, display: activeTab === 'simulation' ? 'flex' : 'none', flexDirection: 'column', height: '100%', maxHeight: '100%', minHeight: 0, overflow: 'hidden' }}>
                    <SimulationTab 
                        project={project} 
                        schemas={schemas} 
                        recipes={recipes} 
                        activeMapName={activeMapName}
                        isActive={activeTab === 'simulation'}
                    />
                </div>
            </div>

            {/* Toast Container */}
            {toast && (
                <div className="toast-container">
                    <div className={`toast ${toast.type}`}>
                        <span>{toast.type === 'success' ? '✓' : '⚠'}</span>
                        <span>{toast.message}</span>
                    </div>
                </div>
            )}

            {/* Project Switch Confirmation Modal */}
            {showSwitchModal && (
                <div className="modal-overlay" onClick={handleCancelSwitch}>
                    <div className="modal-box" onClick={e => e.stopPropagation()}>
                        <h3>Unsaved Changes</h3>
                        <p>
                            You have unsaved changes in project <b>{project}</b>.<br />
                            Would you like to save them before switching to <b>{pendingProject}</b>?
                        </p>
                        <div className="modal-actions">
                            <button 
                                className="action-btn" 
                                style={{background: '#475569'}}
                                onClick={handleCancelSwitch}
                            >
                                Cancel
                            </button>
                            <button 
                                className="action-btn" 
                                style={{background: '#dc2626'}}
                                onClick={handleConfirmSwitchDiscard}
                            >
                                Discard & Switch
                            </button>
                            <button 
                                className="action-btn" 
                                style={{background: '#0284c7'}}
                                onClick={handleConfirmSwitchSave}
                            >
                                Save & Switch
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </React.Fragment>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

