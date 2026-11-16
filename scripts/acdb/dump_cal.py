import sys; sys.path.insert(0,sys.argv[1])
from acdb import *
a=Acdb(sys.argv[2],sys.argv[3])
for sgs in sys.argv[4:]:
    sg=int(sgs,16); print('### SG 0x%x'%sg)
    for ckv,res,offs in sg_cal(a,sg):
        print(' CKV {%s} def/dot/dot2=%s'%(', '.join('%s=%s'%(a.kname(k),a.vname(v) if v else '0') for k,v in ckv),[hex(x) for x in offs]))
        for iid,pid,pl in res:
            print('   iid=0x%x %s (0x%08x) [%s]: %s'%(iid,a.pname(pid),pid,len(pl) if pl is not None else '-',hexw(pl[:256]) if pl else ''))
