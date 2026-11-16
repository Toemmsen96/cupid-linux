import sys; sys.path.insert(0,sys.argv[1])
from acdb import *
a=Acdb(sys.argv[2],sys.argv[3])
want=[int(x,16) for x in sys.argv[4:]]
o=a.ch['CSLU'][0]; n=a.u32(o); o+=4; sgs=[]
for i in range(n):
    s,ne=a.u32(o,2); o+=8+8*ne; sgs.append(s)
for sg in sgs:
    for ckv,res,offs in sg_cal(a,sg):
        for iid,pid,pl in res:
            if pid in want or iid in want:
                print('SG 0x%x CKV{%s} iid=0x%x %s: %s'%(sg,', '.join('%s=%s'%(a.kname(k),a.vname(v)) for k,v in ckv),iid,a.pname(pid),hexw(pl[:64]) if pl else '-'))
