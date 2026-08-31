window.Renderer = {
    draw: function(canvas, state) {
        if (!canvas) return;
        
        // Handle DPI scaling
        const rect = canvas.getBoundingClientRect();
        if (canvas.width !== rect.width || canvas.height !== rect.height) {
            canvas.width = rect.width;
            canvas.height = rect.height;
        }

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Set view transform (very basic centering for now)
        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.scale(0.1, -0.1); // Scale down and flip Y axis to match math coords

        // 1. Draw Map/Machines (static bg)
        ctx.fillStyle = "#888";
        if (state.machines) {
            state.machines.forEach(m => {
                // In a real app, we'd lookup node coords. 
                // For now, just draw a placeholder block.
                ctx.fillRect(-500, -500, 1000, 1000); 
            });
        }

        // 2. Draw Agents
        if (state.agents) {
            state.agents.forEach(agent => {
                ctx.fillStyle = agent.cargo ? "#f59e0b" : "#3b82f6"; // Orange if loaded, Blue if empty
                ctx.beginPath();
                ctx.arc(agent.x, agent.y, 120, 0, 2 * Math.PI); // 120mm radius representing bot
                ctx.fill();
            });
        }
        
        ctx.restore();
    }
};
