import struct,json,sys,os
class Acdb:
    def __init__(s,path,names):
        s.d=open(path,'rb').read()
        s.ch={}
        o=12
        while o+8<=len(s.d):
            cid=s.d[o:o+4].decode('latin1'); sz=struct.unpack_from('<I',s.d,o+4)[0]
            s.ch[cid]=(o+8,sz); o+=8+sz
        n=json.load(open(names))
        s.N={k:{int(a,16):b for a,b in v.items()} for k,v in n.items()}
    def u32(s,o,n=1):
        r=struct.unpack_from('<%dI'%n,s.d,o); return r if n>1 else r[0]
    def kname(s,k): return s.N['key'].get(k,hex(k))
    def vname(s,v): return s.N['val'].get(v,hex(v))
    def mname(s,m): return s.N['mod'].get(m,hex(m))
    def pname(s,p): return s.N['pid'].get(p,hex(p))
    def gkvs(s):
        o,sz=s.ch['GKVT']; lo=s.ch['GKVL'][0]
        nt=s.u32(o); o+=4; res=[]
        for t in range(nt):
            nk,ne=s.u32(o,2); o+=8
            for e in range(ne):
                ent=s.u32(o,nk+1) if nk+1>1 else (s.u32(o),)
                o+=4*(nk+1)
                keys=ent[:nk]; lut=ent[nk]
                p=lo+lut; nk2,ne2=s.u32(p,2); p+=8
                for e2 in range(ne2):
                    ent2=s.u32(p,nk2+2); p+=4*(nk2+2)
                    res.append((tuple(zip(keys,ent2[:nk2])),ent2[nk2],ent2[nk2+1]))
        return res
    def fmt_gkv(s,g): return ' '.join('%s=%s'%(s.kname(k),s.vname(v)) for k,v in g)
    def sg_list(s,off):
        p=s.ch['POOL'][0]+off; size,n=s.u32(p,2); p+=8; out=[]
        for i in range(n):
            sg,nd=s.u32(p,2); p+=8
            dst=list(s.u32(p,nd)) if nd>1 else ([s.u32(p)] if nd==1 else [])
            p+=4*nd; out.append((sg,dst))
        return out
    def sg_props(s,off):
        base=s.ch['POOL'][0]+off
        total,n=s.u32(base,2); p=base+8; out={}
        end=base+8+total
        while p<end and len(out)<n:
            sg,size=s.u32(p,2); q=p+8
            dsz=s.u32(q); drv=s.d[q+4:q+4+dsz]; q+=4+dsz
            ssz=s.u32(q); spf=s.d[q+4:q+4+ssz]
            out[sg]=(drv,spf); p+=8+size
        return out

