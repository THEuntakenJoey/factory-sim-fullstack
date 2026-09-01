/**
 * OHT Track Builder & Canvas Engine
 * Coordinate System: Heading 0 = North (+Y), 90 = East (+X), 180 = South (-Y), 270 = West (-X).
 * Track Types: STRAIGHT, TURN_L, TURN_R, DIVERGE_L, DIVERGE_R, MERGE_L, MERGE_R
 */
window.Builder = {
    tracks: [],
    machines: [],
    projectSchemas: {},
    machineSchemaId: null,
    nodes: {},
    selectedTrackId: null,
    selectedMachineId: null,
    activeTool: "STRAIGHT",
    toolHeading: 0,
    straightLength: 1.0,
    turnRadius: 0.5,

    view: { panX: 0, panY: 0, zoom: 120 },
    mouse: { x: 0, y: 0, worldX: 0, worldY: 0, isPanning: false, dragStart: {x:0, y:0}, snapped: false, snapPos: {x:0, y:0}, snapTargetNode: null },
    
    canvas: null,
    ctx: null,
    onStateChange: null,

    init: function(canvas, onStateChange) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onStateChange = onStateChange;

        const rect = canvas.getBoundingClientRect();
        this.view.panX = rect.width / 2;
        this.view.panY = rect.height / 2;

        this._setupEvents();
        this._startRenderLoop();
    },

    
    setProjectSchemas: function(schemas) {
        this.projectSchemas = schemas;
    },

    setMachineSchema: function(schemaId) {
        this.machineSchemaId = schemaId;
    },

    setTool: function(tool) {
        this.activeTool = tool;
        if (tool) {
            this.selectedTrackId = null;
            this.selectedMachineId = null;
        }
        this._notify();
    },

    rotateTool: function() {
        this.toolHeading = (this.toolHeading + 90) % 360;
        this._notify();
    },

    setStraightLength: function(trackId, newLength) {
        const len = Math.max(0.2, Math.min(20.0, parseFloat(newLength) || 1.0));
        const tr = this.tracks.find(t => t.id === trackId);
        if (tr && tr.type === "STRAIGHT") {
            tr.length = len;
            this._recomputeAllNodes();
            this._notify();
        }
    },

    deleteTrack: function(trackId) {
        this.tracks = this.tracks.filter(t => t.id !== trackId);
        if (this.selectedTrackId === trackId) this.selectedTrackId = null;
        // Clean up ports connecting to deleted track
        this.machines.forEach(m => {
            m.ports = m.ports.filter(p => p.trackId !== trackId);
        });
        this._recomputeAllNodes();
        this._notify();
    },

    deleteMachine: function(machineId) {
        this.machines = this.machines.filter(m => m.id !== machineId);
        if (this.selectedMachineId === machineId) this.selectedMachineId = null;
        this._notify();
    },

    clear: function() {
        this.tracks = [];
        this.machines = [];
        this.nodes = {};
        this.selectedTrackId = null;
        this.selectedMachineId = null;
        this._notify();
    },

    _notify: function() {
        if (this.onStateChange) {
            this.onStateChange({
                activeTool: this.activeTool,
                toolHeading: this.toolHeading,
                selectedTrack: this.getSelectedTrack(),
                selectedMachine: this.getSelectedMachine(),
                trackCount: this.tracks.length,
                machineCount: this.machines.length
            });
        }
    },

    getSelectedTrack: function() {
        return this.tracks.find(t => t.id === this.selectedTrackId) || null;
    },
    
    getSelectedMachine: function() {
        return this.machines.find(m => m.id === this.selectedMachineId) || null;
    },

    screenToWorld: function(sx, sy) {
        return {
            x: (sx - this.view.panX) / this.view.zoom,
            y: (this.view.panY - sy) / this.view.zoom // +Y is up
        };
    },

    worldToScreen: function(wx, wy) {
        return {
            x: this.view.panX + wx * this.view.zoom,
            y: this.view.panY - wy * this.view.zoom
        };
    },

    _normAng: function(a) {
        let ang = a % 360;
        if (ang < 0) ang += 360;
        return ang;
    },
    
    // Convert heading (0=N, 90=E) to vector (dx, dy)
    _dir: function(h) {
        const rad = h * Math.PI / 180;
        return { x: Math.sin(rad), y: Math.cos(rad) };
    },

    computeGeometry: function(type, x, y, heading, length = 1.0) {
        const R = this.turnRadius;
        let inputs = [];
        let outputs = [];
        
        const d_fwd = this._dir(heading);
        const d_right = this._dir(heading + 90);
        const d_left = this._dir(heading - 90);
        const d_back = this._dir(heading + 180);

        if (type === "STRAIGHT") {
            inputs.push({ x, y, heading });
            outputs.push({ x: x + length * d_fwd.x, y: y + length * d_fwd.y, heading });
        } 
        else if (type === "TURN_R") {
            inputs.push({ x, y, heading });
            const cx = x + R * d_right.x;
            const cy = y + R * d_right.y;
            outputs.push({ x: cx + R * d_fwd.x, y: cy + R * d_fwd.y, heading: this._normAng(heading + 90) });
        } 
        else if (type === "TURN_L") {
            inputs.push({ x, y, heading });
            const cx = x + R * d_left.x;
            const cy = y + R * d_left.y;
            outputs.push({ x: cx + R * d_fwd.x, y: cy + R * d_fwd.y, heading: this._normAng(heading - 90) });
        } 
        else if (type === "DIVERGE_R") {
            inputs.push({ x, y, heading });
            outputs.push({ x: x + 0.5 * d_fwd.x, y: y + 0.5 * d_fwd.y, heading, branch: "straight" });
            const cx = x + R * d_right.x;
            const cy = y + R * d_right.y;
            outputs.push({ x: cx + R * d_fwd.x, y: cy + R * d_fwd.y, heading: this._normAng(heading + 90), branch: "turn" });
        }
        else if (type === "DIVERGE_L") {
            inputs.push({ x, y, heading });
            outputs.push({ x: x + 0.5 * d_fwd.x, y: y + 0.5 * d_fwd.y, heading, branch: "straight" });
            const cx = x + R * d_left.x;
            const cy = y + R * d_left.y;
            outputs.push({ x: cx + R * d_fwd.x, y: cy + R * d_fwd.y, heading: this._normAng(heading - 90), branch: "turn" });
        }
        else if (type === "MERGE_R") {
            inputs.push({ x, y, heading, branch: "straight" });
            const in2X = x + R * d_right.x;
            const in2Y = y + R * d_right.y;
            inputs.push({ x: in2X, y: in2Y, heading: this._normAng(heading - 90), branch: "turn" });
            
            outputs.push({ x: x + 0.5 * d_fwd.x, y: y + 0.5 * d_fwd.y, heading });
        }
        else if (type === "MERGE_L") {
            inputs.push({ x, y, heading, branch: "straight" });
            const in2X = x + R * d_left.x;
            const in2Y = y + R * d_left.y;
            inputs.push({ x: in2X, y: in2Y, heading: this._normAng(heading + 90), branch: "turn" });
            
            outputs.push({ x: x + 0.5 * d_fwd.x, y: y + 0.5 * d_fwd.y, heading });
        }

        return { inputs, outputs };
    },

    _recomputeAllNodes: function() {
        this.nodes = {};
        this.tracks.forEach((tr, idx) => {
            const geo = this.computeGeometry(tr.type, tr.x, tr.y, tr.heading, tr.length);
            tr.inputs = geo.inputs.map((inNode, i) => {
                const nid = `${tr.id}_in_${i}`;
                this.nodes[nid] = { id: nid, ...inNode, trackId: tr.id };
                return nid;
            });
            tr.outputs = geo.outputs.map((outNode, i) => {
                const nid = `${tr.id}_out_${i}`;
                this.nodes[nid] = { id: nid, ...outNode, trackId: tr.id };
                return nid;
            });
        });
    },

    _checkSnap: function(type, rawX, rawY, heading) {
        const previewGeo = this.computeGeometry(type, rawX, rawY, heading, this.straightLength);
        const snapThreshold = 0.35;

        // Check if any preview INPUT snaps to existing OUTPUT (Append)
        for (const pIn of previewGeo.inputs) {
            for (const nid in this.nodes) {
                if (!nid.includes("_out")) continue;
                const eOut = this.nodes[nid];
                if (Math.hypot(eOut.x - pIn.x, eOut.y - pIn.y) < snapThreshold) {
                    if (this._normAng(eOut.heading) === this._normAng(pIn.heading)) {
                        return { snapped: true, x: rawX + (eOut.x - pIn.x), y: rawY + (eOut.y - pIn.y), targetNode: eOut };
                    }
                }
            }
        }

        // Check if any preview OUTPUT snaps to existing INPUT (Prepend)
        for (const pOut of previewGeo.outputs) {
            for (const nid in this.nodes) {
                if (!nid.includes("_in")) continue;
                const eIn = this.nodes[nid];
                if (Math.hypot(eIn.x - pOut.x, eIn.y - pOut.y) < snapThreshold) {
                    if (this._normAng(eIn.heading) === this._normAng(pOut.heading)) {
                        return { snapped: true, x: rawX + (eIn.x - pOut.x), y: rawY + (eIn.y - pOut.y), targetNode: eIn };
                    }
                }
            }
        }

        return { snapped: false, x: rawX, y: rawY, targetNode: null };
    },

    _setupEvents: function() {
        if (this._eventsSetup) return;
        this._eventsSetup = true;
        const c = this.canvas;

        c.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (this.activeTool) this.rotateTool();
        });

        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.selectedTrackId = null;
                this.activeTool = null;
                this._notify();
            }
        });

        c.addEventListener('mousedown', (e) => {
            if (e.button === 1) e.preventDefault(); // Prevent middle-click scroll behavior
            const rect = c.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;

            if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
                this.mouse.isPanning = true;
                this.mouse.dragStart = { x: sx, y: sy };
                return;
            }
            
            

            // Normal click to pan if empty space and no tool
            if (!this.activeTool && e.button === 0 && !this._getTrackAt(this.mouse.worldX, this.mouse.worldY) && !this._getMachineAt(this.mouse.worldX, this.mouse.worldY)) {
                this.mouse.isPanning = true;
                this.mouse.dragStart = { x: sx, y: sy };
                return;
            }

            if (e.button === 0) {
                if (this.activeTool) {
                    if (this.activeTool === "MACHINE") {
                        if (!this.machineSchemaId || !this.projectSchemas[this.machineSchemaId]) {
                            alert("Please select a machine schema first.");
                            return;
                        }
                        
                        const schema = this.projectSchemas[this.machineSchemaId];
                        const placeX = this.mouse.machineSnapped ? this.mouse.machineSnapPos.x : this.mouse.worldX;
                        const placeY = this.mouse.machineSnapped ? this.mouse.machineSnapPos.y : this.mouse.worldY;
                        
                        // Map the ports based on the placement and heading
                        const mappedPorts = [];
                        const cos = Math.cos(this.toolHeading * Math.PI / 180);
                        const sin = Math.sin(this.toolHeading * Math.PI / 180);
                        
                        (schema.ports || []).forEach(sp => {
                            const wx = placeX + (sp.rel_x * cos + sp.rel_y * sin);
                            const wy = placeY + (-sp.rel_x * sin + sp.rel_y * cos); 
                            
                            const track = this._getTrackAtExact(wx, wy);
                            if (track && track.type === "STRAIGHT") {
                                const d_fwd = this._dir(track.heading);
                                const vX = wx - track.x;
                                const vY = wy - track.y;
                                let t = (vX * d_fwd.x + vY * d_fwd.y);
                                t = Math.max(0, Math.min(track.length, t));
                                mappedPorts.push({
                                    schema_port_id: sp.id,
                                    trackId: track.id,
                                    offset: t
                                });
                            }
                        });

                        const newMachine = {
                            id: `mach_${Date.now().toString().slice(-5)}`,
                            type: "MACHINE",
                            machine_type: "PROCESS", // legacy
                            schema_id: this.machineSchemaId,
                            x: placeX,
                            y: placeY,
                            heading: this.toolHeading,
                            connected_ports: mappedPorts
                        };
                        this.machines.push(newMachine);
                        this.selectedMachineId = newMachine.id;
                        this.selectedTrackId = null;
                        this.activeTool = null;
                        this._notify();
                        return;
                    }

                    const placeX = this.mouse.snapped ? this.mouse.snapPos.x : this.mouse.worldX;
                    const placeY = this.mouse.snapped ? this.mouse.snapPos.y : this.mouse.worldY;

                    const newTrack = {
                        id: `track_${Date.now().toString().slice(-5)}`,
                        type: this.activeTool,
                        x: placeX, y: placeY,
                        heading: this.toolHeading,
                        length: this.straightLength,
                        radius: this.turnRadius,
                        semaphore: this.activeTool.startsWith("MERGE") ? "auto" : undefined
                    };

                    this.tracks.push(newTrack);
                    this._recomputeAllNodes();
                    this.selectedTrackId = newTrack.id;
                    this.selectedMachineId = null;
                    this._notify();
                } else {
                    const clickedMachine = this._getMachineAt(this.mouse.worldX, this.mouse.worldY);
                    if (clickedMachine) {
                        this.selectedMachineId = clickedMachine.id;
                        this.selectedTrackId = null;
                    } else {
                        const clicked = this._getTrackAt(this.mouse.worldX, this.mouse.worldY);
                        this.selectedTrackId = clicked ? clicked.id : null;
                        this.selectedMachineId = null;
                    }
                    this._notify();
                }
            }
        });

        c.addEventListener('mousemove', (e) => {
            const rect = c.getBoundingClientRect();
            this.mouse.x = e.clientX - rect.left;
            this.mouse.y = e.clientY - rect.top;

            if (this.mouse.isPanning) {
                this.view.panX += this.mouse.x - this.mouse.dragStart.x;
                this.view.panY += this.mouse.y - this.mouse.dragStart.y;
                this.mouse.dragStart = { x: this.mouse.x, y: this.mouse.y };
                return;
            }

            const world = this.screenToWorld(this.mouse.x, this.mouse.y);
            this.mouse.worldX = world.x;
            this.mouse.worldY = world.y;

            if (this.activeTool === "MACHINE" && this.machineSchemaId && this.projectSchemas[this.machineSchemaId]) {
                const schema = this.projectSchemas[this.machineSchemaId];
                this.mouse.machineSnapped = false;
                this.mouse.machineSnapPos = { x: world.x, y: world.y };
                
                // Rotation matrix
                const cos = Math.cos(this.toolHeading * Math.PI / 180);
                const sin = Math.sin(this.toolHeading * Math.PI / 180);
                
                for (let sp of (schema.ports || [])) {
                    // Port position relative to machine center
                    const rx = sp.rel_x * cos + sp.rel_y * sin;
                    const ry = -sp.rel_x * sin + sp.rel_y * cos; 
                    const pwx = world.x + rx;
                    const pwy = world.y + ry;
                    
                    const track = this._getTrackAtExact(pwx, pwy, 1.0); // look for track within 1 unit
                    if (track && track.type === "STRAIGHT") {
                        // We found a track. Let's snap the machine so this port perfectly aligns on the track line.
                        // Calculate orthogonal projection
                        const d_fwd = this._dir(track.heading);
                        const vX = pwx - track.x;
                        const vY = pwy - track.y;
                        const t = (vX * d_fwd.x + vY * d_fwd.y);
                        
                        // The nearest point on the track line
                        const nx = track.x + t * d_fwd.x;
                        const ny = track.y + t * d_fwd.y;
                        
                        // Shift machine by (nx - pwx, ny - pwy)
                        this.mouse.machineSnapPos.x += (nx - pwx);
                        this.mouse.machineSnapPos.y += (ny - pwy);
                        this.mouse.machineSnapped = true;
                        break; // Snap to the first valid port
                    }
                }
            } else if (this.activeTool) {
                const snap = this._checkSnap(this.activeTool, world.x, world.y, this.toolHeading);
                this.mouse.snapped = snap.snapped;
                this.mouse.snapPos = { x: snap.x, y: snap.y };
                this.mouse.snapTargetNode = snap.targetNode;
            } else {
                this.mouse.snapped = false;
            }

        });

        window.addEventListener('mouseup', () => { this.mouse.isPanning = false; });

        c.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
            const newZoom = Math.max(30, Math.min(400, this.view.zoom * zoomFactor));

            const mouseBefore = this.screenToWorld(this.mouse.x, this.mouse.y);
            this.view.zoom = newZoom;
            const mouseAfter = this.screenToWorld(this.mouse.x, this.mouse.y);

            this.view.panX += (mouseAfter.x - mouseBefore.x) * this.view.zoom;
            this.view.panY -= (mouseAfter.y - mouseBefore.y) * this.view.zoom;
        });
    },

    
    _getTrackAtExact: function(wx, wy, threshold=0.5) {
        let best = null;
        let bestD = threshold;
        for (let i = this.tracks.length - 1; i >= 0; i--) {
            const tr = this.tracks[i];
            if (tr.type !== "STRAIGHT") continue;
            // distance point to line segment
            const d_fwd = this._dir(tr.heading);
            const vX = wx - tr.x;
            const vY = wy - tr.y;
            let t = (vX * d_fwd.x + vY * d_fwd.y);
            if (t < 0 || t > tr.length) continue;
            const projX = tr.x + t * d_fwd.x;
            const projY = tr.y + t * d_fwd.y;
            const dist = Math.hypot(wx - projX, wy - projY);
            if (dist < bestD) {
                bestD = dist;
                best = tr;
            }
        }
        return best;
    },

    _getTrackAt: function(wx, wy) {
        for (let i = this.tracks.length - 1; i >= 0; i--) {
            const tr = this.tracks[i];
            if (Math.hypot(tr.x - wx, tr.y - wy) < 0.6) return tr;
        }
        return null;
    },

    _getMachineAt: function(wx, wy) {
        for (let i = this.machines.length - 1; i >= 0; i--) {
            const m = this.machines[i];
            // Simple bounding box check (machine is 0.8x0.8 centered at m.x, m.y)
            if (Math.abs(m.x - wx) < 0.4 && Math.abs(m.y - wy) < 0.4) {
                return m;
            }
        }
        return null;
    },

    _addPortToMachine: function(machineId, track, wx, wy) {
        const machine = this.machines.find(m => m.id === machineId);
        if (!machine) return;

        // Calculate closest point on the straight track to the click position
        // A straight track goes from (tr.x, tr.y) along its heading for tr.length
        const d_fwd = this._dir(track.heading);
        const endX = track.x + track.length * d_fwd.x;
        const endY = track.y + track.length * d_fwd.y;

        // Vector from track start to click point
        const vX = wx - track.x;
        const vY = wy - track.y;
        
        // Dot product to find projection length along the track
        let t = (vX * d_fwd.x + vY * d_fwd.y);
        
        // Clamp to track segment
        t = Math.max(0, Math.min(track.length, t));

        machine.ports.push({
            trackId: track.id,
            offset: t
        });
        
        this._notify();
    },

    _startRenderLoop: function() {
        const render = () => {
            this._draw();
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    },

    _draw: function() {
        const c = this.canvas;
        const ctx = this.ctx;
        if (!c || !ctx) return;

        const rect = c.getBoundingClientRect();
        if (c.width !== rect.width || c.height !== rect.height) {
            c.width = rect.width;
            c.height = rect.height;
        }

        ctx.clearRect(0, 0, c.width, c.height);

        this._drawGrid();

        this.tracks.forEach(tr => {
            const isSelected = tr.id === this.selectedTrackId;
            this._drawTrack(tr, isSelected ? "#eab308" : "#38bdf8", isSelected ? 8 : 4);
        });

        this.machines.forEach(m => {
            const isSelected = m.id === this.selectedMachineId;
            this._drawMachine(m, isSelected ? "#eab308" : "#c084fc");
        });

        for (const nid in this.nodes) {
            const n = this.nodes[nid];
            const s = this.worldToScreen(n.x, n.y);
            ctx.beginPath();
            ctx.arc(s.x, s.y, nid.includes("_in") ? 4 : 5, 0, 2 * Math.PI);
            ctx.fillStyle = nid.includes("_in") ? "#3b82f6" : "#10b981";
            ctx.fill();
        }

        if (this.activeTool) {
            const px = this.mouse.snapped ? this.mouse.snapPos.x : this.mouse.worldX;
            const py = this.mouse.snapped ? this.mouse.snapPos.y : this.mouse.worldY;
            
            if (this.activeTool === "MACHINE") {
                this._drawMachine({ x: px, y: py, width: 0.8, height: 0.8, type: "MACHINE", capacity: 1, ports: [] }, "rgba(192, 132, 252, 0.5)");
            } else {
                const preview = { type: this.activeTool, x: px, y: py, heading: this.toolHeading, length: this.straightLength, radius: this.turnRadius };
                this._drawTrack(preview, "rgba(56, 189, 248, 0.5)", 4, true);
            }

            if (this.mouse.snapped && this.mouse.snapTargetNode) {
                const sp = this.worldToScreen(this.mouse.snapTargetNode.x, this.mouse.snapTargetNode.y);
                ctx.beginPath();
                ctx.arc(sp.x, sp.y, 14, 0, 2 * Math.PI);
                ctx.strokeStyle = "#4ade80";
                ctx.lineWidth = 3;
                ctx.setLineDash([4, 4]);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }
    },

    _drawGrid: function() {
        const c = this.canvas;
        const ctx = this.ctx;
        
        // Background
        ctx.fillStyle = "#0f172a";
        ctx.fillRect(0, 0, c.width, c.height);

        const minW = this.screenToWorld(0, c.height);
        const maxW = this.screenToWorld(c.width, 0);

        ctx.strokeStyle = "#1e293b";
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let x = Math.floor(minW.x * 5) / 5; x <= Math.ceil(maxW.x * 5) / 5; x += 0.2) {
            const p = this.worldToScreen(x, 0);
            ctx.moveTo(p.x, 0);
            ctx.lineTo(p.x, c.height);
        }
        for (let y = Math.floor(minW.y * 5) / 5; y <= Math.ceil(maxW.y * 5) / 5; y += 0.2) {
            const p = this.worldToScreen(0, y);
            ctx.moveTo(0, p.y);
            ctx.lineTo(c.width, p.y);
        }
        ctx.stroke();

        ctx.strokeStyle = "#333b48";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let x = Math.floor(minW.x); x <= Math.ceil(maxW.x); x += 1.0) {
            const p = this.worldToScreen(x, 0);
            ctx.moveTo(p.x, 0);
            ctx.lineTo(p.x, c.height);
        }
        for (let y = Math.floor(minW.y); y <= Math.ceil(maxW.y); y += 1.0) {
            const p = this.worldToScreen(0, y);
            ctx.moveTo(0, p.y);
            ctx.lineTo(c.width, p.y);
        }
        ctx.stroke();

        const origin = this.worldToScreen(0, 0);
        ctx.strokeStyle = "#475569";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(origin.x - 10, origin.y); ctx.lineTo(origin.x + 10, origin.y);
        ctx.moveTo(origin.x, origin.y - 10); ctx.lineTo(origin.x, origin.y + 10);
        ctx.stroke();
    },

    _drawMachine: function(m, color) {
        const ctx = this.ctx;
        const center = this.worldToScreen(m.x, m.y);
        const w = (m.width || 0.8) * this.view.zoom;
        const h = (m.height || 0.8) * this.view.zoom;

        // Draw dashed lines to ports
        if (m.ports) {
            ctx.strokeStyle = "#64748b";
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            m.ports.forEach(port => {
                const tr = this.tracks.find(t => t.id === port.trackId);
                if (tr) {
                    const d_fwd = this._dir(tr.heading);
                    const px = tr.x + port.offset * d_fwd.x;
                    const py = tr.y + port.offset * d_fwd.y;
                    const pScreen = this.worldToScreen(px, py);
                    
                    ctx.beginPath();
                    ctx.moveTo(center.x, center.y);
                    ctx.lineTo(pScreen.x, pScreen.y);
                    ctx.stroke();

                    // Draw port connection dot
                    ctx.beginPath();
                    ctx.arc(pScreen.x, pScreen.y, 4, 0, 2*Math.PI);
                    ctx.fillStyle = "#8b5cf6";
                    ctx.fill();
                }
            });
            ctx.setLineDash([]);
        }

        // Draw machine box
        ctx.fillStyle = "#1e293b";
        ctx.fillRect(center.x - w/2, center.y - h/2, w, h);
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(center.x - w/2, center.y - h/2, w, h);

        // Draw text label
        ctx.fillStyle = "#f8fafc";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(m.machine_type || "MACHINE", center.x, center.y - 10);
        ctx.fillStyle = "#a78bfa";
        ctx.fillText(`[0/${m.capacity || 1}]`, center.x, center.y + 10);
    },

    _drawPathPoints: function(points) {
        if (points.length === 0) return;
        const ctx = this.ctx;
        ctx.beginPath();
        const start = this.worldToScreen(points[0].x, points[0].y);
        ctx.moveTo(start.x, start.y);
        for(let i=1; i<points.length; i++) {
            const p = this.worldToScreen(points[i].x, points[i].y);
            ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
    },

    _getCurvePoints: function(x, y, heading, isRight) {
        const R = this.turnRadius;
        const points = [];
        const d_turn = this._dir(isRight ? heading + 90 : heading - 90);
        const cx = x + R * d_turn.x;
        const cy = y + R * d_turn.y;
        
        // Generate points along the curve
        for (let i = 0; i <= 90; i += 10) {
            const ht = isRight ? heading + i : heading - i;
            const d_arm = this._dir(isRight ? ht + 90 : ht - 90);
            points.push({ x: cx - R * d_arm.x, y: cy - R * d_arm.y });
        }
        return points;
    },

    _getTrackPoints: function(tr) {
        const d_fwd = this._dir(tr.heading);
        const L = tr.length || 1.0;
        let points = [];

        if (tr.type === "STRAIGHT") {
            const steps = Math.ceil(L / 0.1);
            for(let i=0; i<=steps; i++) {
                points.push({ x: tr.x + (i/steps)*L*d_fwd.x, y: tr.y + (i/steps)*L*d_fwd.y });
            }
        }
        else if (tr.type === "TURN_R" || tr.type === "TURN_L") {
            const isRight = tr.type === "TURN_R";
            points = this._getCurvePoints(tr.x, tr.y, tr.heading, isRight);
        }
        else if (tr.type === "DIVERGE_R" || tr.type === "DIVERGE_L") {
            const isRight = tr.type === "DIVERGE_R";
            const steps = Math.ceil(0.5 / 0.1);
            for(let i=0; i<=steps; i++) {
                points.push({ x: tr.x + (i/steps)*0.5*d_fwd.x, y: tr.y + (i/steps)*0.5*d_fwd.y });
            }
            points = points.concat(this._getCurvePoints(tr.x, tr.y, tr.heading, isRight));
        }
        else if (tr.type === "MERGE_R" || tr.type === "MERGE_L") {
            const isRight = tr.type === "MERGE_R";
            const steps = Math.ceil(0.5 / 0.1);
            for(let i=0; i<=steps; i++) {
                // straight branch
                points.push({ x: tr.x + (i/steps)*0.5*d_fwd.x, y: tr.y + (i/steps)*0.5*d_fwd.y });
            }
            
            const R = this.turnRadius;
            const d_side = this._dir(isRight ? tr.heading + 90 : tr.heading - 90);
            const in2X = tr.x + R * d_side.x;
            const in2Y = tr.y + R * d_side.y;
            const in2Heading = isRight ? this._normAng(tr.heading - 90) : this._normAng(tr.heading + 90);
            points = points.concat(this._getCurvePoints(in2X, in2Y, in2Heading, isRight));
        }
        return points;
    },

    _drawTrack: function(tr, color, width = 4, isPreview = false) {
        const ctx = this.ctx;
        
        let drawColor = color;
        if (!isPreview && tr.status) {
            if (tr.status === "error") drawColor = "#ef4444"; // Red
            else if (tr.status === "warning") drawColor = "#f97316"; // Orange
        }

        ctx.strokeStyle = drawColor;
        ctx.lineWidth = width;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        const d_fwd = this._dir(tr.heading);
        const L = tr.length || 1.0;
        const R = this.turnRadius;

        if (tr.type === "STRAIGHT") {
            this._drawPathPoints([
                {x: tr.x, y: tr.y},
                {x: tr.x + L * d_fwd.x, y: tr.y + L * d_fwd.y}
            ]);
            const mid = this.worldToScreen(tr.x + (L/2)*d_fwd.x, tr.y + (L/2)*d_fwd.y);
            this._drawArrow(mid.x, mid.y, tr.heading, drawColor);
        }
        else if (tr.type === "TURN_R" || tr.type === "TURN_L") {
            const isRight = tr.type === "TURN_R";
            const pts = this._getCurvePoints(tr.x, tr.y, tr.heading, isRight);
            this._drawPathPoints(pts);
            const midP = pts[Math.floor(pts.length/2)];
            const midS = this.worldToScreen(midP.x, midP.y);
            this._drawArrow(midS.x, midS.y, isRight ? tr.heading + 45 : tr.heading - 45, drawColor);
        }
        else if (tr.type === "DIVERGE_R" || tr.type === "DIVERGE_L") {
            const isRight = tr.type === "DIVERGE_R";
            this._drawPathPoints([
                {x: tr.x, y: tr.y},
                {x: tr.x + 0.5 * d_fwd.x, y: tr.y + 0.5 * d_fwd.y}
            ]);
            const pts = this._getCurvePoints(tr.x, tr.y, tr.heading, isRight);
            this._drawPathPoints(pts);
        }
        else if (tr.type === "MERGE_R" || tr.type === "MERGE_L") {
            const isRight = tr.type === "MERGE_R";
            
            // Straight branch
            this._drawPathPoints([
                {x: tr.x, y: tr.y},
                {x: tr.x + 0.5 * d_fwd.x, y: tr.y + 0.5 * d_fwd.y}
            ]);
            
            // Turn branch
            const d_side = this._dir(isRight ? tr.heading + 90 : tr.heading - 90);
            const in2X = tr.x + R * d_side.x;
            const in2Y = tr.y + R * d_side.y;
            const in2Heading = isRight ? this._normAng(tr.heading - 90) : this._normAng(tr.heading + 90);
            
            const pts = this._getCurvePoints(in2X, in2Y, in2Heading, isRight);
            this._drawPathPoints(pts);
        }
    },

    _drawArrow: function(sx, sy, heading, color) {
        const ctx = this.ctx;
        // In screen coordinates, positive angle is clockwise. So +X is 0, +Y is 90.
        // Our world: 0=N, 90=E. 
        // 0=N -> screen (0, -1) -> angle -90
        // 90=E -> screen (1, 0) -> angle 0
        // So screenRad = (heading - 90) * PI/180
        const rad = (heading - 90) * Math.PI / 180;
        const size = 6;

        ctx.save();
        ctx.translate(sx, sy);
        ctx.rotate(rad);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(size, 0);
        ctx.lineTo(-size, -size * 0.7);
        ctx.lineTo(-size, size * 0.7);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    },

    verifyMap: function() {
        const errors = [];
        const warnings = [];
        this._recomputeAllNodes();
        
        // Reset track status
        this.tracks.forEach(tr => tr.status = null);

        // Group nodes by physical location (quantize to 1mm to avoid floating point errors)
        const locs = {};
        for (const nid in this.nodes) {
            const node = this.nodes[nid];
            const key = `${Math.round(node.x * 1000)},${Math.round(node.y * 1000)}`;
            if (!locs[key]) locs[key] = { ins: [], outs: [] };
            if (nid.includes("_in")) locs[key].ins.push(node);
            else locs[key].outs.push(node);
        }

        const markTrack = (trackId, status) => {
            const tr = this.tracks.find(t => t.id === trackId);
            if (tr) {
                // don't overwrite error with warning
                if (tr.status !== "error") tr.status = status; 
            }
        };

        // 1. Connection logic
        for (const key in locs) {
            const { ins, outs } = locs[key];
            
            if (ins.length > 1) {
                errors.push(`Multiple tracks inputting at same location (${ins[0].x.toFixed(2)}, ${ins[0].y.toFixed(2)}).`);
                ins.forEach(n => markTrack(n.trackId, "error"));
            }
            if (outs.length > 1) {
                errors.push(`Multiple tracks outputting at same location (${outs[0].x.toFixed(2)}, ${outs[0].y.toFixed(2)}).`);
                outs.forEach(n => markTrack(n.trackId, "error"));
            }

            if (ins.length === 1 && outs.length === 1) {
                const inN = ins[0];
                const outN = outs[0];
                if (this._normAng(inN.heading) !== this._normAng(outN.heading)) {
                    errors.push(`Heading Mismatch at (${inN.x.toFixed(2)}, ${inN.y.toFixed(2)}): ${outN.heading}° -> ${inN.heading}°`);
                    markTrack(inN.trackId, "error");
                    markTrack(outN.trackId, "error");
                }
            }

            if (ins.length === 0 && outs.length > 0) {
                warnings.push(`Loose End: output at (${outs[0].x.toFixed(2)}, ${outs[0].y.toFixed(2)}) is not connected.`);
                outs.forEach(n => markTrack(n.trackId, "warning"));
            }
        }

        // 2. Track Collision / Overlap logic (discretized points)
        const trackPoints = this.tracks.map(tr => ({
            id: tr.id,
            points: this._getTrackPoints(tr)
        }));

        for(let i = 0; i < trackPoints.length; i++) {
            for(let j = i + 1; j < trackPoints.length; j++) {
                const trA = trackPoints[i];
                const trB = trackPoints[j];
                let collided = false;

                // Check distance between every point pair
                for(const pA of trA.points) {
                    for(const pB of trB.points) {
                        const dist = Math.hypot(pA.x - pB.x, pA.y - pB.y);
                        // Check if points are overlapping (< 0.05m) but NOT near the ends 
                        // (endpoints are allowed to touch if they are valid connections)
                        if (dist < 0.05) {
                            // Are these endpoints connecting?
                            // We already validated connection counts above.
                            // If they are touching strictly in the middle of a track, it's an overlap.
                            // Let's just do a simple check: if they share a physical node location, it's okay.
                            const keyA = `${Math.round(pA.x * 1000)},${Math.round(pA.y * 1000)}`;
                            if (!locs[keyA] || (locs[keyA].ins.length + locs[keyA].outs.length < 2)) {
                                collided = true;
                                break;
                            }
                        }
                    }
                    if (collided) break;
                }
                if (collided) {
                    errors.push(`Track ${trA.id} overlaps with ${trB.id}.`);
                    markTrack(trA.id, "error");
                    markTrack(trB.id, "error");
                }
            }
        }

        return { errors, warnings };
    },

    runTests: function() {
        let results = [];
        const backupTracks = JSON.parse(JSON.stringify(this.tracks));

        this.clear();
        this.tracks = [
            { id: "t1", type: "STRAIGHT", x: 0, y: 0, heading: 0, length: 1.0 },
            { id: "t2", type: "TURN_R", x: 0, y: 1.0, heading: 0, radius: 0.5 },
            { id: "t3", type: "TURN_R", x: 0.5, y: 1.5, heading: 90, radius: 0.5 }
        ];
        let res = this.verifyMap();
        results.push({ name: "Turn Angle & Continuity", passed: res.errors.length === 0 });

        this.clear();
        this.tracks = [
            { id: "div", type: "DIVERGE_R", x: 0, y: 0, heading: 0 },
            { id: "s1", type: "STRAIGHT", x: 0, y: 0.5, heading: 0, length: 0.5 },
            { id: "t1", type: "TURN_L", x: 0.5, y: 0.5, heading: 90, radius: 0.5 },
            { id: "merg", type: "MERGE_R", x: 0, y: 1.0, heading: 0, semaphore: "auto" }
        ];
        res = this.verifyMap();
        results.push({ name: "Diverge/Merge Topology", passed: res.errors.length === 0 });

        this.tracks = backupTracks;
        this._recomputeAllNodes();
        this._notify();
        return results;
    },

    saveGraph: function() {
        return { nodes: this.nodes, tracks: this.tracks, machines: this.machines };
    },
    
    loadGraph: function(data) {
        try {
            this.clear();
            if (data.tracks) {
                this.tracks = data.tracks;
                this.machines = data.machines || [];
                this._recomputeAllNodes();
                this._notify();
            }
        } catch (e) {
            alert("Error loading map: " + e.message);
        }
    }
};
