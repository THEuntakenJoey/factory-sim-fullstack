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
    onChange: null,
    isDirty: false,
    _loading: false,

    markDirty: function() {
        this.isDirty = true;
        if (typeof this.onChange === 'function') {
            this.onChange();
        }
    },

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

    rotateSelected: function() {
        if (this.selectedTrackId) {
            const tr = this.tracks.find(t => t.id === this.selectedTrackId);
            if (tr) {
                tr.heading = (tr.heading + 90) % 360;
                this._recomputeAllNodes();
                this._updateAllMachinePorts();
                this.markDirty();
                this._notify();
            }
        } else if (this.selectedMachineId) {
            const m = this.machines.find(mach => mach.id === this.selectedMachineId);
            if (m) {
                m.heading = ((m.heading || 0) + 90) % 360;
                this._updateMachinePorts(m);
                this.markDirty();
                this._notify();
            }
        }
    },

    setStraightLength: function(trackId, newLength) {
        const len = Math.max(0.2, Math.min(20.0, parseFloat(newLength) || 1.0));
        const tr = this.tracks.find(t => t.id === trackId);
        if (tr && tr.type === "STRAIGHT") {
            tr.length = len;
            this._recomputeAllNodes();
            this._notify();
            this.markDirty();
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
        this.markDirty();
    },

    deleteMachine: function(machineId) {
        this.machines = this.machines.filter(m => m.id !== machineId);
        if (this.selectedMachineId === machineId) this.selectedMachineId = null;
        this._notify();
        this.markDirty();
    },

    clear: function() {
        this.tracks = [];
        this.machines = [];
        this.nodes = {};
        this.selectedTrackId = null;
        this.selectedMachineId = null;
        this._notify();
        if (!this._loading) {
            this.markDirty();
        }
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

    _checkSnap: function(type, rawX, rawY, heading, straightLength, excludeTrackId = null) {
        const previewGeo = this.computeGeometry(type, rawX, rawY, heading, straightLength || this.straightLength);
        const snapThreshold = 0.35;

        // Check if any preview INPUT snaps to existing OUTPUT (Append)
        for (const pIn of previewGeo.inputs) {
            for (const nid in this.nodes) {
                if (!nid.includes("_out")) continue;
                const eOut = this.nodes[nid];
                if (excludeTrackId && eOut.trackId === excludeTrackId) continue;
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
                if (excludeTrackId && eIn.trackId === excludeTrackId) continue;
                if (Math.hypot(eIn.x - pOut.x, eIn.y - pOut.y) < snapThreshold) {
                    if (this._normAng(eIn.heading) === this._normAng(pOut.heading)) {
                        return { snapped: true, x: rawX + (eIn.x - pOut.x), y: rawY + (eIn.y - pOut.y), targetNode: eIn };
                    }
                }
            }
        }

        return { snapped: false, x: rawX, y: rawY, targetNode: null };
    },

    _checkMachineSnap: function(schema, rawX, rawY, heading) {
        if (!schema) return { snapped: false, x: rawX, y: rawY };
        const cos = Math.cos(heading * Math.PI / 180);
        const sin = Math.sin(heading * Math.PI / 180);
        let snappedPos = { x: rawX, y: rawY };
        let snapped = false;

        for (let sp of (schema.ports || [])) {
            const rx = sp.rel_x * cos + sp.rel_y * sin;
            const ry = -sp.rel_x * sin + sp.rel_y * cos; 
            const pwx = rawX + rx;
            const pwy = rawY + ry;
            
            const track = this._getTrackAtExact(pwx, pwy, 1.0);
            if (track && track.type === "STRAIGHT") {
                const d_fwd = this._dir(track.heading);
                const vX = pwx - track.x;
                const vY = pwy - track.y;
                const t = (vX * d_fwd.x + vY * d_fwd.y);
                const nx = track.x + t * d_fwd.x;
                const ny = track.y + t * d_fwd.y;
                
                snappedPos.x += (nx - pwx);
                snappedPos.y += (ny - pwy);
                snapped = true;
                break;
            }
        }
        return { snapped, x: snappedPos.x, y: snappedPos.y };
    },

    _updateMachinePorts: function(m) {
        const schema = this.projectSchemas[m.schema_id] || {};
        const cos = Math.cos((m.heading || 0) * Math.PI / 180);
        const sin = Math.sin((m.heading || 0) * Math.PI / 180);
        const mappedPorts = [];
        (schema.ports || []).forEach(sp => {
            const wx = m.x + (sp.rel_x * cos + sp.rel_y * sin);
            const wy = m.y + (-sp.rel_x * sin + sp.rel_y * cos); 
            const track = this._getTrackAtExact(wx, wy, 0.5);
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
        m.ports = mappedPorts;
        m.connected_ports = mappedPorts;
    },

    _updateAllMachinePorts: function() {
        this.machines.forEach(m => this._updateMachinePorts(m));
    },

    _distToSegment: function(px, py, x1, y1, x2, y2) {
        const dx = x2 - x1;
        const dy = y2 - y1;
        const lenSq = dx * dx + dy * dy;
        if (lenSq === 0) return Math.hypot(px - x1, py - y1);
        let t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
        t = Math.max(0, Math.min(1, t));
        const projX = x1 + t * dx;
        const projY = y1 + t * dy;
        return Math.hypot(px - projX, py - projY);
    },

    _getTrackSegments: function(tr) {
        const d_fwd = this._dir(tr.heading);
        const L = tr.length || 1.0;
        const R = this.turnRadius;
        const segments = [];

        const addPolyline = (pts) => {
            for (let i = 0; i < pts.length - 1; i++) {
                segments.push({ x1: pts[i].x, y1: pts[i].y, x2: pts[i + 1].x, y2: pts[i + 1].y });
            }
        };

        if (tr.type === "STRAIGHT") {
            segments.push({
                x1: tr.x,
                y1: tr.y,
                x2: tr.x + L * d_fwd.x,
                y2: tr.y + L * d_fwd.y
            });
        } else if (tr.type === "TURN_R" || tr.type === "TURN_L") {
            addPolyline(this._getCurvePoints(tr.x, tr.y, tr.heading, tr.type === "TURN_R"));
        } else if (tr.type === "DIVERGE_R" || tr.type === "DIVERGE_L") {
            segments.push({
                x1: tr.x,
                y1: tr.y,
                x2: tr.x + 0.5 * d_fwd.x,
                y2: tr.y + 0.5 * d_fwd.y
            });
            addPolyline(this._getCurvePoints(tr.x, tr.y, tr.heading, tr.type === "DIVERGE_R"));
        } else if (tr.type === "MERGE_R" || tr.type === "MERGE_L") {
            const isRight = tr.type === "MERGE_R";
            segments.push({
                x1: tr.x,
                y1: tr.y,
                x2: tr.x + 0.5 * d_fwd.x,
                y2: tr.y + 0.5 * d_fwd.y
            });
            const d_side = this._dir(isRight ? tr.heading + 90 : tr.heading - 90);
            const in2X = tr.x + R * d_side.x;
            const in2Y = tr.y + R * d_side.y;
            const in2Heading = isRight ? this._normAng(tr.heading - 90) : this._normAng(tr.heading + 90);
            addPolyline(this._getCurvePoints(in2X, in2Y, in2Heading, isRight));
        }
        return segments;
    },

    _distToTrack: function(tr, wx, wy) {
        const segments = this._getTrackSegments(tr);
        let minD = Infinity;
        for (let i = 0; i < segments.length; i++) {
            const seg = segments[i];
            const d = this._distToSegment(wx, wy, seg.x1, seg.y1, seg.x2, seg.y2);
            if (d < minD) minD = d;
        }
        return minD;
    },

    _distToMachine: function(m, wx, wy) {
        const schema = this.projectSchemas[m.schema_id] || {};
        const w = schema.width || m.width || 0.8;
        const h = schema.height || m.height || 0.8;
        
        const dx = wx - m.x;
        const dy = wy - m.y;
        const rad = (m.heading || 0) * Math.PI / 180;
        const cos = Math.cos(rad);
        const sin = Math.sin(rad);
        
        // Machine local rotated coords
        const localX = dx * cos - dy * sin;
        const localY = dx * sin + dy * cos;
        
        const halfW = w / 2;
        const halfH = h / 2;
        
        const clampedX = Math.max(-halfW, Math.min(halfW, localX));
        const clampedY = Math.max(-halfH, Math.min(halfH, localY));
        
        return Math.hypot(localX - clampedX, localY - clampedY);
    },

    _getObjectAt: function(wx, wy) {
        const maxThreshold = Math.max(0.2, 18 / this.view.zoom);
        let bestObj = null;
        let bestType = null;
        let bestDist = Infinity;

        // Check tracks first (since tracks are layered on top of machines)
        for (let i = this.tracks.length - 1; i >= 0; i--) {
            const tr = this.tracks[i];
            const d = this._distToTrack(tr, wx, wy);
            if (d < maxThreshold && d < bestDist) {
                bestDist = d;
                bestObj = tr;
                bestType = "TRACK";
            }
        }

        // If cursor is close to a track, prioritize the track
        if (bestObj && bestDist < maxThreshold * 0.75) {
            return { obj: bestObj, type: bestType, dist: bestDist };
        }

        // Check machines (under tracks)
        for (let i = this.machines.length - 1; i >= 0; i--) {
            const m = this.machines[i];
            const d = this._distToMachine(m, wx, wy);
            if (d === 0) {
                if (!bestObj || bestDist > 0.08) {
                    return { obj: m, type: "MACHINE", dist: 0 };
                }
            }
            if (d < maxThreshold && d < bestDist) {
                bestDist = d;
                bestObj = m;
                bestType = "MACHINE";
            }
        }

        if (bestObj) {
            return { obj: bestObj, type: bestType, dist: bestDist };
        }
        return null;
    },

    _getTrackAtExact: function(wx, wy, threshold = 0.5) {
        let best = null;
        let bestD = threshold;
        for (let i = this.tracks.length - 1; i >= 0; i--) {
            const tr = this.tracks[i];
            if (tr.type !== "STRAIGHT") continue;
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

    _getTrackAt: function(wx, wy, threshold) {
        const thresh = threshold !== undefined ? threshold : Math.max(0.2, 18 / this.view.zoom);
        let best = null;
        let bestD = thresh;
        for (let i = this.tracks.length - 1; i >= 0; i--) {
            const tr = this.tracks[i];
            const d = this._distToTrack(tr, wx, wy);
            if (d < bestD) {
                bestD = d;
                best = tr;
            }
        }
        return best;
    },

    _getMachineAt: function(wx, wy, threshold) {
        const thresh = threshold !== undefined ? threshold : Math.max(0.2, 18 / this.view.zoom);
        let best = null;
        let bestD = thresh;
        for (let i = this.machines.length - 1; i >= 0; i--) {
            const m = this.machines[i];
            const d = this._distToMachine(m, wx, wy);
            if (d < bestD) {
                bestD = d;
                best = m;
            }
        }
        return best;
    },

    _setupEvents: function() {
        if (this._eventsSetup) return;
        this._eventsSetup = true;
        const c = this.canvas;

        c.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (this.activeTool) {
                this.rotateTool();
            } else {
                this.rotateSelected();
            }
        });

        window.addEventListener('keydown', (e) => {
            // Ignore if user is typing in an input or textarea
            if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT')) {
                return;
            }
            if (e.key === 'r' || e.key === 'R') {
                if (this.activeTool) {
                    this.rotateTool();
                } else {
                    this.rotateSelected();
                }
                return;
            }
            if (e.key === 'Escape') {
                if (this.dragState && this.dragState.isDragging) {
                    const target = this.dragState.target;
                    target.x = this.dragState.originX;
                    target.y = this.dragState.originY;
                    if (this.dragState.targetType === "TRACK") {
                        this._recomputeAllNodes();
                        this._updateAllMachinePorts();
                    } else {
                        this._updateMachinePorts(target);
                    }
                    this.dragState = null;
                    this._notify();
                    return;
                }
                this.selectedTrackId = null;
                this.selectedMachineId = null;
                this.activeTool = null;
                this._notify();
            } else if (e.key === 'Delete' || e.key === 'Backspace') {
                if (this.selectedTrackId) {
                    this.deleteTrack(this.selectedTrackId);
                } else if (this.selectedMachineId) {
                    this.deleteMachine(this.selectedMachineId);
                }
            }
        });

        c.addEventListener('mousedown', (e) => {
            if (e.button === 1) e.preventDefault(); // Prevent middle-click scroll behavior
            const rect = c.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;
            const world = this.screenToWorld(sx, sy);
            this.mouse.worldX = world.x;
            this.mouse.worldY = world.y;

            if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
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
                        
                        const newMachine = {
                            id: `mach_${Date.now().toString().slice(-5)}`,
                            type: "MACHINE",
                            machine_type: "PROCESS", // legacy
                            schema_id: this.machineSchemaId,
                            x: placeX,
                            y: placeY,
                            heading: this.toolHeading,
                            ports: [],
                            connected_ports: []
                        };
                        this._updateMachinePorts(newMachine);
                        this.machines.push(newMachine);
                        this.selectedMachineId = newMachine.id;
                        this.selectedTrackId = null;
                        this.activeTool = null;
                        this._notify();
                        this.markDirty();
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
                    this.markDirty();
                } else {
                    // SELECT / MOVE mode: accurately hit-test placed objects
                    const hit = this._getObjectAt(world.x, world.y);
                    if (hit) {
                        if (hit.type === "MACHINE") {
                            this.selectedMachineId = hit.obj.id;
                            this.selectedTrackId = null;
                        } else {
                            this.selectedTrackId = hit.obj.id;
                            this.selectedMachineId = null;
                        }
                        this._notify();

                        // Arm drag state for the clicked/selected object
                        this.dragState = {
                            isDown: true,
                            isDragging: false,
                            target: hit.obj,
                            targetType: hit.type,
                            startScreenX: sx,
                            startScreenY: sy,
                            originX: hit.obj.x,
                            originY: hit.obj.y,
                            mouseStartWorldX: world.x,
                            mouseStartWorldY: world.y,
                            snapped: false,
                            snapTargetNode: null
                        };
                    } else {
                        // Clicked empty canvas: deselect and initiate pan
                        this.selectedTrackId = null;
                        this.selectedMachineId = null;
                        this.dragState = null;
                        this._notify();

                        this.mouse.isPanning = true;
                        this.mouse.dragStart = { x: sx, y: sy };
                    }
                }
            }
        });

        window.addEventListener('mousemove', (e) => {
            const rect = c.getBoundingClientRect();
            this.mouse.x = e.clientX - rect.left;
            this.mouse.y = e.clientY - rect.top;

            if (this.mouse.isPanning) {
                this.view.panX += this.mouse.x - this.mouse.dragStart.x;
                this.view.panY += this.mouse.y - this.mouse.dragStart.y;
                this.mouse.dragStart = { x: this.mouse.x, y: this.mouse.y };
                c.style.cursor = 'grabbing';
                return;
            }

            const world = this.screenToWorld(this.mouse.x, this.mouse.y);
            this.mouse.worldX = world.x;
            this.mouse.worldY = world.y;

            // Handle Drag & Drop of selected object
            if (this.dragState && this.dragState.isDown) {
                const screenDist = Math.hypot(this.mouse.x - this.dragState.startScreenX, this.mouse.y - this.dragState.startScreenY);
                if (screenDist > 4) {
                    this.dragState.isDragging = true;
                }

                if (this.dragState.isDragging) {
                    c.style.cursor = 'grabbing';
                    const deltaX = world.x - this.dragState.mouseStartWorldX;
                    const deltaY = world.y - this.dragState.mouseStartWorldY;
                    const rawX = this.dragState.originX + deltaX;
                    const rawY = this.dragState.originY + deltaY;

                    if (this.dragState.targetType === "TRACK") {
                        const tr = this.dragState.target;
                        const snap = this._checkSnap(tr.type, rawX, rawY, tr.heading, tr.length, tr.id);
                        if (snap.snapped) {
                            tr.x = snap.x;
                            tr.y = snap.y;
                            this.dragState.snapped = true;
                            this.dragState.snapTargetNode = snap.targetNode;
                        } else {
                            tr.x = rawX;
                            tr.y = rawY;
                            this.dragState.snapped = false;
                            this.dragState.snapTargetNode = null;
                        }
                        this._recomputeAllNodes();
                        this._updateAllMachinePorts();
                    } else if (this.dragState.targetType === "MACHINE") {
                        const m = this.dragState.target;
                        const schema = this.projectSchemas[m.schema_id] || {};
                        const snap = this._checkMachineSnap(schema, rawX, rawY, m.heading || 0);
                        if (snap.snapped) {
                            m.x = snap.x;
                            m.y = snap.y;
                            this.dragState.snapped = true;
                        } else {
                            m.x = rawX;
                            m.y = rawY;
                            this.dragState.snapped = false;
                        }
                        this._updateMachinePorts(m);
                    }
                    return;
                }
            }

            const isOverCanvas = e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
            if (!isOverCanvas) return;

            if (this.activeTool === "MACHINE" && this.machineSchemaId && this.projectSchemas[this.machineSchemaId]) {
                c.style.cursor = 'crosshair';
                const schema = this.projectSchemas[this.machineSchemaId];
                const snap = this._checkMachineSnap(schema, world.x, world.y, this.toolHeading);
                this.mouse.machineSnapped = snap.snapped;
                this.mouse.machineSnapPos = { x: snap.x, y: snap.y };
            } else if (this.activeTool) {
                c.style.cursor = 'crosshair';
                const snap = this._checkSnap(this.activeTool, world.x, world.y, this.toolHeading);
                this.mouse.snapped = snap.snapped;
                this.mouse.snapPos = { x: snap.x, y: snap.y };
                this.mouse.snapTargetNode = snap.targetNode;
            } else {
                this.mouse.snapped = false;
                const hover = this._getObjectAt(world.x, world.y);
                c.style.cursor = hover ? 'grab' : 'default';
            }
        });

        window.addEventListener('mouseup', () => { 
            this.mouse.isPanning = false; 

            if (this.dragState && this.dragState.isDown) {
                if (this.dragState.isDragging) {
                    const target = this.dragState.target;
                    const movedDist = Math.hypot(target.x - this.dragState.originX, target.y - this.dragState.originY);
                    if (movedDist > 0.001) {
                        if (this.dragState.targetType === "TRACK") {
                            this._recomputeAllNodes();
                            this._updateAllMachinePorts();
                        } else {
                            this._updateMachinePorts(target);
                        }
                        this.markDirty();
                        this._notify();
                    }
                }
                this.dragState = null;
            }
        });

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

        this.machines.forEach(m => {
            const isSelected = m.id === this.selectedMachineId;
            this._drawMachine(m, isSelected ? "#eab308" : "#c084fc");
        });

        this.tracks.forEach(tr => {
            const isSelected = tr.id === this.selectedTrackId;
            this._drawTrack(tr, isSelected ? "#eab308" : "#38bdf8", isSelected ? 8 : 4);
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
                const schema = (this.machineSchemaId && this.projectSchemas[this.machineSchemaId]) || {};
                this._drawMachine({
                    x: this.mouse.machineSnapped ? this.mouse.machineSnapPos.x : px,
                    y: this.mouse.machineSnapped ? this.mouse.machineSnapPos.y : py,
                    heading: this.toolHeading,
                    schema_id: this.machineSchemaId,
                    width: schema.width || 0.8,
                    height: schema.height || 0.8,
                    type: "MACHINE",
                    capacity: schema.capacity || 1,
                    ports: []
                }, "rgba(192, 132, 252, 0.7)");
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

        if (this.dragState && this.dragState.isDragging && this.dragState.snapped && this.dragState.snapTargetNode) {
            const sp = this.worldToScreen(this.dragState.snapTargetNode.x, this.dragState.snapTargetNode.y);
            ctx.beginPath();
            ctx.arc(sp.x, sp.y, 14, 0, 2 * Math.PI);
            ctx.strokeStyle = "#4ade80";
            ctx.lineWidth = 3;
            ctx.setLineDash([4, 4]);
            ctx.stroke();
            ctx.setLineDash([]);
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
        const schema = this.projectSchemas[m.schema_id] || {};
        const heading = m.heading || 0;
        const w = (schema.width || m.width || 0.8) * this.view.zoom;
        const h = (schema.height || m.height || 0.8) * this.view.zoom;

        const role = schema.machine_role || 'normal';
        let boxColor = "#1e293b";
        if (role === 'source') boxColor = "#166534";
        else if (role === 'sink') boxColor = "#7f1d1d";

        ctx.save();
        ctx.translate(center.x, center.y);
        // Rotate in screen space clockwise by heading
        ctx.rotate((heading * Math.PI) / 180);

        // 1. Machine body box (centered at 0, 0)
        ctx.fillStyle = boxColor;
        ctx.fillRect(-w / 2, -h / 2, w, h);
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(-w / 2, -h / 2, w, h);

        // 2. Heading orientation notch pointing North (local -Y in screen space)
        ctx.beginPath();
        ctx.moveTo(0, -h / 2 + 2);
        ctx.lineTo(-6, -h / 2 + 10);
        ctx.lineTo(6, -h / 2 + 10);
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();

        // 3. Labels
        let label = role.toUpperCase();
        if (label === 'NORMAL') label = m.schema_id || m.machine_type || "MACHINE";

        ctx.fillStyle = "#f8fafc";
        ctx.font = "bold 11px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, 0, -6);
        ctx.fillStyle = "#a78bfa";
        ctx.font = "10px sans-serif";
        ctx.fillText(`[0/${schema.capacity || m.capacity || 1}]`, 0, 8);

        // 4. Render visible ports directly on the machine body
        const schemaPorts = schema.ports || [];
        schemaPorts.forEach(sp => {
            // Local position: rel_x is East (+X), rel_y is North (+Y world = -Y canvas)
            const pLocalX = sp.rel_x * this.view.zoom;
            const pLocalY = -sp.rel_y * this.view.zoom;

            let portBg = "#4ade80"; // LOAD green
            if (sp.type === "UNLOAD") portBg = "#ef4444"; // red
            else if (sp.type === "BOTH") portBg = "#fbbf24"; // amber/yellow

            // Dark outer border ring
            ctx.beginPath();
            ctx.arc(pLocalX, pLocalY, 7, 0, 2 * Math.PI);
            ctx.fillStyle = "#0f172a";
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1;
            ctx.stroke();

            // Inner colored circle
            ctx.beginPath();
            ctx.arc(pLocalX, pLocalY, 5, 0, 2 * Math.PI);
            ctx.fillStyle = portBg;
            ctx.fill();

            // Port letter label (L / U / B)
            ctx.fillStyle = "#0f172a";
            ctx.font = "bold 7px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const typeLetter = sp.type === "LOAD" ? "L" : (sp.type === "UNLOAD" ? "U" : "B");
            ctx.fillText(typeLetter, pLocalX, pLocalY);
        });

        ctx.restore();

        // 5. Draw connection lines from the machine port to the connected track
        const machinePorts = m.ports || m.connected_ports;
        if (machinePorts && machinePorts.length > 0) {
            const cos = Math.cos(heading * Math.PI / 180);
            const sin = Math.sin(heading * Math.PI / 180);

            ctx.strokeStyle = "#8b5cf6";
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 4]);

            machinePorts.forEach(cp => {
                const tr = this.tracks.find(t => t.id === cp.trackId);
                if (!tr) return;

                const sp = schemaPorts.find(p => p.id === cp.schema_port_id);
                let portScreenX = center.x;
                let portScreenY = center.y;
                if (sp) {
                    const pwx = m.x + (sp.rel_x * cos + sp.rel_y * sin);
                    const pwy = m.y + (-sp.rel_x * sin + sp.rel_y * cos);
                    const pScreen = this.worldToScreen(pwx, pwy);
                    portScreenX = pScreen.x;
                    portScreenY = pScreen.y;
                }

                const d_fwd = this._dir(tr.heading);
                const tx = tr.x + cp.offset * d_fwd.x;
                const ty = tr.y + cp.offset * d_fwd.y;
                const trackScreen = this.worldToScreen(tx, ty);

                ctx.beginPath();
                ctx.moveTo(portScreenX, portScreenY);
                ctx.lineTo(trackScreen.x, trackScreen.y);
                ctx.stroke();

                // Draw connection dot on the track
                ctx.beginPath();
                ctx.arc(trackScreen.x, trackScreen.y, 4, 0, 2 * Math.PI);
                ctx.fillStyle = "#8b5cf6";
                ctx.fill();
            });
            ctx.setLineDash([]);
        }
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
            this._loading = true;
            this.clear();
            if (data.tracks) {
                this.tracks = data.tracks;
                this.machines = data.machines || [];
                this._recomputeAllNodes();
                this._notify();
            }
            this.isDirty = false;
        } catch (e) {
            alert("Error loading map: " + e.message);
        } finally {
            this._loading = false;
        }
    }
};
