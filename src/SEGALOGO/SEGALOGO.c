/*
 * SEGALOGO.PRG .text [0x06054000, 0x06054148) — both functions + shared
 * literal pool, one translation unit. Best candidate after Bucket 1 step 4
 * iteration: 317/328 bytes match the original; the 11-byte residual (three
 * clusters, all instruction-scheduling/peephole choices, zero structural
 * difference) is documented in docs/FINDINGS/SEGALOGO_segalogo.md.
 *
 * Names are placeholders. External addresses reference 1ST_READ code and
 * work RAM, called/accessed via absolute constants (self-contained compile:
 * elfcnv rejects unresolved relocations; the original's relocated externs
 * produce identical bytes).
 *
 * Source-shape notes (byte-level requirements, discovered empirically):
 * - The global blocks must be accessed via constant struct derefs (entry)
 *   or a plain pointer local (init); cast pointer arithmetic on constants
 *   gets folded into distinct pool literals, which the original lacks.
 * - The two q stores are one chained assignment (single value temp in r2,
 *   w562 stored first).
 * - The v temp reused for both VDP1 command words is what pulls the
 *   value loads into r4 ahead of the base materializations and gives
 *   one/vram/p their original callee-saved registers (r12/r13/r14).
 */

struct scrn {
    char pad0[0xf8];
    short w248;
    short w250;
    short w252;
};

struct blk {            /* 0x604b224 */
    long f0;
    struct scrn *scr;
    long f8;
    long f12;
    long f16;
    long f20;
};

struct wrk {            /* 0x604b244 */
    char pad0[0x112];
    short w274;
    char pad114[0x11e];
    short w562;
};

struct gst {            /* 0x604b484 */
    char pad0[72];
    short w72;
    char pad74[2];
    char b76;
    char b77;
};

static void func_0605403a();

void
func_06054000()
{
    long t;

    func_0605403a();
    if (((struct gst *)0x604b484)->b77 >= ((struct gst *)0x604b484)->b76) {
        struct wrk *q;
        q = (struct wrk *)0x604b244;
        q->w274 = q->w562 = 0;
    }
    t = (*(long (*)())0x6034c20)((struct gst *)0x604b484);
    (*(void (*)())0x6034aaa)((struct gst *)0x604b484, t,
                             ((struct gst *)0x604b484)->w72, 30);
}

static void
func_0605403a()
{
    struct blk *p;
    char *vram;
    long one;
    long v;

    (*(void (*)())0x6032292)();
    (*(void (*)())0x600fc14)((void *)0x6054148, (void *)0x25e20000);
    vram = (char *)0x25e24000;
    (*(void (*)())0x60288e0)((void *)0x6054dfc, vram);
    (*(void (*)())0x602fd7a)((void *)0x6054e04, (void *)0x25f00800, 32, 0);

    one = 1;
    p = (struct blk *)0x604b224;
    v = 0x37ffffff;
    *(long *)((char *)p->scr + 16) = v;
    p->f20 = one;
    v = 0x4ffffff;
    *(long *)((char *)p->scr + 20) = v;
    p->f20 = one;
    (*(void (*)())0x60326dc)((void *)0x6054dd0);
    (*(void (*)())0x6028a26)(0, vram, vram, vram, vram);

    p->scr->w248 = 4;
    p->scr->w250 = 0x700;
    p->scr->w252 = 0;
    p->f20 = one;
    *(char *)0x605036c = 0;
    if (*(volatile unsigned short *)0x25f80004 & one) {
        (*(void (*)())0x60289cc)(0x10000, 0xe000);
    }
    *(char *)0x605036c = 4;
}
