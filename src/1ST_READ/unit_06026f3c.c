/*
 * 1ST_READ.PRG translation unit @ 0x06026f3c .. 0x06026f86 (74 bytes),
 * three functions (Bucket 4 STOP 1, deliverable 2 — proof-of-machine).
 *
 * Closed translation unit (tools/tu_cluster.py): a weighted-checksum leaf
 * (cksum) plus a store wrapper and a verify wrapper that each call it via a
 * PC-relative bsr. No literal pool, no external calls — so the ONLY
 * translation-unit properties under test are the two intra-unit bsr
 * displacements (both wrappers -> cksum) and SHC's instruction schedule.
 * Compiled TOGETHER, in binary order, as one unit.
 *
 * cksum: weighted sum over the record body (skips the 4-byte header that
 * holds the checksum), weight = 1-based position index.
 * Names are descriptive placeholders (no Azel hypothesis for this address).
 */

int
cksum(p, n)
unsigned char *p;
int n;
{
    int sum;
    int w;

    sum = 0;
    w = 1;
    p += 4;
    n -= 4;
    do {
        sum += (int)*p++ * w;
        w++;
    } while (--n);
    return sum;
}

void
store_cksum(p, n)
int *p;
int n;
{
    *p = cksum((unsigned char *)p, n);
}

int
verify_cksum(p, n)
int *p;
int n;
{
    int c;

    c = cksum((unsigned char *)p, n);
    return *p == c;
}
