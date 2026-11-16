import sys; sys.path.insert(0,sys.argv[1])
from acdb import *
a=Acdb(sys.argv[2],sys.argv[3])
pat=sys.argv[4:]
for gkv,sl,sp in a.gkvs():
    s=a.fmt_gkv(gkv)
    if not all(any(p==t for t in s.split()) for p in pat): continue
    if len(gkv)!=len(pat): continue
    print('== GKV:',s, ' raw:',' '.join('%08x=%08x'%kv for kv in gkv))
    sgs=a.sg_list(sl)
    for sg,dst in sgs: print('  subgraph 0x%x -> %s'%(sg,[hex(x) for x in dst]))
    props=a.sg_props(sp)
    for sg,(drv,spf) in props.items():
        print(' SG 0x%x driver_props: %s'%(sg,hexw(drv)))
        out=[]; decode_spf(a,spf,out); print('\n'.join(out))
    for sg,dst in sgs:
        for d in dst:
            b=sg_conn(a,sg,d)
            print(' SG-CONN 0x%x -> 0x%x:'%(sg,d))
            if b: out=[]; decode_spf(a,b,out); print('\n'.join(out))
    for sg,dst in sgs:
        print(' CAL SG 0x%x'%sg)
        for ckv,res,offs in sg_cal(a,sg):
            print('  CKV {%s}'%(', '.join('%s=%s'%(a.kname(k),a.vname(v)) for k,v in ckv)))
            for iid,pid,pl in res:
                print('   iid=0x%x %s (0x%08x) [%s]: %s'%(iid,a.pname(pid),pid,len(pl) if pl is not None else '-',hexw(pl[:512]) if pl else ''))