APM_PIDS={0x08001001:'SUB_GRAPH_CONFIG',0x08001000:'CONTAINER_CONFIG',0x08001002:'MODULES_LIST',0x08001003:'MODULE_PROP',0x08001004:'MODULE_CONN',0x08001061:'MODULE_CTRL_LINK_CFG'}
SG_PROPS={0x0800100E:'PERF_MODE',0x0800100F:'DIRECTION',0x08001010:'SCENARIO_ID',0x080010CC:'VSID'}
CONT_PROPS={0x08001011:'TYPE',0x08001012:'GRAPH_POS',0x08001013:'STACK_SIZE',0x08001014:'PROC_DOMAIN',0x080010CB:'PARENT_CONT',0x08001174:'HEAP_ID',0x0800124D:'PEER_HEAP_ID',0x08001A9B:'FRAME_SIZE'}
MOD_PROPS={0x08001015:'PORT_INFO',0x08001A9A:'HEAP_ID'}
LINK_PROPS={0x08001062:'INTENT_LIST',0x0800136F:'HEAP_ID'}
def hexw(b): return ' '.join('%08x'%x for x in struct.unpack('<%dI'%(len(b)//4),b[:len(b)//4*4]))+(' +'+b[len(b)//4*4:].hex() if len(b)%4 else '')
def decode_spf(a,spf,out,mods=None):
    p=0
    while p+12<=len(spf):
        miid,pid,sz=struct.unpack_from('<III',spf,p); pl=spf[p+12:p+12+sz]; p+=12+sz
        if sz%8: p+=8-sz%8
        name=APM_PIDS.get(pid,a.pname(pid))
        out.append('  [%s miid=0x%x size=%d]'%(name,miid,sz))
        st={'q':0}
        def rd(n=1):
            r=struct.unpack_from('<%dI'%n,pl,st['q']); st['q']+=4*n; return r if n>1 else r[0]
        def props(tab):
            np_=rd(); res=[]
            for i in range(np_):
                pid_,psz=rd(2); val=pl[st['q']:st['q']+psz]; st['q']+=psz
                res.append('%s=%s'%(tab.get(pid_,hex(pid_)),hexw(val)))
            return res
        try:
            if pid==0x08001001:
                for i in range(rd()):
                    sg=rd(); out.append('    SG 0x%x: %s'%(sg,', '.join(props(SG_PROPS))))
            elif pid==0x08001000:
                for i in range(rd()):
                    c=rd(); out.append('    CONT 0x%x: %s'%(c,', '.join(props(CONT_PROPS))))
            elif pid==0x08001002:
                for i in range(rd()):
                    sg,c,nm=rd(3)
                    ms=[rd(2) for j in range(nm)]
                    if mods is not None:
                        for m,iid in ms: mods[iid]=m
                    out.append('    SG 0x%x CONT 0x%x:\n      '%(sg,c)+'\n      '.join('%s (0x%08x) iid=0x%x'%(a.mname(m),m,iid) for m,iid in ms))
            elif pid==0x08001003:
                for i in range(rd()):
                    iid=rd(); out.append('    MOD iid=0x%x: %s'%(iid,', '.join(props(MOD_PROPS))))
            elif pid==0x08001004:
                for i in range(rd()):
                    s_,sp,d_,dp=rd(4); out.append('    CONN 0x%x:%x -> 0x%x:%x'%(s_,sp,d_,dp))
            elif pid==0x08001061:
                for i in range(rd()):
                    p1,pp1,p2,pp2=rd(4); out.append('    CTRL 0x%x:%x <-> 0x%x:%x %s'%(p1,pp1,p2,pp2,', '.join(props(LINK_PROPS))))
            else:
                out.append('    '+hexw(pl))
        except Exception as e:
            out.append('    !decode error %s: %s'%(e,hexw(pl)))

def sg_cal(a,sg):
    """yield (ckv list, [(iid,pid,payload)])"""
    o=a.ch['CSLU'][0]; n=a.u32(o); o+=4
    ents=None
    for i in range(n):
        s,ne=a.u32(o,2); o+=8
        if s==sg: ents=[a.u32(o+8*j,2) for j in range(ne)]; break
        o+=8*ne
    if ents is None: return
    for kt,lut in ents:
        p=a.ch['CAKT'][0]+kt; nk=a.u32(p); keys=[a.u32(p+4+4*j) for j in range(nk)]
        q=a.ch['CDLU'][0]+lut; nv,nl=a.u32(q,2); q+=8
        for e in range(nl):
            vals=[a.u32(q+4*j) for j in range(nv)]; q+=4*nv
            de,do,do2=a.u32(q,3); q+=12
            ckv=list(zip(keys,vals))
            dp=a.ch['CDDE'][0]+de; ndef=a.u32(dp); pairs=[a.u32(dp+4+8*j,2) for j in range(ndef)]
            op=a.ch['CDDO'][0]+do; ndot=a.u32(op)
            res=[]
            for j,(iid,pid) in enumerate(pairs):
                if j<ndot:
                    doff=a.u32(op+4+4*j); pp=a.ch['POOL'][0]+doff; psz=a.u32(pp); pl=a.d[pp+4:pp+4+psz]
                else: pl=None
                res.append((iid,pid,pl))
            yield ckv,res,(de,do,do2)

def sg_conn(a,src,dst):
    o,sz=a.ch['SCLU']; n=a.u32(o)
    for i in range(n):
        s,d,de,do=a.u32(o+4+16*i,4)
        if s==src and d==dst:
            dp=a.ch['SCDE'][0]+de; op=a.ch['SCDO'][0]+do
            nd=a.u32(dp); blob=b''
            for k in range(nd):
                miid,pid=a.u32(dp+4+8*k,2); doff=a.u32(op+4+4*k)
                pp=a.ch['POOL'][0]+doff; psz=a.u32(pp); pl=a.d[pp+4:pp+4+psz]
                blob+=struct.pack('<III',miid,pid,psz)+pl+b'\0'*((8-psz%8)%8)
            return blob
    return None
