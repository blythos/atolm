/*
 * 1ST_READ.PRG @ 0x06014608, 90 bytes (campaign; seed 0x601460c corrected
 * -4: detector anchored on sts.l pr inside the prologue).
 * Dispatcher: step/commit callbacks around a mod-8 phase counter.
 * Names are placeholders (no Azel hypothesis for this address).
 */
struct phased {
    int x00, x04, x08;
    int phase;                  /* +0x0c, counts mod 8 */
    int x10;
    int count;                  /* +0x14 */
    void (*done)();             /* +0x18, tail-called */
    int x1c;
    void (*step)();             /* +0x20 */
};

void
func_06014608(cmd, t)
int cmd;
struct phased *t;
{
    switch (cmd) {
    case -1:
        (*t->step)(2, t);
        t->phase = (t->phase - 1) & 7;
        t->count = t->count - 1;
        (*t->done)(-2, t);
        break;
    case 1:
        (*t->step)(-2, t);
        t->phase = (t->phase + 1) & 7;
        t->count = t->count + 1;
        (*t->done)(2, t);
        break;
    }
}
