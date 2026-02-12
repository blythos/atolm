
class YamahaAdpcmDecoder:
    """
    Decoder for Yamaha ADPCM (used in Sega Saturn / SCSP).
    Based on aosdk/eng_dsf/aica.c reference implementation.
    4-bit samples.
    """
    
    # aica.c: TableQuant (Fixed point 8.0 -> values * 256)
    RATE_TABLE = [
        230, 230, 230, 230, 307, 409, 512, 614
    ]
    
    # aica.c: quant_mul
    QUANT_MUL = [
        1, 3, 5, 7, 9, 11, 13, 15,
        -1, -3, -5, -7, -9, -11, -13, -15
    ]
    
    def __init__(self):
        self.signal = 0
        self.step = 127 # cur_quant in aica.c
        
    def decode(self, data, initial_signal=None, initial_step=None, nibble_order='lo_hi'):
        """
        Decodes ADPCM data.
        nibble_order: 'hi_lo' (Standard) or 'lo_hi' (Saturn/AICA standard).
        """
        if initial_signal is not None:
             self.signal = initial_signal
        if initial_step is not None:
             self.step = initial_step
             
        samples = []
        
        for byte in data:
            if nibble_order == 'lo_hi':
                n1 = byte & 0x0F       # Low nibble first
                n2 = (byte >> 4) & 0x0F # High nibble second
            else:
                n1 = (byte >> 4) & 0x0F
                n2 = byte & 0x0F
            
            self._decode_nibble(n1, samples)
            self._decode_nibble(n2, samples)
            
        return samples

    def _decode_nibble(self, nibble, samples):
        # Match aica.c DecodeADPCM
        # int x = adpcm->cur_quant * quant_mul [Delta & 15];
        x = self.step * self.QUANT_MUL[nibble & 15]
        
        # x = adpcm->cur_sample + ((int)(x + ((UINT32)x >> 29)) >> 3);
        # Python handles shifts differently for negative numbers.
        # Javascript/C style logical right shift for the term inside:
        def urshift(val, n): 
            return (val % 0x100000000) >> n
            
        term2 = urshift(x, 29)
        delta_signal = (x + term2) >> 3
        
        new_signal = self.signal + delta_signal
        
        # adpcm->cur_sample=ICLIP16(x);
        self.signal = max(-32768, min(32767, new_signal))
        
        samples.append(self.signal)
        
        # adpcm->cur_quant=(adpcm->cur_quant*TableQuant[Delta&7])>>ADPCMSHIFT;
        # ADPCMSHIFT is 8
        self.step = (self.step * self.RATE_TABLE[nibble & 7]) >> 8
        
        # Clamp step
        # (adpcm->cur_quant<0x7f)?0x7f:((adpcm->cur_quant>0x6000)?0x6000:adpcm->cur_quant);
        if self.step < 127: self.step = 127
        elif self.step > 24576: self.step = 24576
