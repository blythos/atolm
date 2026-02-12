
class DviAdpcmDecoder:
    """
    IMA/DVI ADPCM Decoder for Sega FILM/CPK audio.
    Matches standard IMA ADPCM logic.
    """
    
    index_table = [
        -1, -1, -1, -1, 2, 4, 6, 8,
        -1, -1, -1, -1, 2, 4, 6, 8
    ]

    step_table = [
        7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
        19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
        50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
        130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
        337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
        876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
        2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
        5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
        15290, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
    ]

    def __init__(self):
        self.predictor = 0
        self.step_index = 0

    def decode(self, data, initial_predictor=0, initial_index=0):
        """
        Decodes a bytearray of ADPCM data into a list of 16-bit signed PCM samples.
        """
        samples = []
        
        # Reset state for chunk-based decoding if provided
        # Or should we persist state? 
        # For film chunks usually each chunk is independent or state is provided.
        # But if not provided, we should probably persist?
        # The calling code passes `step_index` from header.
        if initial_index is not None:
             self.step_index = initial_index
        if initial_predictor is not None:
             self.predictor = initial_predictor

        # Clamp index just in case
        self.step_index = max(0, min(88, self.step_index))
        
        # DVI ADPCM: 4-bits per sample.
        # Layout: [Sample1(low nibble) Sample2(high nibble)]? 
        # Or [Sample1(high) Sample2(low)]?
        # Hint said "Standard Nibble Order (High-Low)"
        # But Brute Force suggested maybe Low-High?
        # Let's default to High-Low (Standard).
        
        for byte in data:
            # High Nibble First
            n1 = (byte >> 4) & 0x0F
            n2 = byte & 0x0F
            
            self._decode_nibble(n1, samples)
            self._decode_nibble(n2, samples)
            
        return samples

    def _decode_nibble(self, nibble, samples):
        step = self.step_table[self.step_index]
        diff = step >> 3
        
        if nibble & 4: diff += step
        if nibble & 2: diff += (step >> 1)
        if nibble & 1: diff += (step >> 2)
        
        if nibble & 8:
            self.predictor -= diff
        else:
            self.predictor += diff
            
        # Clamp predictor
        if self.predictor > 32767: self.predictor = 32767
        elif self.predictor < -32768: self.predictor = -32768
        
        samples.append(self.predictor)
        
        # Update index
        self.step_index += self.index_table[nibble & 7]
        
        # Clamp index
        if self.step_index < 0: self.step_index = 0
        elif self.step_index > 88: self.step_index = 88
