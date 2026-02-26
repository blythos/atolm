import os
import struct
import argparse
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

class SEQParser:
    def __init__(self, data):
        self.data = data
        self.offset = 0
        self.resolution = 480
        self.num_tempo_events = 0
        self.data_offset = 0
        self.tempo_loop_offset = 0
        self.tempo_events = []
        
    def _read_u8(self):
        val = self.data[self.offset]
        self.offset += 1
        return val

    def _read_u16(self):
        val = struct.unpack('>H', self.data[self.offset:self.offset+2])[0]
        self.offset += 2
        return val

    def _read_u32(self):
        val = struct.unpack('>I', self.data[self.offset:self.offset+4])[0]
        self.offset += 4
        return val

    def parse_header(self, start_offset=0):
        self.offset = start_offset
        self.resolution = self._read_u16()
        self.num_tempo_events = self._read_u16()
        self.data_offset = self._read_u16()
        self.tempo_loop_offset = self._read_u16()
        
        self.tempo_events = []
        for _ in range(self.num_tempo_events):
            tick = self._read_u32()
            mspb = self._read_u32()
            self.tempo_events.append({'tick': tick, 'mspb': mspb})
            
    def convert_to_midi(self, track_name="Track"):
        mid = MidiFile(ticks_per_beat=self.resolution)
        track = MidiTrack()
        mid.tracks.append(track)
        
        track.append(MetaMessage('track_name', name=track_name, time=0))
        
        # Add tempo events
        last_tick = 0
        for tempo in sorted(self.tempo_events, key=lambda t: t["tick"]):
            delta = tempo['tick'] - last_tick
            track.append(MetaMessage('set_tempo', tempo=tempo['mspb'], time=delta))
            last_tick = tempo['tick']
            
        # Process data track
        self.offset = self.data_offset
        if hasattr(self, 'song_start_offset'):
            self.offset += self.song_start_offset
            
        clock = 0
        delta_acc = 0
        gate_acc = 0
        
        # gatequeue stores [expire_clock, channel, note, velocity]
        gate_queue = []
        
        done = False
        ref_stack = [] # For reference (81) commands: (return_offset, count)
        
        # Helper to process gate queue
        def process_gates(current_clock, midi_track):
            nonlocal delta_acc
            gate_queue.sort(key=lambda x: x[0])
            while gate_queue and gate_queue[0][0] <= current_clock:
                expire_clock, ch, note, vel = gate_queue.pop(0)
        # We need to output MIDI events with relative deltas.
        # last_midi_event_clock keeps track of when the last event was written.
        last_midi_event_clock = 0

        def safe_msg(m_type, **kwargs):
            try:
                # Clamp common numeric fields
                for k in ['note', 'velocity', 'control', 'value', 'program']:
                    if k in kwargs:
                        kwargs[k] = max(0, min(127, kwargs[k]))
                return Message(m_type, **kwargs)
            except ValueError as e:
                print(f"MIDI ValueError: {e} | Type: {m_type} | Args: {kwargs}")
                raise e

        def write_event(midi_track, msg, event_clock):
            nonlocal last_midi_event_clock
            delta = event_clock - last_midi_event_clock
            msg.time = delta
            midi_track.append(msg)
            last_midi_event_clock = event_clock

        def check_gates(target_clock, midi_track):
            # Write out any scheduled note offs that happen before or at target_clock
            while True:
                next_off = None
                best_idx = -1
                for i, g in enumerate(gate_queue):
                    if g[0] <= target_clock:
                        if next_off is None or g[0] < next_off[0]:
                            next_off = g
                            best_idx = i
                
                if next_off:
                    gate_queue.pop(best_idx)
                    write_event(midi_track, safe_msg('note_off', channel=next_off[1], note=next_off[2], velocity=64), next_off[0])
                else:
                    break

        while not done:
            if ref_stack:
                ret_off, count = ref_stack[-1]
                if count == 0:
                    self.offset = ret_off
                    ref_stack.pop()
                    if not done and self.offset >= len(self.data): break # safety
                    continue

            status = self._read_u8()
            
            # Handle Note On (0x00-0x7F)
            if status <= 0x7F:
                channel = status & 0x0F
                note = self._read_u8()
                velocity = self._read_u8()
                gate_byte = self._read_u8()
                delta_byte = self._read_u8()
                
                curr_gate = gate_acc + gate_byte
                if status & 0x40: curr_gate += 256
                gate_acc = 0 # reset
                
                curr_delta = delta_acc + delta_byte
                if status & 0x20: curr_delta += 256
                delta_acc = 0 # reset
                
                # Check gates before this note on
                check_gates(clock, track)
                
                # Ensure values are MIDI compliant (0-127)
                def clamp(val, name):
                    if val < 0 or val > 127:
                        return max(0, min(127, val))
                    return val

                note_midi = clamp(note, "note")
                vel_midi = clamp(velocity, "velocity")

                # Note bytes are direct MIDI note numbers (0-127). No transposition needed.
                # Low notes (0-23) are legitimate — they may be used for drums/SFX or very
                # low bass instruments in the Saturn tone bank. Sending them verbatim is correct.
                # "Pitch outside valid range" warnings from the GM soundfont player are cosmetic
                # (the soundfont lacks samples for those notes on those GM programs) and do not
                # indicate an encoding error.

                # Write Note On
                write_event(track, safe_msg('note_on', channel=channel, note=note_midi, velocity=vel_midi), clock)
                
                # Queue Note Off
                gate_queue.append([clock + curr_gate, channel, note_midi, vel_midi])
                
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)

            # Control Change (Bx)
            elif 0xB0 <= status <= 0xBF:
                channel = status & 0x0F
                cc = self._read_u8()
                val = self._read_u8()
                delta_byte = self._read_u8()
                
                curr_delta = delta_acc + delta_byte
                delta_acc = 0
                
                check_gates(clock, track)
                write_event(track, safe_msg('control_change', channel=channel, control=cc & 0x7F, value=val & 0x7F), clock)
                
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)

            # Program Change (Cx)
            elif 0xC0 <= status <= 0xCF:
                channel = status & 0x0F
                prog = self._read_u8()
                delta_byte = self._read_u8()
                
                curr_delta = delta_acc + delta_byte
                delta_acc = 0
                
                check_gates(clock, track)
                write_event(track, safe_msg('program_change', channel=channel, program=prog & 0x7F), clock)
                
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)

            # Pitch Bend (Ex)
            elif 0xE0 <= status <= 0xEF:
                channel = status & 0x0F
                # seq2mid: "yy is the pitch value. To convert to midi's pitch wheel, 
                # just put the value in the second pitch byte(not the first)."
                # MIDI pitch is 14-bit unsigned, where 8192 is center.
                # If we have 1 byte (0-127), it maps to the high 7 bits.
                val_byte = self._read_u8()
                delta_byte = self._read_u8()
                
                curr_delta = delta_acc + delta_byte
                delta_acc = 0
                
                check_gates(clock, track)
                # mido pitch is -8192 to 8191.
                # center 0. val_byte 64 is likely center.
                pitch = (val_byte << 7) - 8192
                if pitch > 8191: pitch = 8191
                if pitch < -8192: pitch = -8192
                
                write_event(track, safe_msg('pitchwheel', channel=channel, pitch=pitch), clock)
                
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)

            # Reference (81)
            elif status == 0x81:
                ref_offset = self._read_u16()
                ref_count = self._read_u8()
                
                # Save current position and jump
                ref_stack.append((self.offset, ref_count))
                # Offset is relative to the start of the data track
                self.offset = (self.song_start_offset + self.data_offset) + ref_offset

            # Loop (82) - handled as marker
            elif status == 0x82:
                delta_byte = self._read_u8()
                curr_delta = delta_acc + delta_byte
                delta_acc = 0
                
                check_gates(clock, track)
                track.append(MetaMessage('marker', text='loop', time=max(0, clock - last_midi_event_clock)))
                last_midi_event_clock = clock 
                
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)

            # Skip 0x80 (Padding/Mystery)
            elif status == 0x80:
                pass 

            # End of Track (83)
            elif status == 0x83:
                # Finish all gates
                check_gates(clock + 1000000, track) # Flush all
                track.append(MetaMessage('end_of_track', time=0))
                done = True

            # Gate Extends (88-8B)
            elif 0x88 <= status <= 0x8B:
                exts = [0x200, 0x800, 0x1000, 0x2000]
                gate_acc += exts[status - 0x88]

            # Delta Extends (8C-8F)
            elif 0x8C <= status <= 0x8F:
                exts = [0x100, 0x200, 0x800, 0x1000]
                delta_acc += exts[status - 0x8C]
            
            # Aftertouch (Aw, Dx)
            elif 0xA0 <= status <= 0xAF:
                channel = status & 0x0F
                note = self._read_u8()
                val = self._read_u8()
                delta_byte = self._read_u8()
                curr_delta = delta_acc + delta_byte
                delta_acc = 0
                check_gates(clock, track)
                write_event(track, safe_msg('polytouch', channel=channel, note=note, value=val), clock)
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)
            elif 0xD0 <= status <= 0xDF:
                channel = status & 0x0F
                val = self._read_u8()
                delta_byte = self._read_u8()
                curr_delta = delta_acc + delta_byte
                delta_acc = 0
                check_gates(clock, track)
                write_event(track, safe_msg('aftertouch', channel=channel, value=val), clock)
                clock += curr_delta
                if ref_stack: ref_stack[-1] = (ref_stack[-1][0], ref_stack[-1][1] - 1)
                
            else:
                if status != 0: # 0 is often just padding at end
                    print(f"Unknown status byte {hex(status)} at offset {hex(self.offset-1)}")
                # Continue if possible, though unknown status often breaks alignment
                if status > 0x80:
                    # Try to skip assuming it might be a single byte or something
                    pass 
                
        return mid

