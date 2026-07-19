/*
 * 1ST_READ.PRG @ 0x06014d14, 108 bytes (campaign). Walks the object list
 * of world-grid cell (x,y) and invokes 0x6031360 on each object's class
 * with a 4-word parameter block. Neighbours the Azel-named grid functions
 * (updateWorldGrid 0x60144c0, GetCellAtWorldPos 0x6014f70). Absolute
 * addresses are literal casts: final linked byte values, no externs
 * (elfcnv rejects unresolved externals).
 */
struct cellnode {
    struct cellnode *next;
    struct gridobj *obj;
};

struct gridobj {
    int x00;
    struct objclass *cls;
};

struct objclass {
    int x00, x04, x08, x0c;
    int x10;
};

struct grid {
    int w;
    int pad[79];
    int table;                  /* +0x140: cell list heads */
};

void
func_06014d14(a, x, y, b, c)
int a, x, y, b, c;
{
    struct cellnode *n;
    struct gridobj *o;
    struct objclass *k;
    struct {
        struct gridobj *obj;
        int b;
        int pad;
        int c;
    } blk;
    struct grid *g;

    g = (struct grid *)0x60526dc;
    n = (struct cellnode *)(g->table + (y * g->w + x) * 4);
    for (n = *(struct cellnode **)n; n; n = n->next) {
        o = n->obj;
        k = o->cls;
        blk.obj = o;
        blk.b = b;
        blk.c = c;
        (*(void (*)()) 0x6031360)(a, k, k->x10, &blk);
    }
}
