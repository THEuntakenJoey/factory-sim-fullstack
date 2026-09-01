window.API = {
    socket: null,
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
        const res = await fetch(`http://localhost:8000/api/maps/${project}`);
        if (res.ok) {
            const data = await res.json();
            return data.maps;
        }
        return [];
    },
    loadMap: async function(project, filename) {
        const res = await fetch(`http://localhost:8000/api/maps/${project}/${filename}`);
        if (res.ok) {
            return await res.json();
        }
        throw new Error("Failed to load map");
    },
    saveMap: async function(project, filename, data) {
        const res = await fetch(`http://localhost:8000/api/save_map/${project}/${filename}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error("Failed to save map");
        return await res.json();
    },
    
    // Generic request method for new endpoints
    request: async function(path, options = {}) {
        const url = `http://localhost:8000${path}`;
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
