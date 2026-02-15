/**
 * viewer_animation.js — Saturn-Accurate Animation System for PDS Models
 * ======================================================================
 *
 * Implements the animation stepping and interpolation logic matching the
 * original Sega Saturn code. Derived from analysis of yaz0r's Azel project
 * (https://github.com/yaz0r/Azel), specifically kernel/animation.cpp.
 *
 * Animation Modes (flags & 7):
 *   Mode 0: Full-frame quantized — 1 value per bone per frame, direct lookup
 *   Mode 1: Delta-compressed — cumulative deltas with delay encoding
 *   Mode 4: Half-rate (every 2 frames) — interpolated between keyframes
 *   Mode 5: Quarter-rate (every 4 frames) — interpolated between keyframes
 *
 * Track Data Format (per value):
 *   First entry:  raw s16 value (multiplied by 16 for initial)
 *   Subsequent:   bits [15:4] = delta value (s12), bits [3:0] = delay (hold frames)
 */

// ── MCB Binary Readers ─────────────────────────────────────────────────────

const MCB = {
    u32(buf, off) {
        return ((buf[off] << 24) | (buf[off + 1] << 16) | (buf[off + 2] << 8) | buf[off + 3]) >>> 0;
    },
    s32(buf, off) {
        return (buf[off] << 24) | (buf[off + 1] << 16) | (buf[off + 2] << 8) | buf[off + 3];
    },
    u16(buf, off) {
        return (buf[off] << 8) | buf[off + 1];
    },
    s16(buf, off) {
        const v = (buf[off] << 8) | buf[off + 1];
        return v >= 0x8000 ? v - 0x10000 : v;
    }
};

// ── Animation Data Parser ──────────────────────────────────────────────────

/**
 * Parse animation data from raw MCB bytes at a given offset.
 * Matches sAnimationData constructor from Azel source.
 *
 * @param {Uint8Array} mcb - Raw MCB buffer
 * @param {number} offset - Byte offset to animation header
 * @returns {Object|null} Parsed animation data
 */
function parseAnimationData(mcb, offset) {
    if (offset + 12 > mcb.length) return null;

    const flags = MCB.u16(mcb, offset);
    if (flags === 0) return null;

    const mode = flags & 7;
    const numBones = MCB.u16(mcb, offset + 2);
    const numFrames = MCB.u16(mcb, offset + 4);
    // offset + 6: padding
    const trackHeaderOffset = MCB.u32(mcb, offset + 8);

    const trackHeaders = [];

    for (let boneId = 0; boneId < numBones; boneId++) {
        const thOff = offset + trackHeaderOffset + 0x38 * boneId;

        // Read 9 track lengths (s16)
        const tracksLength = [];
        for (let i = 0; i < 9; i++) {
            tracksLength.push(MCB.s16(mcb, thOff + i * 2));
        }

        // Skip 2 bytes padding, read 9 track data offsets (u32)
        const trackDataOffsets = [];
        for (let i = 0; i < 9; i++) {
            trackDataOffsets.push(MCB.u32(mcb, thOff + 20 + i * 4));
        }

        // Read actual track data
        const trackData = [];
        for (let i = 0; i < 9; i++) {
            const vals = [];
            if (tracksLength[i] > 0 && trackDataOffsets[i] > 0) {
                const absOff = offset + trackDataOffsets[i];
                for (let j = 0; j < tracksLength[i]; j++) {
                    if (absOff + j * 2 + 2 <= mcb.length) {
                        vals.push(MCB.s16(mcb, absOff + j * 2));
                    } else {
                        vals.push(0);
                    }
                }
            }
            trackData.push(vals);
        }

        trackHeaders.push({ tracksLength, trackData });
    }

    return {
        flags,
        mode,
        numBones,
        numFrames,
        hasPosition: !!(flags & 8),
        hasRotation: !!(flags & 0x10),
        hasScale: !!(flags & 0x20),
        trackHeaders,
    };
}

// ── Static Pose Parser ─────────────────────────────────────────────────────

