
const { useState, useEffect } = React;

function App() {
    const [activeTab, setActiveTab] = useState('map');
    const [project, setProject] = useState('factory1');
    const [projectList, setProjectList] = useState(['factory1']);
    const [schemas, setSchemas] = useState({});
    const [recipes, setRecipes] = useState({});
    
    useEffect(() => {
        // Fetch list of projects on mount
        window.API.request('/api/projects').then(data => {
            if (data && data.projects && data.projects.length > 0) {
                setProjectList(data.projects);
                if (!data.projects.includes(project)) {
                    setProject(data.projects[0]);
                }
            }
        }).catch(e => console.error("Failed to load projects list"));
    }, []);

    // Auto-save debouncer could go here, but for now we manually save or save on change
    const loadProjectData = async (projName) => {
        try {
            const schemasData = await window.API.request(`/api/schemas/${projName}`);
            const recipesData = await window.API.request(`/api/recipes/${projName}`);
            setSchemas(schemasData || {});
            setRecipes(recipesData || {});
        } catch (e) {
            console.error("Failed to load project data", e);
        }
    };
    
    useEffect(() => {
        loadProjectData(project);
    }, [project]);

    const saveSchemas = async (newSchemas) => {
        setSchemas(newSchemas);
        await window.API.request(`/api/schemas/${project}`, {
            method: 'POST',
            body: JSON.stringify(newSchemas)
        });
    };

    const saveRecipes = async (newRecipes) => {
        setRecipes(newRecipes);
        await window.API.request(`/api/recipes/${project}`, {
            method: 'POST',
            body: JSON.stringify(newRecipes)
        });
    };
    
    // Count stubs
    const stubCount = Object.values(schemas).filter(s => s.is_stub).length;

    return (
        <React.Fragment>
            <div className="topbar">
                <div style={{fontWeight: 'bold', color: 'white', marginRight: '32px'}}>OHT Builder</div>
                <button className={`tab-btn ${activeTab === 'map' ? 'active' : ''}`} onClick={() => setActiveTab('map')}>Map Builder</button>
                <button className={`tab-btn ${activeTab === 'machine' ? 'active' : ''}`} onClick={() => setActiveTab('machine')}>
                    Machine Designer {stubCount > 0 && <span className="badge">{stubCount}</span>}
                </button>
                <button className={`tab-btn ${activeTab === 'recipe' ? 'active' : ''}`} onClick={() => setActiveTab('recipe')}>Recipe Manager</button>
                
                <div style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px'}}>
                    <span style={{fontSize: '12px', color: '#94a3b8'}}>Project:</span>
                    <select 
                        value={project} 
                        onChange={e => setProject(e.target.value)}
                        style={{width: '120px', padding: '4px'}}
                    >
                        {projectList.map(p => (
                            <option key={p} value={p}>{p}</option>
                        ))}
                    </select>
                    <button 
                        className="action-btn" 
                        style={{padding: '4px 8px'}}
                        onClick={() => {
                            const newProj = prompt("Enter new project name:");
                            if (newProj && newProj.trim()) {
                                const cleanName = newProj.trim().replace(/[^a-zA-Z0-9_-]/g, '');
                                if (cleanName) {
                                    setProjectList(prev => [...new Set([...prev, cleanName])]);
                                    setProject(cleanName);
                                }
                            }
                        }}
                    >
                        New
                    </button>
                </div>
            </div>

            {/* Tab Contents - Keep all mounted to avoid canvas reload */}
            <div className="workspace">
                <div style={{ flex: 1, display: activeTab === 'map' ? 'block' : 'none' }}>
                    <MapBuilderTab project={project} schemas={schemas} recipes={recipes} />
                </div>
                <div style={{ flex: 1, display: activeTab === 'machine' ? 'block' : 'none' }}>
                    <MachineDesignerTab schemas={schemas} saveSchemas={saveSchemas} />
                </div>
                <div style={{ flex: 1, display: activeTab === 'recipe' ? 'block' : 'none' }}>
                    <RecipeManagerTab recipes={recipes} saveRecipes={saveRecipes} schemas={schemas} />
                </div>
            </div>
        </React.Fragment>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
