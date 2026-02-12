
class YamahaAdpcmDecoder:
    """
    Decoder for Yamaha ADPCM (used in Sega Saturn / SCSP).
    4-bit samples.
    """
    
    def __init__(self):
        self.signal = 0
        self.step = 127 # Default initial step? Or 0?
        # AzelLib audio.cpp likely initializes this.
        # Common initial step is 127 or 0x7F.
        
    def decode(self, data, initial_signal=0, initial_step=127):
        # Yamaha ADPCM Logic
        # (Based on standard algorithms found in MAME/VGMStream for YM2610/SCSP)
        
        if initial_signal is not None:
             self.signal = initial_signal
        if initial_step is not None:
             self.step = initial_step
             
        samples = []
        
        for byte in data:
            # 4-bit samples. Order: High nibble, then Low nibble? 
            # Or Low then High?
            # Standard is usually High then Low.
            
            n1 = (byte >> 4) & 0x0F
            n2 = byte & 0x0F
            
            self._decode_nibble(n1, samples)
            self._decode_nibble(n2, samples)
            
        return samples

    def _decode_nibble(self, nibble, samples):
        # Yamaha Algorithm
        # 1. Update Signal
        # step * delta / 8
        # delta = (nibble & 7) * 2 + 1
        # if (nibble & 8) signal -= ... else signal += ...
        
        step = self.step
        delta = (nibble & 7) * 2 + 1
        calc = (step * delta) >> 3
        
        if nibble & 8:
            self.signal -= calc
        else:
            self.signal += calc
            
        # Clamp Signal (16-bit signed)
        self.signal = max(-32768, min(32767, self.signal))
        
        samples.append(self.signal)
        
        # 2. Update Step
        # step = (step * Rate[nibble]) >> 8
        # Rate table (standard):
        # 57, 57, 57, 57, 77, 102, 128, 153 (for 0-7)
        # Same for 8-15 (ignore sign bit 8)
        
        rate_table = [57, 57, 57, 57, 77, 102, 128, 153]
        rate = rate_table[nibble & 7]
        
        self.step = (self.step * rate) >> 6 # Shift 6? Or 8?
        # Some impls say >> 6, some >> 8.
        # MAME ymz280b.cpp uses:
        # step = (step * rate_table[n&7]) >> 6
        # Clamp step
        if self.step < 127: self.step = 127
        elif self.step > 24576: self.step = 24576
        
        # Note: AzelLib might use different table or shift.
        # But this is the standard Yamaha algo.