/**
 * Parse static pose data from raw MCB bytes.
 * Each bone: 3×s32 translation, 3×s32 rotation, 3×s32 scale = 36 bytes.
 *
 * @param {Uint8Array} mcb - Raw MCB buffer
 * @param {number} offset - Byte offset to pose data
 * @param {number} numBones - Number of bones
 * @returns {Array} Array of bone pose objects
 */
function parseStaticPose(mcb, offset, numBones) {
    const bones = [];
    for (let i = 0; i < numBones; i++) {
        const boff = offset + i * 36;
        bones.push({
            translation: [MCB.s32(mcb, boff), MCB.s32(mcb, boff + 4), MCB.s32(mcb, boff + 8)],
            rotation: [MCB.s32(mcb, boff + 12), MCB.s32(mcb, boff + 16), MCB.s32(mcb, boff + 20)],
            scale: [MCB.s32(mcb, boff + 24), MCB.s32(mcb, boff + 28), MCB.s32(mcb, boff + 32)],
        });
    }
    return bones;
}

// ── Track Stepping (Core Animation Engine) ─────────────────────────────────

/**
 * Step a single animation track forward by one step.
 * This is the core decompression function matching Azel's stepAnimationTrack().
 *
 * Track encoding:
 *   First entry (currentStep == 0): raw value, multiplied by 16
 *   Subsequent entries: bits[15:4] = value (s12, sign-extended), bits[3:0] = delay
 *
 * @param {Object} trackState - Mutable track state {currentStep, delay, value}
 * @param {Int16Array|Array} trackData - Track data values
 * @param {number} maxStep - Track length
 * @returns {number} Current track value (s32)
 */
function stepAnimationTrack(trackState, trackData, maxStep) {
    if (maxStep <= 0 || trackData.length === 0) return trackState.value;

    if (trackState.delay > 0) {
        trackState.delay--;
        return trackState.value;
    }

    if (trackState.currentStep > 0) {
        const raw = trackData[trackState.currentStep] & 0xFFFF;
        trackState.delay = (raw & 0xF) - 1;
        // Sign-extend the upper 12 bits: value is (raw & 0xFFF0) treated as s16
        const val16 = raw & 0xFFF0;
        trackState.value = val16 >= 0x8000 ? val16 - 0x10000 : val16;
    } else {
        trackState.delay = 0;
        trackState.value = trackData[0] * 16;
    }

    trackState.currentStep++;
    if (trackState.currentStep >= maxStep) {
        trackState.currentStep = 0;
    }

    return trackState.value;
}

// ── Animation State Machine ────────────────────────────────────────────────

/**
 * Complete animation controller for a hierarchical model.
 * Manages playback state, pose computation, and animation switching.
 */
class AnimationController {
    /**
     * @param {number} numBones - Bone count from hierarchy
     * @param {Array} defaultPose - Static pose data (from parseStaticPose)
     */
    constructor(numBones, defaultPose) {
        this.numBones = numBones;
        this.defaultPose = defaultPose;
        this.currentAnimation = null;
        this.currentFrame = 0;
        this.playing = false;
        this.loop = true;
        this.speed = 1;

        // Per-bone working pose (translation, rotation, scale as s32 16.16 FP)
        this.poseData = [];
        for (let i = 0; i < numBones; i++) {
            this.poseData.push({
                translation: [...(defaultPose[i]?.translation || [0, 0, 0])],
                rotation: [...(defaultPose[i]?.rotation || [0, 0, 0])],
                scale: [...(defaultPose[i]?.scale || [0x10000, 0x10000, 0x10000])],
                // Half-step interpolation values (for modes 4 and 5)
                halfTranslation: [0, 0, 0],
                halfRotation: [0, 0, 0],
                halfScale: [0, 0, 0],
                // Track decompression state: 9 channels
                trackState: Array.from({ length: 9 }, () => ({
                    currentStep: 0,
                    delay: 0,
                    value: 0,
                })),
            });
        }
    }

