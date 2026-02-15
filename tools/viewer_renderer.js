/**
 * viewer_renderer.js — WebGL Renderer for PDS Raw Models
 * =======================================================
 *
 * Handles:
 *  - MCB binary parsing (models, hierarchies, quads/vertices)
 *  - CGB texture decoding (Saturn VDP1 color modes 0, 1, 4, 5)
 *  - Runtime texture atlas building
 *  - WebGL rendering with shaded, wireframe, and bone overlay modes
 *
 * Data structures derived from yaz0r's Azel project
 * (https://github.com/yaz0r/Azel).
 */

// ── Depends on viewer_animation.js for MCB binary readers ──────────────────
// Lazy-resolve MCB to avoid load-order race conditions
let _MCB = null;
function getMCB() {
    if (!_MCB) _MCB = window.PDSAnimation.MCB;
    return _MCB;
}

// ── Texture Decoding ───────────────────────────────────────────────────────

/**
 * Decode Saturn ABGR1555 to RGBA8888.
 * Bit layout: MSB=bit15, B=bits[14:10], G=bits[9:5], R=bits[4:0]
 */
function decodeRGB555(raw) {
    const r = (raw & 0x1F) << 3;
    const g = ((raw >> 5) & 0x1F) << 3;
    const b = ((raw >> 10) & 0x1F) << 3;
    return [r, g, b, 255];
}

/**
 * Decode a single texture from CGB data.
 *
 * @param {Uint8Array} cgb - Raw CGB buffer
 * @param {number} cmdsrca - Texture source address (×8 for byte offset)
 * @param {number} cmdcolr - Color lookup table address (×8 for byte offset)
 * @param {number} cmdpmod - Pixel mode register
 * @param {number} texW - Texture width in pixels
 * @param {number} texH - Texture height in pixels
 * @param {number} spd - Transparent pixel disable flag
 * @returns {Uint8Array|null} RGBA pixel data (texW × texH × 4 bytes)
 */
function decodeTexture(cgb, cmdsrca, cmdcolr, cmdpmod, texW, texH, spd) {
    if (texW === 0 || texH === 0) return null;

    const colorMode = (cmdpmod >> 3) & 7;
    const texOffset = cmdsrca * 8;
    const pixels = new Uint8Array(texW * texH * 4);

    if (colorMode === 5) {
        // 16bpp direct RGB555
        for (let y = 0; y < texH; y++) {
            for (let x = 0; x < texW; x++) {
                const addr = texOffset + (y * texW + x) * 2;
                const pi = (y * texW + x) * 4;
                if (addr + 2 <= cgb.length) {
                    const raw = (cgb[addr] << 8) | cgb[addr + 1];
                    if (raw === 0 && !spd) {
                        // Transparent
                    } else {
                        const c = decodeRGB555(raw);
                        pixels[pi] = c[0]; pixels[pi + 1] = c[1];
                        pixels[pi + 2] = c[2]; pixels[pi + 3] = c[3];
                    }
                }
            }
        }
    } else if (colorMode === 1) {
        // 4bpp LUT mode — palette at CMDCOLR×8 in CGB
        const lutOffset = cmdcolr * 8;
        const palette = [];
        for (let i = 0; i < 16; i++) {
            const off = lutOffset + i * 2;
            if (off + 2 <= cgb.length) {
                palette.push((cgb[off] << 8) | cgb[off + 1]);
            } else {
                palette.push(0);
            }
        }

        for (let y = 0; y < texH; y++) {
            for (let x = 0; x < texW; x++) {
                const byteAddr = texOffset + ((y * texW + x) >> 1);
                const pi = (y * texW + x) * 4;
                if (byteAddr < cgb.length) {
                    const byteVal = cgb[byteAddr];
                    const nibble = ((y * texW + x) & 1) === 0
                        ? (byteVal >> 4) & 0xF
                        : byteVal & 0xF;

                    if (nibble === 0 && !spd) {
                        // Transparent
                    } else {
                        const raw = palette[nibble];
                        if (raw & 0x8000) {
                            const c = decodeRGB555(raw);
                            pixels[pi] = c[0]; pixels[pi + 1] = c[1];
                            pixels[pi + 2] = c[2]; pixels[pi + 3] = c[3];
                        }
                        // Non-MSB entries are shadow/special — leave transparent
                    }
                }
            }
        }
    } else if (colorMode === 0) {
        // 4bpp bank mode — no CRAM available, greyscale fallback
        for (let y = 0; y < texH; y++) {
            for (let x = 0; x < texW; x++) {
                const byteAddr = texOffset + ((y * texW + x) >> 1);
                const pi = (y * texW + x) * 4;
                if (byteAddr < cgb.length) {
                    const byteVal = cgb[byteAddr];
                    const nibble = ((y * texW + x) & 1) === 0
                        ? (byteVal >> 4) & 0xF
                        : byteVal & 0xF;

                    if (nibble === 0 && !spd) {
                        // Transparent
                    } else {
                        const g = nibble * 17;
                        pixels[pi] = g; pixels[pi + 1] = g;
                        pixels[pi + 2] = g; pixels[pi + 3] = 255;
                    }
                }
            }
        }
    } else if (colorMode === 4) {
        // 8bpp bank mode — greyscale fallback
        for (let y = 0; y < texH; y++) {
            for (let x = 0; x < texW; x++) {
                const addr = texOffset + y * texW + x;
                const pi = (y * texW + x) * 4;
                if (addr < cgb.length) {
                    const val = cgb[addr];
                    if (val === 0 && !spd) {
                        // Transparent
                    } else {
                        pixels[pi] = val; pixels[pi + 1] = val;
                        pixels[pi + 2] = val; pixels[pi + 3] = 255;
                    }
                }
            }
        }
    } else {
        return null;
    }

    return pixels;
}

