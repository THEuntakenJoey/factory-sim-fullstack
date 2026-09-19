window.API = {
    socket: null,
    getBaseUrl: function() {
        if (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin.startsWith('http')) {
            return window.location.origin;
        }
        return "http://localhost:8000";
    },
    connect: function(url, onMessage) {
        this.socket = new WebSocket(url);
        this.socket.onopen = () => console.log("Connected to simulation server");
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };
        this.socket.onerror = (err) => console.error("WebSocket error:", err);
    },
    disconnect: function() {
        if (this.socket) {
            this.socket.close();
        }
    },
    send: function(payload) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(payload));
        }
    },
    
    // REST API Map management
    listMaps: async function(project) {
        const res = await fetch(`${this.getBaseUrl()}/api/maps/${project}`);
        if (res.ok) {
            const data = await res.json();
            return data.maps;
        }
        return [];
    },
    loadMap: async function(project, filename) {
        const res = await fetch(`${this.getBaseUrl()}/api/maps/${project}/${filename}`);
        if (res.ok) {
            return await res.json();
        }
        throw new Error("Failed to load map");
    },
    saveMap: async function(project, filename, data) {
        const res = await fetch(`${this.getBaseUrl()}/api/save_map/${project}/${filename}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error("Failed to save map");
        return await res.json();
    },

    // Unified Project Save
    saveProject: async function(project, payload) {
        const res = await fetch(`${this.getBaseUrl()}/api/projects/${project}/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Failed to save project (${res.statusText})`);
        }
        return await res.json();
    },

    // Project Creation
    createProject: async function(name) {
        const res = await fetch(`${this.getBaseUrl()}/api/projects/create`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Failed to create project (${res.statusText})`);
        }
        return await res.json();
    },

    saveSchemas: async function(project, schemas) {
        return this.request(`/api/schemas/${project}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(schemas)
        });
    },

    saveRecipes: async function(project, recipes) {
        return this.request(`/api/recipes/${project}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(recipes)
        });
    },
    
    // Generic request method for new endpoints
    request: async function(path, options = {}) {
        const url = `${this.getBaseUrl()}${path}`;
        const res = await fetch(url, options);
        if (res.ok) {
            return await res.json();
        }
        throw new Error(`API request failed: ${res.statusText}`);
    },
    verifyGraph: async function(graph) {
        // Mock verification for now until backend implements it
        return { is_valid: true, errored_pieces: [], loose_ends: [] };
    }
};