    /**
     * Set a new animation to play.
     * Matches setupModelAnimation() from Azel source.
     *
     * @param {Object} animation - Parsed animation data from parseAnimationData
     */
    setAnimation(animation) {
        if (!animation) {
            this.currentAnimation = null;
            this.playing = false;
            return;
        }

        this.currentAnimation = animation;
        this.currentFrame = 0;

        // Copy default pose based on flags
        if (animation.hasPosition) {
            this._copyPosePositions();
        }
        if (animation.hasRotation) {
            this._copyPoseRotations();
        }
        if (animation.hasScale) {
            this._resetPoseScale();
        }

        // Reset track states
        for (let i = 0; i < this.numBones; i++) {
            const mode = animation.mode;
            if (mode === 1 || mode === 4 || mode === 5) {
                for (let j = 0; j < 9; j++) {
                    this.poseData[i].trackState[j].currentStep = 0;
                    this.poseData[i].trackState[j].delay = 0;
                    this.poseData[i].trackState[j].value = 0;
                }
            }
        }

        this.playing = true;

        // Step animation to frame 0 to avoid T-pose
        this.stepAnimation();
    }

    /**
     * Advance animation by one frame.
     * Routes to mode-specific handlers matching Azel's step functions.
     *
     * @returns {boolean} true if animation is still playing
     */
    stepAnimation() {
        const anim = this.currentAnimation;
        if (!anim) return false;

        const mode = anim.mode;

        switch (mode) {
            case 0: this._stepMode0(); break;
            case 1: this._stepMode1(); break;
            case 4: this._stepMode4(); break;
            case 5: this._stepMode5(); break;
        }

        this.currentFrame++;
        if (this.currentFrame >= anim.numFrames) {
            if (this.loop) {
                this.currentFrame = 0;
                // Reset track states for looping
                for (let i = 0; i < this.numBones; i++) {
                    for (let j = 0; j < 9; j++) {
                        this.poseData[i].trackState[j].currentStep = 0;
                        this.poseData[i].trackState[j].delay = 0;
                        this.poseData[i].trackState[j].value = 0;
                    }
                }
                // Re-copy default pose for flag-based channels
                if (anim.hasPosition) this._copyPosePositions();
                if (anim.hasRotation) this._copyPoseRotations();
                if (anim.hasScale) this._resetPoseScale();
                // Step to frame 0
                this.stepAnimation();
                this.currentFrame = 0; // avoid double increment
                return true;
            } else {
                this.playing = false;
                return false;
            }
        }
        return true;
    }

    /**
     * Update method called per display frame. Handles speed control.
     *
     * @returns {boolean} true if animation state changed
     */
    update() {
        if (!this.playing || !this.currentAnimation) return false;
        // Speed control: at speed 1, step every call
        // At speed 0.5, step every other call, etc.
        return this.stepAnimation();
    }

    // ── Mode-Specific Stepping ─────────────────────────────────────────────

    /**
     * Mode 0: Full-frame quantized.
     * Direct lookup: track[frame] for each channel.
     * Translation *= 0x10, Rotation *= 0x10000
     */
    _stepMode0() {
        const anim = this.currentAnimation;
        const frame = this.currentFrame;

        for (let i = 0; i < this.numBones; i++) {
            const th = anim.trackHeaders[i];
            const pose = this.poseData[i];

            // Position: tracks 0,1,2
            if (anim.hasPosition && th.trackData[0].length > frame) {
                pose.translation[0] = th.trackData[0][frame] * 0x10;
                pose.translation[1] = th.trackData[1][frame] * 0x10;
                pose.translation[2] = th.trackData[2][frame] * 0x10;
            }

            // Rotation: tracks 3,4,5
            if (anim.hasRotation && th.trackData[3].length > frame) {
                pose.rotation[0] = th.trackData[3][frame] * 0x10000;
                pose.rotation[1] = th.trackData[4][frame] * 0x10000;
                pose.rotation[2] = th.trackData[5][frame] * 0x10000;
            }

            // Scale: tracks 6,7,8 (rarely used)
            if (anim.hasScale && th.trackData[6].length > frame) {
                pose.scale[0] = th.trackData[6][frame] * 0x10000;
                pose.scale[1] = th.trackData[7][frame] * 0x10000;
                pose.scale[2] = th.trackData[8][frame] * 0x10000;
            }
        }
    }