// ── MCB Model Parsing ──────────────────────────────────────────────────────

/**
 * Parse a 3D model sub-resource from raw MCB bytes.
 *
 * @param {Uint8Array} mcb - Raw MCB buffer
 * @param {number} offset - Byte offset to model header
 * @returns {Object|null} Parsed model with vertices and quads
 */
function parseModel(mcb, offset) {
    const MCB = getMCB();
    if (offset + 12 > mcb.length) return null;

    const radius = MCB.s32(mcb, offset);
    const numVerts = MCB.u32(mcb, offset + 4);
    const vertOffset = MCB.u32(mcb, offset + 8);

    if (numVerts > 10000 || vertOffset + numVerts * 6 > mcb.length) return null;

    // Vertices: 3×s16 (12.4 fixed-point)
    const vertices = [];
    for (let i = 0; i < numVerts; i++) {
        const vo = vertOffset + i * 6;
        vertices.push([
            MCB.s16(mcb, vo),
            MCB.s16(mcb, vo + 2),
            MCB.s16(mcb, vo + 4),
        ]);
    }

    // Quads: 20 bytes + variable lighting data
    const quads = [];
    let qp = offset + 0x0C;

    while (qp + 20 <= mcb.length) {
        const i0 = MCB.u16(mcb, qp);
        const i1 = MCB.u16(mcb, qp + 2);
        const i2 = MCB.u16(mcb, qp + 4);
        const i3 = MCB.u16(mcb, qp + 6);

        if (i0 === 0 && i1 === 0 && i2 === 0 && i3 === 0) break;
        if (i0 >= numVerts || i1 >= numVerts || i2 >= numVerts || i3 >= numVerts) break;

        const lightingCtrl = MCB.u16(mcb, qp + 8);
        const cmdctrl = MCB.u16(mcb, qp + 10);
        const cmdpmod = MCB.u16(mcb, qp + 12);
        const cmdcolr = MCB.u16(mcb, qp + 14);
        const cmdsrca = MCB.u16(mcb, qp + 16);
        const cmdsize = MCB.u16(mcb, qp + 18);

        const lm = (lightingCtrl >> 8) & 3;
        const texW = (cmdsize & 0x3F00) >> 5;
        const texH = cmdsize & 0xFF;
        const colorMode = (cmdpmod >> 3) & 7;
        const flipH = (cmdctrl >> 4) & 1;
        const flipV = (cmdctrl >> 5) & 1;
        const spd = (cmdpmod >> 6) & 1;

        const extraSize = [0, 8, 48, 24][lm];
        const lighting = [];

        if (lm >= 1 && qp + 20 + extraSize <= mcb.length) {
            const ldOff = qp + 20;
            if (lm === 1) {
                lighting.push({
                    normal: [MCB.s16(mcb, ldOff), MCB.s16(mcb, ldOff + 2), MCB.s16(mcb, ldOff + 4)]
                });
            } else if (lm === 2) {
                for (let vi = 0; vi < 4; vi++) {
                    const vo = ldOff + vi * 12;
                    lighting.push({
                        normal: [MCB.s16(mcb, vo), MCB.s16(mcb, vo + 2), MCB.s16(mcb, vo + 4)],
                        color: [MCB.u16(mcb, vo + 6), MCB.u16(mcb, vo + 8), MCB.u16(mcb, vo + 10)]
                    });
                }
            } else if (lm === 3) {
                for (let vi = 0; vi < 4; vi++) {
                    const vo = ldOff + vi * 6;
                    lighting.push({
                        normal: [MCB.s16(mcb, vo), MCB.s16(mcb, vo + 2), MCB.s16(mcb, vo + 4)]
                    });
                }
            }
        }

        quads.push({
            indices: [i0, i1, i2, i3],
            lightingMode: lm,
            colorMode, texW, texH,
            cmdsrca, cmdcolr, cmdpmod,
            flipH, flipV, spd,
            lighting,
        });

        qp += 20 + extraSize;
    }

    return { radius, vertices, quads };
}

