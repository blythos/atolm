/*
 * 1ST_READ.PRG @ 0x06007788, 14 bytes (Bucket 4 STOP 2 tiering test).
 * Byte-header setter, matched by the cheap-tier permuter (tools/permute.py).
 * Writes a 3-byte record header: [0]=2 (tag), [1]=0, [2]=arg.
 */
void func_06007788(p, v)
unsigned char *p;
int v;
{
    p[1] = 0;
    p[2] = v;
    p[0] = 2;
}