def main():
    parser = argparse.ArgumentParser(description='Saturn SEQ to MIDI Converter')
    parser.add_argument('--input', type=str, required=True, help='Path to .SEQ file')
    parser.add_argument('--output', type=str, help='Output .mid path or directory')
    parser.add_argument('--catalog', type=str, help='Path to music_catalog.json for naming')
    
    args = parser.parse_args()
    
    catalog = None
    if args.catalog:
        import json
        with open(args.catalog, 'r') as f:
            catalog = json.load(f)
            
    with open(args.input, 'rb') as f:
        data = f.read()

    input_filename = os.path.basename(args.input)
    
    # SEQ multi-song layout:
    #   [0:2]  u16 num_songs  (big-endian)
    #   [2:6]  u32 song_pointer[0]  (big-endian, 4 bytes, absolute file offset)
    #   [6:10] u32 song_pointer[1]  (if num_songs > 1)
    #   ...
    # Each pointer points to a song header: u16 resolution, u16 num_tempo_events, ...
    num_songs = struct.unpack('>H', data[0:2])[0]
    song_pointers = []
    if 0 < num_songs < 256:  # Sanity check: unlikely to have >256 songs
        for i in range(num_songs):
            ptr = struct.unpack('>I', data[2 + i*4 : 6 + i*4])[0]  # 4-byte u32, not 3-byte
            song_pointers.append(ptr)
    else:
        # Fallback: single-song files that don't have the standard header
        song_pointers = [6]

    for i, ptr in enumerate(song_pointers):
        if ptr >= len(data): continue
        
        parser = SEQParser(data)
        parser.song_start_offset = ptr
        try:
            parser.parse_header(ptr)
            mid = parser.convert_to_midi(f"{os.path.basename(args.input)}_{i}")
            
            out_path = args.output
            if not out_path or os.path.isdir(out_path):
                # Try to find name in catalog
                display_name = None
                if catalog:
                    # Search in named_tracks
                    for track in catalog.get('named_tracks', []):
                        if track['seq']['name'].upper() == input_filename.upper():
                            display_name = track.get('name')
                            break
                    # If not found, search in unnamed_tracks (though unlikely to have a name there)
                    if not display_name:
                        for track in catalog.get('unnamed_tracks', []):
                            if track['seq']['name'].upper() == input_filename.upper():
                                # Unnamed tracks don't have 'name' field, but maybe we found the entry
                                break
                
                base_name = os.path.splitext(input_filename)[0]
                if display_name:
                    # Clean display name for filesystem
                    safe_name = "".join([c if c.isalnum() or c in " ._()" else "_" for c in display_name])
                    base_name = f"{base_name} ({safe_name})"
                
                suffix = f"_{i}" if len(song_pointers) > 1 else ""
                target_filename = f"{base_name}{suffix}.mid"
                
                if out_path and os.path.isdir(out_path):
                    out_path = os.path.join(out_path, target_filename)
                else:
                    out_path = os.path.join(os.path.dirname(args.input), target_filename)
            
            mid.save(out_path)
            print(f"Converted {args.input} (song {i}) -> {out_path}")
            if len(song_pointers) == 1: break 
        except Exception as e:
            print(f"Error converting {args.input} (song {i}): {e}")
            import traceback
            # traceback.print_exc()
            continue

if __name__ == "__main__":
    main()