/**
 * Walk hierarchy tree and collect nodes in traversal order.
 *
 * @param {Uint8Array} mcb - Raw MCB buffer
 * @param {number} offset - Root hierarchy offset
 * @returns {Array} Nodes with modelOffset, childOffset, siblingOffset, depth
 */
function parseHierarchy(mcb, offset) {
    const MCB = getMCB();
    const nodes = [];

    function walk(off, depth) {
        if (off === 0 || off >= mcb.length || off + 12 > mcb.length) return;

        const modelOff = MCB.u32(mcb, off);
        const childOff = MCB.u32(mcb, off + 4);
        const siblingOff = MCB.u32(mcb, off + 8);

        nodes.push({
            offset: off,
            modelOffset: (modelOff !== 0 && modelOff < mcb.length) ? modelOff : 0,
            childOffset: (childOff !== 0 && childOff < mcb.length) ? childOff : 0,
            siblingOffset: (siblingOff !== 0 && siblingOff < mcb.length) ? siblingOff : 0,
            depth,
        });

        if (childOff !== 0 && childOff < mcb.length) walk(childOff, depth + 1);
        if (siblingOff !== 0 && siblingOff < mcb.length) walk(siblingOff, depth);
    }

    walk(offset, 0);
    return nodes;
}


// ── Texture Atlas Builder ──────────────────────────────────────────────────

/**
 * Build a WebGL texture atlas from all unique textures in the model set.
 *
 * @param {Uint8Array} cgb - Raw CGB buffer
 * @param {Array} allModels - Array of parsed models
 * @returns {Object} { canvas, textureMap: Map<string, {x,y,w,h}> }
 */
function buildTextureAtlas(cgb, allModels) {
    const unique = new Map(); // key → {w, h, pixels}

    for (const model of allModels) {
        if (!model) continue;
        for (const quad of model.quads) {
            if (quad.texW === 0 || quad.texH === 0) continue;
            const key = `${quad.cmdsrca}_${quad.cmdcolr}_${quad.cmdpmod}_${quad.texW}_${quad.texH}`;
            if (unique.has(key)) continue;

            const pixels = decodeTexture(cgb, quad.cmdsrca, quad.cmdcolr,
                quad.cmdpmod, quad.texW, quad.texH, quad.spd);
            if (pixels) {
                unique.set(key, { w: quad.texW, h: quad.texH, pixels });
            }
        }
    }

    if (unique.size === 0) {
        // Create 1×1 white texture
        const canvas = document.createElement('canvas');
        canvas.width = 1; canvas.height = 1;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, 1, 1);
        return { canvas, textureMap: new Map() };
    }

    // Layout: stack vertically
    let atlasW = 0, atlasH = 0;
    for (const { w, h } of unique.values()) {
        atlasW = Math.max(atlasW, w);
        atlasH += h;
    }

    const canvas = document.createElement('canvas');
    canvas.width = atlasW;
    canvas.height = atlasH;
    const ctx = canvas.getContext('2d');

    const textureMap = new Map();
    let yCursor = 0;

    for (const [key, { w, h, pixels }] of unique) {
        const imgData = ctx.createImageData(w, h);
        imgData.data.set(pixels);
        ctx.putImageData(imgData, 0, yCursor);
        textureMap.set(key, { x: 0, y: yCursor, w, h });
        yCursor += h;
    }

    return { canvas, textureMap, atlasW, atlasH };
}


// ── WebGL Renderer ─────────────────────────────────────────────────────────

const VERT_SHADER = `
    attribute vec3 aPosition;
    attribute vec2 aTexCoord;
    attribute vec3 aNormal;
    attribute vec4 aColor;

    uniform mat4 uProjection;
    uniform mat4 uView;
    uniform mat4 uModel;
    uniform vec3 uLightDir;

    varying vec2 vTexCoord;
    varying vec4 vColor;
    varying float vLighting;

    void main() {
        gl_Position = uProjection * uView * uModel * vec4(aPosition, 1.0);
        vTexCoord = aTexCoord;
        vColor = aColor;

        // Simple directional lighting
        vec3 worldNormal = normalize(mat3(uModel) * aNormal);
        vLighting = max(dot(worldNormal, normalize(uLightDir)), 0.0) * 0.6 + 0.4;
    }
`;

