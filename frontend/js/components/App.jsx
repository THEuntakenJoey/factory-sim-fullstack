
const { useState, useEffect } = React;

function App() {
    const [activeTab, setActiveTab] = useState('map');
    const [project, setProject] = useState('factory1');
    const [schemas, setSchemas] = useState({});
    const [recipes, setRecipes] = useState({});
    
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
                    <input 
                        type="text" 
                        value={project} 
                        onChange={e => setProject(e.target.value)}
                        style={{width: '120px'}}
                    />
                </div>
            </div>

            <div className="workspace">
                {activeTab === 'map' && <MapBuilderTab project={project} schemas={schemas} />}
                {activeTab === 'machine' && <MachineDesignerTab schemas={schemas} saveSchemas={saveSchemas} />}
                {activeTab === 'recipe' && <RecipeManagerTab recipes={recipes} saveRecipes={saveRecipes} schemas={schemas} saveSchemas={saveSchemas} />}
            </div>
        </React.Fragment>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
