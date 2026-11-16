import sys,struct
d=open(sys.argv[1],'rb').read()
print(d[:4], struct.unpack_from('<II',d,4), len(d))
o=12
while o+8<=len(d):
    cid=d[o:o+4]; sz=struct.unpack_from('<I',d,o+4)[0]
    print('%08x %s size=%d (0x%x)'%(o,cid,sz,sz))
    o+=8+sz