const FRAG_SHADER = `
    precision mediump float;

    varying vec2 vTexCoord;
    varying vec4 vColor;
    varying float vLighting;

    uniform sampler2D uTexture;
    uniform bool uUseTexture;
    uniform float uAlpha;

    void main() {
        vec4 color;
        if (uUseTexture) {
            color = texture2D(uTexture, vTexCoord);
            if (color.a < 0.01) discard;
        } else {
            color = vColor;
        }
        color.rgb *= vLighting;
        color.a *= uAlpha;
        gl_FragColor = color;
    }
`;

const WIRE_VERT = `
    attribute vec3 aPosition;
    uniform mat4 uProjection;
    uniform mat4 uView;
    uniform mat4 uModel;
    void main() {
        gl_Position = uProjection * uView * uModel * vec4(aPosition, 1.0);
    }
`;

const WIRE_FRAG = `
    precision mediump float;
    uniform vec4 uColor;
    void main() {
        gl_FragColor = uColor;
    }
`;

/**
 * Main WebGL renderer for PDS models.
 */
class PDSRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.gl = canvas.getContext('webgl', { antialias: true, alpha: false });
        if (!this.gl) throw new Error('WebGL not supported');

        this.gl.enable(this.gl.DEPTH_TEST);
        this.gl.enable(this.gl.BLEND);
        this.gl.blendFunc(this.gl.SRC_ALPHA, this.gl.ONE_MINUS_SRC_ALPHA);

        this._initShaders();

        // Camera
        this.cameraDistance = 200;
        this.cameraRotX = 0.3;
        this.cameraRotY = 0;
        this.cameraPanX = 0;
        this.cameraPanY = 0;

        // Render state
        this.showWireframe = false;
        this.showBones = false;
        this.showTexture = true;

        // Model data
        this.meshBuffers = null;
        this.wireBuffers = null;
        this.boneBuffers = null;
        this.atlasTexture = null;
        this.atlasData = null;

        // Current loaded model info
        this.currentModels = null;
        this.currentHierarchy = null;
    }

    _initShaders() {
        const gl = this.gl;

        // Main shader
        this.mainProgram = this._createProgram(VERT_SHADER, FRAG_SHADER);
        this.mainLocs = {
            aPosition: gl.getAttribLocation(this.mainProgram, 'aPosition'),
            aTexCoord: gl.getAttribLocation(this.mainProgram, 'aTexCoord'),
            aNormal: gl.getAttribLocation(this.mainProgram, 'aNormal'),
            aColor: gl.getAttribLocation(this.mainProgram, 'aColor'),
            uProjection: gl.getUniformLocation(this.mainProgram, 'uProjection'),
            uView: gl.getUniformLocation(this.mainProgram, 'uView'),
            uModel: gl.getUniformLocation(this.mainProgram, 'uModel'),
            uLightDir: gl.getUniformLocation(this.mainProgram, 'uLightDir'),
            uTexture: gl.getUniformLocation(this.mainProgram, 'uTexture'),
            uUseTexture: gl.getUniformLocation(this.mainProgram, 'uUseTexture'),
            uAlpha: gl.getUniformLocation(this.mainProgram, 'uAlpha'),
        };

        // Wireframe shader
        this.wireProgram = this._createProgram(WIRE_VERT, WIRE_FRAG);
        this.wireLocs = {
            aPosition: gl.getAttribLocation(this.wireProgram, 'aPosition'),
            uProjection: gl.getUniformLocation(this.wireProgram, 'uProjection'),
            uView: gl.getUniformLocation(this.wireProgram, 'uView'),
            uModel: gl.getUniformLocation(this.wireProgram, 'uModel'),
            uColor: gl.getUniformLocation(this.wireProgram, 'uColor'),
        };
    }

    _createProgram(vsSource, fsSource) {
        const gl = this.gl;
        const vs = gl.createShader(gl.VERTEX_SHADER);
        gl.shaderSource(vs, vsSource);
        gl.compileShader(vs);
        if (!gl.getShaderParameter(vs, gl.COMPILE_STATUS)) {
            console.error('VS:', gl.getShaderInfoLog(vs));
        }

        const fs = gl.createShader(gl.FRAGMENT_SHADER);
        gl.shaderSource(fs, fsSource);
        gl.compileShader(fs);
        if (!gl.getShaderParameter(fs, gl.COMPILE_STATUS)) {
            console.error('FS:', gl.getShaderInfoLog(fs));
        }

        const prog = gl.createProgram();
        gl.attachShader(prog, vs);
        gl.attachShader(prog, fs);
        gl.linkProgram(prog);
        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
            console.error('Link:', gl.getProgramInfoLog(prog));
        }
        return prog;
    }

    /**
     * Load a model from raw MCB/CGB buffers + structure JSON.
     *
     * @param {Uint8Array} mcb - Raw MCB bytes
     * @param {Uint8Array} cgb - Raw CGB bytes
     * @param {Object} structure - Parsed structure JSON
     */
    loadModel(mcb, cgb, structure) {
        // Parse all models referenced by hierarchies
        const allModels = [];
        const modelCache = {};

        for (const entry of structure.pointerTable) {
            if (entry.type === 'model') {
                const model = parseModel(mcb, entry.offset);
                if (model) {
                    modelCache[entry.offset] = model;
                    allModels.push(model);
                }
            }
        }

        // Parse hierarchies
        const hierarchies = [];
        for (const hierData of structure.hierarchies) {
            const nodes = parseHierarchy(mcb, hierData.offset);
            hierarchies.push({ ...hierData, parsedNodes: nodes });
        }

        // Build texture atlas
        this.atlasData = buildTextureAtlas(cgb, allModels);
        this._uploadTexture(this.atlasData.canvas);

        this.currentModels = modelCache;
        this.currentHierarchy = hierarchies.length > 0 ? hierarchies[0] : null;
        this.structure = structure;
        this.mcb = mcb;

        // Auto-fit camera
        this._autoFitCamera(allModels);

        // Build mesh buffers
        this._buildMeshBuffers(allModels);
    }

    _uploadTexture(canvas) {
        const gl = this.gl;
        if (this.atlasTexture) gl.deleteTexture(this.atlasTexture);

        this.atlasTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, this.atlasTexture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvas);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }

    _autoFitCamera(allModels) {
        let maxR = 10;
        for (const model of allModels) {
            if (!model) continue;
            for (const v of model.vertices) {
                const r = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) / 16;
                maxR = Math.max(maxR, r);
            }
        }
        this.cameraDistance = maxR * 3;
    }

    /**
     * Build triangle mesh buffers for all models in the current hierarchy.
     * Called with current pose data for animated rendering.
     *
     * @param {Array} poseForRendering - Per-bone float pose from AnimationController
     */
    buildAnimatedMeshBuffers(poseForRendering) {
        if (!this.currentHierarchy || !this.currentModels) return;

        const positions = [];
        const texCoords = [];
        const normals = [];
        const colors = [];
        const wirePositions = [];
        const bonePositions = [];

        const FP_VERT = 1.0 / 16.0; // 12.4 → float
        const hierNodes = this.currentHierarchy.parsedNodes;
        const atlasW = this.atlasData?.atlasW || 1;
        const atlasH = this.atlasData?.atlasH || 1;
        const texMap = this.atlasData?.textureMap;

        // Walk hierarchy, applying transforms
        const matrixStack = [mat4_identity()];

        for (let ni = 0; ni < hierNodes.length; ni++) {
            const node = hierNodes[ni];
            const pose = poseForRendering && poseForRendering[ni]
                ? poseForRendering[ni]
                : { translation: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };

            // Manage matrix stack based on depth
            while (matrixStack.length > node.depth + 1) {
                matrixStack.pop();
            }
            const parentMatrix = matrixStack[matrixStack.length - 1];

            // Build bone transform
            let boneMatrix = mat4_identity();
            boneMatrix = mat4_translate(boneMatrix, pose.translation[0], pose.translation[1], pose.translation[2]);
            boneMatrix = mat4_rotateZYX(boneMatrix, pose.rotation[0], pose.rotation[1], pose.rotation[2]);
            boneMatrix = mat4_scale(boneMatrix, pose.scale[0], pose.scale[1], pose.scale[2]);

            const worldMatrix = mat4_multiply(parentMatrix, boneMatrix);
            matrixStack.push(worldMatrix);

            // Draw bone connector
            const boneOrigin = mat4_transformPoint(worldMatrix, [0, 0, 0]);
            bonePositions.push(...boneOrigin);

            // Render model at this node
            if (node.modelOffset !== 0) {
                const model = this.currentModels[node.modelOffset];
                if (!model) continue;

                for (const quad of model.quads) {
                    const idx = quad.indices;
                    // Compute face normal from first triangle
                    const v0 = mat4_transformPoint(worldMatrix, [
                        model.vertices[idx[0]][0] * FP_VERT,
                        model.vertices[idx[0]][1] * FP_VERT,
                        model.vertices[idx[0]][2] * FP_VERT]);
                    const v1 = mat4_transformPoint(worldMatrix, [
                        model.vertices[idx[1]][0] * FP_VERT,
                        model.vertices[idx[1]][1] * FP_VERT,
                        model.vertices[idx[1]][2] * FP_VERT]);
                    const v2 = mat4_transformPoint(worldMatrix, [
                        model.vertices[idx[2]][0] * FP_VERT,
                        model.vertices[idx[2]][1] * FP_VERT,
                        model.vertices[idx[2]][2] * FP_VERT]);
                    const v3 = mat4_transformPoint(worldMatrix, [
                        model.vertices[idx[3]][0] * FP_VERT,
                        model.vertices[idx[3]][1] * FP_VERT,
                        model.vertices[idx[3]][2] * FP_VERT]);

                    const e1 = [v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]];
                    const e2 = [v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]];
                    const fn = vec3_normalize(vec3_cross(e1, e2));

                    // Texture coordinates
                    const texKey = `${quad.cmdsrca}_${quad.cmdcolr}_${quad.cmdpmod}_${quad.texW}_${quad.texH}`;
                    const texEntry = texMap?.get(texKey);
                    let uvs;
                    if (texEntry && quad.texW > 0 && quad.texH > 0) {
                        const u0 = texEntry.x / atlasW;
                        const v0t = texEntry.y / atlasH;
                        const u1 = (texEntry.x + texEntry.w) / atlasW;
                        const v1t = (texEntry.y + texEntry.h) / atlasH;

                        let ul = u0, ur = u1, vt = v0t, vb = v1t;
                        if (quad.flipH) { const t = ul; ul = ur; ur = t; }
                        if (quad.flipV) { const t = vt; vt = vb; vb = t; }

                        uvs = [[ul, vt], [ur, vt], [ur, vb], [ul, vb]];
                    } else {
                        uvs = [[0, 0], [0, 0], [0, 0], [0, 0]];
                    }

                    // Vertex color (fallback for untextured quads)
                    const hasTexture = texEntry && quad.texW > 0 && quad.texH > 0;
                    const col = hasTexture ? [1, 1, 1, 1] : [0.7, 0.7, 0.8, 1.0];

                    // Triangle 1: 0-1-2
                    positions.push(...v0, ...v1, ...v2);
                    texCoords.push(...uvs[0], ...uvs[1], ...uvs[2]);
                    normals.push(...fn, ...fn, ...fn);
                    colors.push(...col, ...col, ...col);

                    // Triangle 2: 0-2-3
                    positions.push(...v0, ...v2, ...v3);
                    texCoords.push(...uvs[0], ...uvs[2], ...uvs[3]);
                    normals.push(...fn, ...fn, ...fn);
                    colors.push(...col, ...col, ...col);

                    // Wireframe edges: 0-1, 1-2, 2-3, 3-0
                    wirePositions.push(...v0, ...v1, ...v1, ...v2,
                        ...v2, ...v3, ...v3, ...v0);
                }
            }
        }

        this._uploadBuffers(positions, texCoords, normals, colors, wirePositions, bonePositions);
    }

    /**
     * Build static mesh buffers (no animation).
     */
    _buildMeshBuffers(allModels) {
        const positions = [];
        const texCoords = [];
        const normals = [];
        const colors = [];
        const wirePositions = [];

        const FP_VERT = 1.0 / 16.0;
        const atlasW = this.atlasData?.atlasW || 1;
        const atlasH = this.atlasData?.atlasH || 1;
        const texMap = this.atlasData?.textureMap;

        for (const model of allModels) {
            if (!model) continue;
            for (const quad of model.quads) {
                const idx = quad.indices;
                const v0 = model.vertices[idx[0]].map(v => v * FP_VERT);
                const v1 = model.vertices[idx[1]].map(v => v * FP_VERT);
                const v2 = model.vertices[idx[2]].map(v => v * FP_VERT);
                const v3 = model.vertices[idx[3]].map(v => v * FP_VERT);

                const e1 = [v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]];
                const e2 = [v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]];
                const fn = vec3_normalize(vec3_cross(e1, e2));

                const texKey = `${quad.cmdsrca}_${quad.cmdcolr}_${quad.cmdpmod}_${quad.texW}_${quad.texH}`;
                const texEntry = texMap?.get(texKey);
                let uvs;
                if (texEntry && quad.texW > 0 && quad.texH > 0) {
                    const u0 = texEntry.x / atlasW;
                    const v0t = texEntry.y / atlasH;
                    const u1 = (texEntry.x + texEntry.w) / atlasW;
                    const v1t = (texEntry.y + texEntry.h) / atlasH;
                    let ul = u0, ur = u1, vt = v0t, vb = v1t;
                    if (quad.flipH) { const t = ul; ul = ur; ur = t; }
                    if (quad.flipV) { const t = vt; vt = vb; vb = t; }
                    uvs = [[ul, vt], [ur, vt], [ur, vb], [ul, vb]];
                } else {
                    uvs = [[0, 0], [0, 0], [0, 0], [0, 0]];
                }

                const hasTexture = texEntry && quad.texW > 0 && quad.texH > 0;
                const col = hasTexture ? [1, 1, 1, 1] : [0.7, 0.7, 0.8, 1.0];

                positions.push(...v0, ...v1, ...v2, ...v0, ...v2, ...v3);
                texCoords.push(...uvs[0], ...uvs[1], ...uvs[2], ...uvs[0], ...uvs[2], ...uvs[3]);
                normals.push(...fn, ...fn, ...fn, ...fn, ...fn, ...fn);
                colors.push(...col, ...col, ...col, ...col, ...col, ...col);
                wirePositions.push(...v0, ...v1, ...v1, ...v2, ...v2, ...v3, ...v3, ...v0);
            }
        }

        this._uploadBuffers(positions, texCoords, normals, colors, wirePositions, []);
    }

    _uploadBuffers(positions, texCoords, normals, colors, wirePositions, bonePositions) {
        const gl = this.gl;

        this.meshBuffers = {
            position: this._createBuffer(new Float32Array(positions)),
            texCoord: this._createBuffer(new Float32Array(texCoords)),
            normal: this._createBuffer(new Float32Array(normals)),
            color: this._createBuffer(new Float32Array(colors)),
            triCount: positions.length / 3,
        };

        this.wireBuffers = {
            position: this._createBuffer(new Float32Array(wirePositions)),
            lineCount: wirePositions.length / 3,
        };

        if (bonePositions.length > 0) {
            this.boneBuffers = {
                position: this._createBuffer(new Float32Array(bonePositions)),
                pointCount: bonePositions.length / 3,
            };
        }
    }

    _createBuffer(data) {
        const gl = this.gl;
        const buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
        return buf;
    }

    /**
     * Render a frame.
     */
    render() {
        const gl = this.gl;
        const w = this.canvas.width;
        const h = this.canvas.height;

        gl.viewport(0, 0, w, h);
        gl.clearColor(0.09, 0.09, 0.12, 1.0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        if (!this.meshBuffers) return;

        const proj = mat4_perspective(45 * Math.PI / 180, w / h, 0.1, this.cameraDistance * 10);
        const view = mat4_lookAt(this.cameraDistance, this.cameraRotX, this.cameraRotY,
            this.cameraPanX, this.cameraPanY);
        const model = mat4_identity();

        // Shaded pass
        if (this.showTexture || !this.showWireframe) {
            gl.useProgram(this.mainProgram);
            gl.uniformMatrix4fv(this.mainLocs.uProjection, false, proj);
            gl.uniformMatrix4fv(this.mainLocs.uView, false, view);
            gl.uniformMatrix4fv(this.mainLocs.uModel, false, model);
            gl.uniform3f(this.mainLocs.uLightDir, 0.3, 0.8, 0.5);
            gl.uniform1f(this.mainLocs.uAlpha, 1.0);

            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, this.atlasTexture);
            gl.uniform1i(this.mainLocs.uTexture, 0);
            gl.uniform1i(this.mainLocs.uUseTexture, this.showTexture ? 1 : 0);

            this._bindAttrib(this.mainLocs.aPosition, this.meshBuffers.position, 3);
            this._bindAttrib(this.mainLocs.aTexCoord, this.meshBuffers.texCoord, 2);
            this._bindAttrib(this.mainLocs.aNormal, this.meshBuffers.normal, 3);
            this._bindAttrib(this.mainLocs.aColor, this.meshBuffers.color, 4);

            gl.drawArrays(gl.TRIANGLES, 0, this.meshBuffers.triCount);
        }

        // Wireframe pass
        if (this.showWireframe && this.wireBuffers) {
            gl.useProgram(this.wireProgram);
            gl.uniformMatrix4fv(this.wireLocs.uProjection, false, proj);
            gl.uniformMatrix4fv(this.wireLocs.uView, false, view);
            gl.uniformMatrix4fv(this.wireLocs.uModel, false, model);
            gl.uniform4f(this.wireLocs.uColor, 0.0, 1.0, 0.6, 0.8);

            this._bindAttrib(this.wireLocs.aPosition, this.wireBuffers.position, 3);
            gl.drawArrays(gl.LINES, 0, this.wireBuffers.lineCount);
        }

        // Bone overlay
        if (this.showBones && this.boneBuffers) {
            gl.useProgram(this.wireProgram);
            gl.uniformMatrix4fv(this.wireLocs.uProjection, false, proj);
            gl.uniformMatrix4fv(this.wireLocs.uView, false, view);
            gl.uniformMatrix4fv(this.wireLocs.uModel, false, model);
            gl.uniform4f(this.wireLocs.uColor, 1.0, 0.3, 0.2, 1.0);

            this._bindAttrib(this.wireLocs.aPosition, this.boneBuffers.position, 3);
            gl.drawArrays(gl.POINTS, 0, this.boneBuffers.pointCount);

            // Draw bone connectors
            if (this.boneBuffers.pointCount > 1) {
                gl.uniform4f(this.wireLocs.uColor, 1.0, 0.6, 0.1, 0.6);
                gl.drawArrays(gl.LINE_STRIP, 0, this.boneBuffers.pointCount);
            }
        }
    }

    _bindAttrib(loc, buffer, size) {
        if (loc < 0) return;
        const gl = this.gl;
        gl.enableVertexAttribArray(loc);
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
    }

    resize(w, h) {
        this.canvas.width = w;
        this.canvas.height = h;
    }
}


