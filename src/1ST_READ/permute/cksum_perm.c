int cksum(p,n)
unsigned char *p;
int n;
{
    /*PERM int sum=0; int w=1; | int w=1; int sum=0; | register int sum=0; register int w=1; | register int w=1; register int sum=0; */
    int t;
    p += 4;
    n -= 4;
    do {
        /*PERM t=(int)*p++; sum+=t*w; | t=(int)*p++; sum+=w*t; | sum+=(int)*p++*w; | sum+=w*(int)*p++; */
        w++;
    } while (--n);
    return sum;
}
