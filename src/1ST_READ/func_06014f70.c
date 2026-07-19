/*
 * 1ST_READ.PRG @ 0x06014f70, 122 B (campaign, isolated-ok). Azel name:
 * GetCellAtWorldPos. Converts world (x,y) via 0x6013138 to grid cell
 * coords, bounds-checks against the global grid at 0x60526dc, returns the
 * 8x8 cell value (0 out of range). Absolute refs are literal casts (elfcnv
 * rejects unresolved externals).
 */
struct grid {
    int xmax, ymax;       /* 00, 04 */
    int xoff, yoff;       /* 08, 0c */
    int xorg, yorg;       /* 10, 14 */
    int pad1[6];          /* 18..2c */
    int scale;            /* 30 */
    int pad2[3];          /* 34..3c */
    int cells[64];        /* 40: 8x8, row stride 32 bytes */
};

int
func_06014f70(x, y)
int x, y;
{
    struct grid *g;
    int cx, cy;

    g = (struct grid *)0x60526dc;
    cx = (*(int (*)()) 0x6013138)(x, g->scale);
    cy = (*(int (*)()) 0x6013138)(y, g->scale);
    if (cx < 0 || cx >= g->xmax || cy < 0 || cy >= g->ymax)
        return 0;
    cx -= g->xorg;
    cy -= g->yorg;
    if (cx < -3 || cx > 3 || cy < -3 || cy > 3)
        return 0;
    return *(int *)((char *)g->cells
                    + (((g->yoff + cy) & 7) << 5)
                    + (((g->xoff + cx) & 7) << 2));
}