// ── Matrix Math Utilities ──────────────────────────────────────────────────

function mat4_identity() {
    return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
}

function mat4_multiply(a, b) {
    const r = new Float32Array(16);
    for (let i = 0; i < 4; i++) {
        for (let j = 0; j < 4; j++) {
            r[j * 4 + i] = a[i] * b[j * 4] + a[4 + i] * b[j * 4 + 1] + a[8 + i] * b[j * 4 + 2] + a[12 + i] * b[j * 4 + 3];
        }
    }
    return r;
}

function mat4_translate(m, x, y, z) {
    const t = mat4_identity();
    t[12] = x; t[13] = y; t[14] = z;
    return mat4_multiply(m, t);
}

function mat4_scale(m, x, y, z) {
    const s = mat4_identity();
    s[0] = x; s[5] = y; s[10] = z;
    return mat4_multiply(m, s);
}

function mat4_rotateX(m, a) {
    const c = Math.cos(a), s = Math.sin(a);
    const r = mat4_identity();
    r[5] = c; r[6] = s; r[9] = -s; r[10] = c;
    return mat4_multiply(m, r);
}

function mat4_rotateY(m, a) {
    const c = Math.cos(a), s = Math.sin(a);
    const r = mat4_identity();
    r[0] = c; r[2] = -s; r[8] = s; r[10] = c;
    return mat4_multiply(m, r);
}