    /**
     * Mode 1: Delta-compressed animation.
     * Frame 0: set from track. Subsequent: accumulate deltas.
     * Rotation deltas are multiplied by 0x1000.
     */
    _stepMode1() {
        const anim = this.currentAnimation;
        const frame = this.currentFrame;

        // Position — bone 0 only uses special root handling
        if (anim.hasPosition) {
            const th0 = anim.trackHeaders[0];
            const pose0 = this.poseData[0];

            if (frame > 0) {
                pose0.translation[0] += stepAnimationTrack(pose0.trackState[0], th0.trackData[0], th0.tracksLength[0]);
                pose0.translation[1] += stepAnimationTrack(pose0.trackState[1], th0.trackData[1], th0.tracksLength[1]);
                pose0.translation[2] += stepAnimationTrack(pose0.trackState[2], th0.trackData[2], th0.tracksLength[2]);
            } else {
                pose0.translation = [...(this.defaultPose[0]?.translation || [0, 0, 0])];
                stepAnimationTrack(pose0.trackState[0], th0.trackData[0], th0.tracksLength[0]);
                stepAnimationTrack(pose0.trackState[1], th0.trackData[1], th0.tracksLength[1]);
                stepAnimationTrack(pose0.trackState[2], th0.trackData[2], th0.tracksLength[2]);
            }
        }

        // Rotation — all bones
        if (anim.hasRotation) {
            for (let i = 0; i < this.numBones; i++) {
                const th = anim.trackHeaders[i];
                const pose = this.poseData[i];

                if (frame > 0) {
                    pose.rotation[0] += stepAnimationTrack(pose.trackState[3], th.trackData[3], th.tracksLength[3]) * 0x1000;
                    pose.rotation[1] += stepAnimationTrack(pose.trackState[4], th.trackData[4], th.tracksLength[4]) * 0x1000;
                    pose.rotation[2] += stepAnimationTrack(pose.trackState[5], th.trackData[5], th.tracksLength[5]) * 0x1000;
                } else {
                    pose.rotation[0] = stepAnimationTrack(pose.trackState[3], th.trackData[3], th.tracksLength[3]) * 0x1000;
                    pose.rotation[1] = stepAnimationTrack(pose.trackState[4], th.trackData[4], th.tracksLength[4]) * 0x1000;
                    pose.rotation[2] = stepAnimationTrack(pose.trackState[5], th.trackData[5], th.tracksLength[5]) * 0x1000;
                }
            }
        }
    }

