/*
 * 1ST_READ.PRG @ 0x06006622, 18 bytes. Matched (Bucket 0, 2026-07-15).
 * shc-5.0-r31, -optimize=1 -speed. Proof: config/targets/1ST_READ.yaml.
 * Pure register-arithmetic leaf; purpose unknown, name is placeholder.
 */
unsigned int
func_06006622(x)
unsigned int x;
{
    unsigned int y;
    y = x & 15;
    x = x ^ y;
    x = x >> 1;
    y = y + x;
    x = x >> 2;
    y = y + x;
    return y;
}