function mat4_rotateZ(m, a) {
    const c = Math.cos(a), s = Math.sin(a);
    const r = mat4_identity();
    r[0] = c; r[1] = s; r[4] = -s; r[5] = c;
    return mat4_multiply(m, r);
}

/** Rotate Z-Y-X (Saturn order). */
function mat4_rotateZYX(m, rx, ry, rz) {
    m = mat4_rotateZ(m, rz);
    m = mat4_rotateY(m, ry);
    m = mat4_rotateX(m, rx);
    return m;
}

function mat4_transformPoint(m, p) {
    return [
        m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
        m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
        m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14],
    ];
}

function mat4_perspective(fov, aspect, near, far) {
    const f = 1.0 / Math.tan(fov / 2);
    const nf = 1 / (near - far);
    return new Float32Array([
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (far + near) * nf, -1,
        0, 0, 2 * far * near * nf, 0,
    ]);
}

function mat4_lookAt(dist, rotX, rotY, panX, panY) {
    let m = mat4_identity();
    m = mat4_translate(m, panX, panY, -dist);
    m = mat4_rotateX(m, rotX);
    m = mat4_rotateY(m, rotY);
    return m;
}

function vec3_cross(a, b) {
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ];
}

function vec3_normalize(v) {
    const len = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    if (len < 0.0001) return [0, 1, 0];
    return [v[0] / len, v[1] / len, v[2] / len];
}


// ── Exports ────────────────────────────────────────────────────────────────

if (typeof window !== 'undefined') {
    window.PDSRenderer = {
        decodeTexture,
        buildTextureAtlas,
        parseModel,
        parseHierarchy,
        PDSRenderer,
        // Matrix utils
        mat4_identity, mat4_multiply, mat4_translate, mat4_scale,
        mat4_rotateX, mat4_rotateY, mat4_rotateZ, mat4_rotateZYX,
        mat4_transformPoint, mat4_perspective, mat4_lookAt,
        vec3_cross, vec3_normalize,
    };
}