    /**
     * Mode 4: Half-rate animation (every 2 frames).
     * On even frames: sample new keyframe and compute half-step.
     * On odd frames: add half-step to interpolate.
     */
    _stepMode4() {
        const anim = this.currentAnimation;
        const frame = this.currentFrame;
        const isSubFrame = frame & 1;

        // Position
        if (anim.hasPosition) {
            if (isSubFrame) {
                // Interpolate
                for (let i = 0; i < this.numBones; i++) {
                    const pose = this.poseData[i];
                    pose.translation[0] += pose.halfTranslation[0];
                    pose.translation[1] += pose.halfTranslation[1];
                    pose.translation[2] += pose.halfTranslation[2];
                }
            } else {
                if (frame > 0) {
                    for (let i = 0; i < this.numBones; i++) {
                        const pose = this.poseData[i];
                        pose.translation[0] += pose.halfTranslation[0];
                        pose.translation[1] += pose.halfTranslation[1];
                        pose.translation[2] += pose.halfTranslation[2];
                    }
                } else {
                    // Frame 0: set from track
                    for (let i = 0; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.translation[0] = stepAnimationTrack(pose.trackState[0], th.trackData[0], th.tracksLength[0]);
                        pose.translation[1] = stepAnimationTrack(pose.trackState[1], th.trackData[1], th.tracksLength[1]);
                        pose.translation[2] = stepAnimationTrack(pose.trackState[2], th.trackData[2], th.tracksLength[2]);
                    }
                }

                // Compute half-step for next sub-frame
                if (anim.numFrames - 1 > frame) {
                    for (let i = 0; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.halfTranslation[0] = (stepAnimationTrack(pose.trackState[0], th.trackData[0], th.tracksLength[0]) / 2) | 0;
                        pose.halfTranslation[1] = (stepAnimationTrack(pose.trackState[1], th.trackData[1], th.tracksLength[1]) / 2) | 0;
                        pose.halfTranslation[2] = (stepAnimationTrack(pose.trackState[2], th.trackData[2], th.tracksLength[2]) / 2) | 0;
                    }
                }
            }
        }

        // Rotation
        if (anim.hasRotation) {
            if (isSubFrame) {
                for (let i = 0; i < this.numBones; i++) {
                    const pose = this.poseData[i];
                    pose.rotation[0] += pose.halfRotation[0];
                    pose.rotation[1] += pose.halfRotation[1];
                    pose.rotation[2] += pose.halfRotation[2];
                }
            } else {
                if (frame > 0) {
                    for (let i = 0; i < this.numBones; i++) {
                        const pose = this.poseData[i];
                        pose.rotation[0] += pose.halfRotation[0];
                        pose.rotation[1] += pose.halfRotation[1];
                        pose.rotation[2] += pose.halfRotation[2];
                    }
                } else {
                    for (let i = 0; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.rotation[0] = stepAnimationTrack(pose.trackState[3], th.trackData[3], th.tracksLength[3]) * 0x1000;
                        pose.rotation[1] = stepAnimationTrack(pose.trackState[4], th.trackData[4], th.tracksLength[4]) * 0x1000;
                        pose.rotation[2] = stepAnimationTrack(pose.trackState[5], th.trackData[5], th.tracksLength[5]) * 0x1000;
                    }
                }

                if (anim.numFrames - 1 > frame) {
                    for (let i = 0; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.halfRotation[0] = (stepAnimationTrack(pose.trackState[3], th.trackData[3], th.tracksLength[3]) * 0x800) | 0;
                        pose.halfRotation[1] = (stepAnimationTrack(pose.trackState[4], th.trackData[4], th.tracksLength[4]) * 0x800) | 0;
                        pose.halfRotation[2] = (stepAnimationTrack(pose.trackState[5], th.trackData[5], th.tracksLength[5]) * 0x800) | 0;
                    }
                }
            }
        }
    }

    /**
     * Mode 5: Quarter-rate animation (every 4 frames).
     * On every 4th frame: sample new keyframe and compute quarter-step.
     * On sub-frames: add quarter-step to interpolate.
     */
    _stepMode5() {
        const anim = this.currentAnimation;
        const frame = this.currentFrame;
        const isSubFrame = frame & 3;

        // Position — root bone (bone 0) uses special handling
        if (anim.hasPosition) {
            const th0 = anim.trackHeaders[0];
            const pose0 = this.poseData[0];

            if (isSubFrame) {
                pose0.translation[0] += pose0.halfTranslation[0];
                pose0.translation[1] += pose0.halfTranslation[1];
                pose0.translation[2] += pose0.halfTranslation[2];
            } else {
                if (frame > 0) {
                    pose0.translation[0] += pose0.halfTranslation[0];
                    pose0.translation[1] += pose0.halfTranslation[1];
                    pose0.translation[2] += pose0.halfTranslation[2];
                } else {
                    pose0.translation = [...(this.defaultPose[0]?.translation || [0, 0, 0])];
                    stepAnimationTrack(pose0.trackState[0], th0.trackData[0], th0.tracksLength[0]);
                    stepAnimationTrack(pose0.trackState[1], th0.trackData[1], th0.tracksLength[1]);
                    stepAnimationTrack(pose0.trackState[2], th0.trackData[2], th0.tracksLength[2]);
                }

                if (anim.numFrames - 1 > frame) {
                    pose0.halfTranslation[0] = (stepAnimationTrack(pose0.trackState[0], th0.trackData[0], th0.tracksLength[0]) / 4) | 0;
                    pose0.halfTranslation[1] = (stepAnimationTrack(pose0.trackState[1], th0.trackData[1], th0.tracksLength[1]) / 4) | 0;
                    pose0.halfTranslation[2] = (stepAnimationTrack(pose0.trackState[2], th0.trackData[2], th0.tracksLength[2]) / 4) | 0;
                }
            }

            // Non-root bones position (mode5_position1)
            if (isSubFrame) {
                for (let i = 1; i < this.numBones; i++) {
                    const pose = this.poseData[i];
                    pose.translation[0] += pose.halfTranslation[0];
                    pose.translation[1] += pose.halfTranslation[1];
                    pose.translation[2] += pose.halfTranslation[2];
                }
            } else if (frame === 0) {
                for (let i = 1; i < this.numBones; i++) {
                    const th = anim.trackHeaders[i];
                    const pose = this.poseData[i];
                    pose.translation[0] = stepAnimationTrack(pose.trackState[0], th.trackData[0], th.tracksLength[0]);
                    pose.translation[1] = stepAnimationTrack(pose.trackState[1], th.trackData[1], th.tracksLength[1]);
                    pose.translation[2] = stepAnimationTrack(pose.trackState[2], th.trackData[2], th.tracksLength[2]);
                }
                if (anim.numFrames - 1 > frame) {
                    for (let i = 1; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.halfTranslation[0] = (stepAnimationTrack(pose.trackState[0], th.trackData[0], th.tracksLength[0]) / 4) | 0;
                        pose.halfTranslation[1] = (stepAnimationTrack(pose.trackState[1], th.trackData[1], th.tracksLength[1]) / 4) | 0;
                        pose.halfTranslation[2] = (stepAnimationTrack(pose.trackState[2], th.trackData[2], th.tracksLength[2]) / 4) | 0;
                    }
                }
            } else {
                for (let i = 1; i < this.numBones; i++) {
                    const pose = this.poseData[i];
                    pose.translation[0] += pose.halfTranslation[0];
                    pose.translation[1] += pose.halfTranslation[1];
                    pose.translation[2] += pose.halfTranslation[2];
                }
                if (anim.numFrames - 1 > frame) {
                    for (let i = 1; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.halfTranslation[0] = (stepAnimationTrack(pose.trackState[0], th.trackData[0], th.tracksLength[0]) / 4) | 0;
                        pose.halfTranslation[1] = (stepAnimationTrack(pose.trackState[1], th.trackData[1], th.tracksLength[1]) / 4) | 0;
                        pose.halfTranslation[2] = (stepAnimationTrack(pose.trackState[2], th.trackData[2], th.tracksLength[2]) / 4) | 0;
                    }
                }
            }
        }

        // Rotation
        if (anim.hasRotation) {
            if (isSubFrame) {
                for (let i = 0; i < this.numBones; i++) {
                    const pose = this.poseData[i];
                    pose.rotation[0] += pose.halfRotation[0];
                    pose.rotation[1] += pose.halfRotation[1];
                    pose.rotation[2] += pose.halfRotation[2];
                }
            } else {
                if (frame > 0) {
                    for (let i = 0; i < this.numBones; i++) {
                        const pose = this.poseData[i];
                        pose.rotation[0] += pose.halfRotation[0];
                        pose.rotation[1] += pose.halfRotation[1];
                        pose.rotation[2] += pose.halfRotation[2];
                    }
                } else {
                    for (let i = 0; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.rotation[0] = stepAnimationTrack(pose.trackState[3], th.trackData[3], th.tracksLength[3]) * 0x1000;
                        pose.rotation[1] = stepAnimationTrack(pose.trackState[4], th.trackData[4], th.tracksLength[4]) * 0x1000;
                        pose.rotation[2] = stepAnimationTrack(pose.trackState[5], th.trackData[5], th.tracksLength[5]) * 0x1000;
                    }
                }

                if (anim.numFrames - 1 > frame) {
                    for (let i = 0; i < this.numBones; i++) {
                        const th = anim.trackHeaders[i];
                        const pose = this.poseData[i];
                        pose.halfRotation[0] = (stepAnimationTrack(pose.trackState[3], th.trackData[3], th.tracksLength[3]) * 0x400) | 0;
                        pose.halfRotation[1] = (stepAnimationTrack(pose.trackState[4], th.trackData[4], th.tracksLength[4]) * 0x400) | 0;
                        pose.halfRotation[2] = (stepAnimationTrack(pose.trackState[5], th.trackData[5], th.tracksLength[5]) * 0x400) | 0;
                    }
                }
            }
        }

        // Scale (mode 5 only supports root bone scaling)
        if (anim.hasScale) {
            const th0 = anim.trackHeaders[0];
            const pose0 = this.poseData[0];

            if (isSubFrame) {
                pose0.scale[0] += pose0.halfScale[0];
                pose0.scale[1] += pose0.halfScale[1];
                pose0.scale[2] += pose0.halfScale[2];
            } else {
                if (frame > 0) {
                    pose0.scale[0] += pose0.halfScale[0];
                    pose0.scale[1] += pose0.halfScale[1];
                    pose0.scale[2] += pose0.halfScale[2];
                } else {
                    stepAnimationTrack(pose0.trackState[6], th0.trackData[6], th0.tracksLength[6]);
                    stepAnimationTrack(pose0.trackState[7], th0.trackData[7], th0.tracksLength[7]);
                    stepAnimationTrack(pose0.trackState[8], th0.trackData[8], th0.tracksLength[8]);
                }

                if (anim.numFrames - 1 > frame) {
                    pose0.halfScale[0] = (stepAnimationTrack(pose0.trackState[6], th0.trackData[6], th0.tracksLength[6]) / 4) | 0;
                    pose0.halfScale[1] = (stepAnimationTrack(pose0.trackState[7], th0.trackData[7], th0.tracksLength[7]) / 4) | 0;
                    pose0.halfScale[2] = (stepAnimationTrack(pose0.trackState[8], th0.trackData[8], th0.tracksLength[8]) / 4) | 0;
                }
            }
        }
    }

    // ── Pose Management ────────────────────────────────────────────────────

    _copyPosePositions() {
        for (let i = 0; i < this.numBones; i++) {
            if (this.defaultPose[i]) {
                this.poseData[i].translation = [...this.defaultPose[i].translation];
            }
        }
    }

    _copyPoseRotations() {
        for (let i = 0; i < this.numBones; i++) {
            if (this.defaultPose[i]) {
                this.poseData[i].rotation = [...this.defaultPose[i].rotation];
            }
        }
    }

    _resetPoseScale() {
        for (let i = 0; i < this.numBones; i++) {
            this.poseData[i].scale = [0x10000, 0x10000, 0x10000];
        }
    }

    /**
     * Get the current pose as float arrays suitable for rendering.
     * Converts 16.16 fixed-point to floats.
     *
     * @param {number} vertexScale - Vertex coordinate scale (default: 1/16 for 12.4 FP)
     * @returns {Array} Array of {translation, rotation, scale} per bone (in floats)
     */
    getPoseForRendering(vertexScale = 1.0 / 16.0) {
        const FP = 1.0 / 65536.0; // 16.16 FP to float
        const ROT_SCALE = (2.0 * Math.PI) / 4096.0; // 12-bit angle to radians
        const result = [];

        for (let i = 0; i < this.numBones; i++) {
            const pose = this.poseData[i];
            result.push({
                translation: [
                    pose.translation[0] * FP * vertexScale,
                    pose.translation[1] * FP * vertexScale,
                    pose.translation[2] * FP * vertexScale,
                ],
                rotation: [
                    (pose.rotation[0] * FP) * ROT_SCALE,
                    (pose.rotation[1] * FP) * ROT_SCALE,
                    (pose.rotation[2] * FP) * ROT_SCALE,
                ],
                scale: [
                    pose.scale[0] * FP,
                    pose.scale[1] * FP,
                    pose.scale[2] * FP,
                ],
            });
        }
        return result;
    }
}

// ── Exports ────────────────────────────────────────────────────────────────
// (Used as module in viewer, but also works standalone)

if (typeof window !== 'undefined') {
    window.PDSAnimation = {
        MCB,
        parseAnimationData,
        parseStaticPose,
        stepAnimationTrack,
        AnimationController,
    };
}
