# =============================================================
# Ouk Chaktrang AI Training Script
# Works on: Google Colab, Kaggle, Hugging Face, Render, GitHub Actions
# Auto-detects platform, loads weights from JSONBin, trains, pushes back
# =============================================================

import os, sys, json, time, random, math, requests, copy
from collections import deque

# =============================================================
# CONFIG — edit these two lines only
# =============================================================
JSONBIN_KEY = os.environ.get('JSONBIN_KEY', 'YOUR_JSONBIN_KEY_HERE')
JSONBIN_BIN = os.environ.get('JSONBIN_BIN', 'YOUR_JSONBIN_BIN_HERE')
# =============================================================

# Detect platform
def detect_platform():
    if os.path.exists('/content'):          return 'colab'
    if os.path.exists('/kaggle'):           return 'kaggle'
    if os.environ.get('RENDER'):            return 'render'
    if os.environ.get('SPACE_ID'):          return 'huggingface'
    if os.environ.get('GITHUB_ACTIONS'):    return 'github'
    return 'local'

PLATFORM = detect_platform()
print(f"Platform: {PLATFORM}")

# Time limits per platform (seconds)
TIME_LIMITS = {
    'colab':      10 * 3600,   # 10 hours
    'kaggle':     10 * 3600,   # 10 hours
    'render':     20 * 3600,   # 20 hours (restart before limit)
    'huggingface':20 * 3600,
    'github':      4 * 3600,   # 4 hours (GitHub Actions limit 6hrs)
    'local':      99 * 3600,
}
MAX_TIME = TIME_LIMITS.get(PLATFORM, 4 * 3600)

# =============================================================
# GAME ENGINE
# =============================================================
W, BL = 'w', 'b'
PV = {'K':20000,'Q':155,'R':560,'B':295,'N':320,'P':130}

def make_board():
    b = [[None]*8 for _ in range(8)]
    back = ['R','N','B','K','Q','B','N','R']
    for c,p in enumerate(back): b[0][c]=BL+p
    for c in range(8): b[2][c]=BL+'P'
    for c,p in enumerate(back): b[7][c]=W+p
    for c in range(8): b[5][c]=W+'P'
    return b

def opp(c): return BL if c==W else W
def col(p): return p[0] if p else None
def typ(p): return p[1] if p else None

def copy_board(b): return [r[:] for r in b]

def make_flags():
    return {'wKM':False,'bKM':False,'wQM':False,'bQM':False,'wKR':False,'bKR':False}

def in_check(board, color):
    king = color+'K'
    kr=kc=-1
    for r in range(8):
        for c in range(8):
            if board[r][c]==king: kr,kc=r,c
    if kr==-1: return True
    en=opp(color)
    for r in range(8):
        for c in range(8):
            p=board[r][c]
            if not p or col(p)!=en: continue
            for m in piece_attacks(board,r,c,typ(p),en):
                if m==(kr,kc): return True
    return False

def piece_attacks(board,r,c,t,color):
    attacks=[]
    en=opp(color)
    def add(tr,tc):
        if 0<=tr<8 and 0<=tc<8: attacks.append((tr,tc))
    def slide(dirs):
        for dr,dc in dirs:
            nr,nc=r+dr,c+dc
            while 0<=nr<8 and 0<=nc<8:
                attacks.append((nr,nc))
                if board[nr][nc]: break
                nr+=dr; nc+=dc
    if t=='K':
        for dr in[-1,0,1]:
            for dc in[-1,0,1]:
                if dr or dc: add(r+dr,c+dc)
    elif t=='Q':
        for dr,dc in[(-1,-1),(-1,1),(1,-1),(1,1)]: add(r+dr,c+dc)
    elif t=='B':
        fwd=-1 if color==W else 1
        for dr,dc in[(-1,-1),(-1,1),(1,-1),(1,1)]: add(r+dr,c+dc)
        add(r+fwd,c)
    elif t=='N':
        for dr,dc in[(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]: add(r+dr,c+dc)
    elif t=='R':
        slide([(-1,0),(1,0),(0,-1),(0,1)])
    elif t=='P':
        fwd=-1 if color==W else 1
        add(r+fwd,c)
        for dc in[-1,1]: add(r+fwd,c+dc)
    return attacks

def legal_moves(board,color,flags):
    moves=[]
    for r in range(8):
        for c in range(8):
            p=board[r][c]
            if not p or col(p)!=color: continue
            t=typ(p)
            moves+=get_moves(board,r,c,t,color,flags)
    return [m for m in moves if not in_check(apply_move(board,m),color)]

def get_moves(board,r,c,t,color,flags):
    moves=[]
    en=opp(color)
    def add(tr,tc,sp=None):
        if 0<=tr<8 and 0<=tc<8:
            tg=board[tr][tc]
            if tg is None or col(tg)==en:
                moves.append({'from':(r,c),'to':(tr,tc),'special':sp})
    def slide(dirs):
        for dr,dc in dirs:
            nr,nc=r+dr,c+dc
            while 0<=nr<8 and 0<=nc<8:
                tg=board[nr][nc]
                if tg is None:
                    moves.append({'from':(r,c),'to':(nr,nc),'special':None})
                elif col(tg)==en:
                    moves.append({'from':(r,c),'to':(nr,nc),'special':None}); break
                else: break
                nr+=dr; nc+=dc
    if t=='K':
        for dr in[-1,0,1]:
            for dc in[-1,0,1]:
                if dr or dc: add(r+dr,c+dc)
        km='wKM' if color==W else 'bKM'
        rf='wKR' if color==W else 'bKR'
        if not flags[km] and not flags[rf] and not in_check(board,color):
            for dr,dc in[(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
                nr,nc=r+dr,c+dc
                if 0<=nr<8 and 0<=nc<8 and board[nr][nc] is None:
                    moves.append({'from':(r,c),'to':(nr,nc),'special':'kleap'})
    elif t=='Q':
        for dr,dc in[(-1,-1),(-1,1),(1,-1),(1,1)]: add(r+dr,c+dc)
        qm='wQM' if color==W else 'bQM'
        if not flags[qm]:
            fwd=-1 if color==W else 1
            nr=r+2*fwd
            if 0<=nr<8 and board[r+fwd][c] is None and board[nr][c] is None:
                moves.append({'from':(r,c),'to':(nr,c),'special':'qleap'})
    elif t=='B':
        fwd=-1 if color==W else 1
        for dr,dc in[(-1,-1),(-1,1),(1,-1),(1,1)]: add(r+dr,c+dc)
        add(r+fwd,c)
    elif t=='N':
        for dr,dc in[(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]: add(r+dr,c+dc)
    elif t=='R':
        slide([(-1,0),(1,0),(0,-1),(0,1)])
    elif t=='P':
        fwd=-1 if color==W else 1
        nr=r+fwd
        if 0<=nr<8 and board[nr][c] is None:
            sp='promo' if (color==W and nr==2) or (color==BL and nr==5) else None
            moves.append({'from':(r,c),'to':(nr,c),'special':sp})
        for dc in[-1,1]:
            nc=c+dc
            if 0<=nr<8 and 0<=nc<8 and board[nr][nc] and col(board[nr][nc])==en:
                sp='promo' if (color==W and nr==2) or (color==BL and nr==5) else None
                moves.append({'from':(r,c),'to':(nr,nc),'special':sp})
    return moves

def apply_move(board,move):
    b=copy_board(board)
    fr,fc=move['from']; tr,tc=move['to']
    piece=b[fr][fc]
    b[tr][tc]=piece; b[fr][fc]=None
    if move.get('special')=='promo': b[tr][tc]=col(piece)+'Q'
    return b

def apply_flags(flags,board,move,color):
    f=dict(flags)
    fr,fc=move['from']
    p=board[fr][fc]
    if not p: return f
    t=typ(p)
    if t=='K':
        if color==W: f['wKM']=True
        else: f['bKM']=True
    if t=='Q':
        if color==W: f['wQM']=True
        else: f['bQM']=True
    if t=='R':
        tr,tc=move['to']
        ek=BL+'K' if color==W else W+'K'
        for r2 in range(8):
            for c2 in range(8):
                if board[r2][c2]==ek:
                    if r2==tr or c2==tc:
                        if color==W: f['bKR']=True
                        else: f['wKR']=True
    return f

# =============================================================
# NEURAL NETWORK (matches browser: 64→32→16→1 value, 64→32→64 policy)
# =============================================================
NN_IN,NN_H1,NN_H2,NN_POL = 64,32,16,64

def relu(x): return max(0.0,x)
def tanh(x): return math.tanh(x)

def extract_features(board,color):
    feat=[0.0]*NN_IN
    matW=matB=pawnsW=pawnsB=0
    kRW=kRB=3; kFW=kFB=4
    rookOW=rookOB=passW=passB=douW=douB=pAdvW=pAdvB=0
    knCW=knCB=bisW=bisB=kSW=kSB=0
    pfW={}; pfB={}; prW={}; prB={}
    for r in range(8):
        for c in range(8):
            p=board[r][c]
            if not p: continue
            t=typ(p); cl=col(p); pv=PV.get(t,0)
            if cl==W:
                matW+=pv
                if t=='K': kRW=r; kFW=c
                if t=='P':
                    pawnsW+=1; pfW[c]=pfW.get(c,0)+1
                    if c not in prW or r<prW[c]: prW[c]=r
                    pAdvW+=(7-r)
                if t=='B': bisW+=1
                if t=='N':
                    nd=abs(r-3.5)+abs(c-3.5); knCW+=(7-nd*1.5)
            else:
                matB+=pv
                if t=='K': kRB=r; kFB=c
                if t=='P':
                    pawnsB+=1; pfB[c]=pfB.get(c,0)+1
                    if c not in prB or r>prB[c]: prB[c]=r
                    pAdvB+=r
                if t=='B': bisB+=1
                if t=='N':
                    nd=abs(r-3.5)+abs(c-3.5); knCB+=(7-nd*1.5)
    total=matW+matB or 1
    for r in range(8):
        for c in range(8):
            p=board[r][c]
            if not p or typ(p)!='R': continue
            if col(p)==W and not pfW.get(c) and not pfB.get(c): rookOW+=1
            if col(p)==BL and not pfB.get(c) and not pfW.get(c): rookOB+=1
    for f in range(8):
        if pfW.get(f,0)>1: douW+=1
        if pfB.get(f,0)>1: douB+=1
        if pfW.get(f,0)>0:
            rk=prW[f]; bl=any(pfB.get(af,0)>0 and prB.get(af,999)<rk for af in range(max(0,f-1),min(8,f+2)))
            if not bl: passW+=1
        if pfB.get(f,0)>0:
            rk=prB[f]; bl=any(pfW.get(af,0)>0 and prW.get(af,0)>rk for af in range(max(0,f-1),min(8,f+2)))
            if not bl: passB+=1
    def ks(kr,kc,ec):
        t=0
        for dr in range(-2,3):
            for dc in range(-2,3):
                nr,nc=kr+dr,kc+dc
                if 0<=nr<8 and 0<=nc<8 and board[nr][nc] and col(board[nr][nc])==ec: t+=1
        return t
    kSW=ks(kRW,kFW,BL); kSB=ks(kRB,kFB,W)
    feat[0]=(matW-matB)/3000; feat[1]=matW/total
    feat[2]=(pawnsW-pawnsB)/8; feat[3]=(kRW-3.5)/4
    feat[4]=(kRB-3.5)/4; feat[5]=total/6000
    feat[6]=1 if total<2400 else 0; feat[7]=(kFW-3.5)/4
    feat[8]=(kFB-3.5)/4; feat[9]=1 if color==W else -1
    feat[10]=min(rookOW,2)/2; feat[11]=min(rookOB,2)/2
    feat[12]=min(passW,4)/4; feat[13]=min(passB,4)/4
    feat[14]=min(douW,4)/4; feat[15]=min(douB,4)/4
    feat[16]=(pAdvW/pawnsW/7) if pawnsW else 0
    feat[17]=(pAdvB/pawnsB/7) if pawnsB else 0
    feat[18]=max(-1,min(1,knCW/14)); feat[19]=max(-1,min(1,knCB/14))
    feat[20]=bisW/2; feat[21]=bisB/2
    feat[22]=min(1,kSW/8); feat[23]=min(1,kSB/8)
    pts=['K','Q','R','B','N','P']
    for pi,pt in enumerate(pts):
        wc=bc=0
        for r in range(8):
            for c in range(8):
                p=board[r][c]
                if p and typ(p)==pt:
                    if col(p)==W: wc+=1
                    else: bc+=1
        feat[25+pi]=(wc-bc)/2
    csqs=[(3,3),(3,4),(4,3),(4,4)]
    for ci,(cr,cc) in enumerate(csqs):
        p=board[cr][cc]
        feat[31+ci]=1 if p and col(p)==W else (-1 if p else 0)
    feat[35]=min(1,matW/matB) if matB else 1
    return feat

class OukNet:
    def __init__(self):
        def xavier(fi,fo,n):
            lim=math.sqrt(6/(fi+fo))
            return [random.uniform(-lim,lim) for _ in range(n)]
        def zeros(n): return [0.0]*n
        self.W1=xavier(NN_IN,NN_H1,NN_IN*NN_H1); self.B1=zeros(NN_H1)
        self.W2=xavier(NN_H1,NN_H2,NN_H1*NN_H2); self.B2=zeros(NN_H2)
        self.W3=xavier(NN_H2,1,NN_H2);            self.B3=[0.0]
        self.WP1=xavier(NN_IN,NN_H1,NN_IN*NN_H1); self.BP1=zeros(NN_H1)
        self.WP2=xavier(NN_H1,NN_POL,NN_H1*NN_POL); self.BP2=zeros(NN_POL)
        self.games=0; self.trained=False; self.policyEnabled=False

    def forward(self,feat):
        h1=[relu(self.B1[i]+sum(feat[j]*self.W1[i*NN_IN+j] for j in range(NN_IN))) for i in range(NN_H1)]
        h2=[relu(self.B2[i]+sum(h1[j]*self.W2[i*NN_H1+j] for j in range(NN_H1))) for i in range(NN_H2)]
        out=tanh(self.B3[0]+sum(h2[i]*self.W3[i] for i in range(NN_H2)))
        return out,h1,h2

    def policy(self,h1):
        hp=[relu(self.BP1[i]+sum(h1[j]*self.WP1[i*NN_IN+j] for j in range(NN_IN))) for i in range(NN_H1)]
        logits=[self.BP2[i]+sum(hp[j]*self.WP2[i*NN_H1+j] for j in range(NN_H1)) for i in range(NN_POL)]
        mx=max(logits); exps=[math.exp(x-mx) for x in logits]; s=sum(exps)
        return [e/s for e in exps]

    def backprop(self,feat,target,lr=0.005):
        out,h1,h2=self.forward(feat)
        err=target-out; dout=err*(1-out*out)
        for i in range(NN_H2): self.W3[i]+=lr*2*dout*h2[i]
        self.B3[0]+=lr*2*dout
        dh2=[dout*self.W3[i] for i in range(NN_H2)]
        dz2=[dh2[i] if h2[i]>0 else 0 for i in range(NN_H2)]
        for i in range(NN_H2):
            self.B2[i]+=lr*dz2[i]
            for j in range(NN_H1): self.W2[i*NN_H1+j]+=lr*dz2[i]*h1[j]
        dh1=[sum(dz2[i]*self.W2[i*NN_H1+j] for i in range(NN_H2)) for j in range(NN_H1)]
        dz1=[dh1[i] if h1[i]>0 else 0 for i in range(NN_H1)]
        for i in range(NN_H1):
            self.B1[i]+=lr*dz1[i]
            for j in range(NN_IN): self.W1[i*NN_IN+j]+=lr*dz1[i]*feat[j]

    def to_dict(self):
        return {
            'W1':self.W1,'B1':self.B1,'W2':self.W2,'B2':self.B2,
            'W3':self.W3,'B3':self.B3,
            'WP1':self.WP1,'BP1':self.BP1,'WP2':self.WP2,'BP2':self.BP2,
            'trained':self.trained,'games':self.games,'policyEnabled':self.policyEnabled,
            'W4':None,'B4':None
        }

    def from_dict(self,d):
        for k in ['W1','B1','W2','B2','W3','B3','WP1','BP1','WP2','BP2']:
            if d.get(k): setattr(self,k,d[k])
        self.games=d.get('games',0)
        self.trained=d.get('trained',False)
        self.policyEnabled=d.get('policyEnabled',False)

# =============================================================
# CLOUD: load/save weights from JSONBin
# =============================================================
def cloud_load(net):
    if JSONBIN_KEY=='YOUR_JSONBIN_KEY_HERE': return False
    try:
        r=requests.get(f'https://api.jsonbin.io/v3/b/{JSONBIN_BIN}/latest',
            headers={'X-Master-Key':JSONBIN_KEY},timeout=15)
        if r.ok:
            data=r.json().get('record',{})
            if data.get('nnue') and data['nnue'].get('W1'):
                net.from_dict(data['nnue'])
                print(f"Loaded weights from cloud (games={net.games})")
                return True
    except Exception as e:
        print(f"Cloud load failed: {e}")
    return False

def cloud_save(net):
    if JSONBIN_KEY=='YOUR_JSONBIN_KEY_HERE': return False
    try:
        payload=json.dumps({'nnue':net.to_dict()},separators=(',',':'))
        r=requests.put(f'https://api.jsonbin.io/v3/b/{JSONBIN_BIN}',
            data=payload,
            headers={'Content-Type':'application/json','X-Master-Key':JSONBIN_KEY},
            timeout=30)
        if r.ok:
            print(f"Pushed weights to cloud (games={net.games})")
            return True
        else:
            print(f"Cloud save failed: {r.status_code}")
    except Exception as e:
        print(f"Cloud save error: {e}")
    return False

# =============================================================
# SELF-PLAY
# =============================================================
def move_to_pol(move):
    fr,fc=move['from']; tr,tc=move['to']
    fsq=fr*8+fc; dr=tr-fr; dc=tc-fc
    dirs=[(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1)]
    best=0; bd=-999
    for di,(dr2,dc2) in enumerate(dirs):
        dot=dr*dr2+dc*dc2
        if dot>bd: bd=dot; best=di
    return min(fsq*8+best,NN_POL-1)

def quick_eval(board,color):
    wm=bm=0
    for r in range(8):
        for c in range(8):
            p=board[r][c]
            if p: 
                if col(p)==W: wm+=PV.get(typ(p),0)
                else: bm+=PV.get(typ(p),0)
    score=(wm-bm)/3000.0
    return score if color==W else -score

def pick_move(net,board,color,flags,move_num):
    ms=legal_moves(board,color,flags)
    if not ms: return None
    if len(ms)==1: return ms[0]
    # Temperature moves: use policy priors
    if net.policyEnabled and net.trained:
        feat=extract_features(board,color)
        _,h1,_=net.forward(feat)
        probs=net.policy(h1)
        scored=[(probs[move_to_pol(m)],m) for m in ms]
        scored.sort(reverse=True)
        if move_num<20:
            pool=scored[:min(3,len(scored))]
            weights=[0.70,0.20,0.10]
            r=random.random(); cum=0
            for wi,(p,m) in enumerate(pool):
                cum+=weights[wi] if wi<len(weights) else 0.05
                if r<=cum: return m
            return pool[0][1]
        return scored[0][1]
    # Fallback: eval-based
    scored=[(quick_eval(apply_move(board,m),opp(color)),m) for m in ms]
    scored.sort(reverse=True)
    if move_num<15:
        pool=scored[:min(3,len(scored))]
        return random.choice(pool)[1]
    return scored[0][1]

def play_game(net):
    board=make_board(); flags=make_flags(); color=W
    history=[]; pos_seen={}; max_moves=120
    for mn in range(max_moves):
        ms=legal_moves(board,color,flags)
        if not ms: break
        history.append((extract_features(board,color),color))
        move=pick_move(net,board,color,flags,mn)
        if not move: break
        flags=apply_flags(flags,board,move,color)
        board=apply_move(board,move)
        color=opp(color)
        fen=''.join(p or '.' for row in board for p in row)+color
        pos_seen[fen]=pos_seen.get(fen,0)+1
        if pos_seen[fen]>=3: break
    ms=legal_moves(board,color,flags)
    if not ms and in_check(board,color):
        winner=opp(color)
    else:
        wm=sum(PV.get(typ(p),0) for row in board for p in row if p and col(p)==W)
        bm=sum(PV.get(typ(p),0) for row in board for p in row if p and col(p)==BL)
        winner=W if wm>bm+200 else (BL if bm>wm+200 else None)
    examples=[]
    n=len(history)
    for i,(feat,c) in enumerate(history):
        z=0.0 if winner is None else (1.0 if c==winner else -1.0)
        z*=0.6+0.4*(i/max(1,n-1))
        examples.append((feat,z))
    return examples,winner

# =============================================================
# MAIN TRAINING LOOP
# =============================================================
def main():
    print(f"\n=== Ouk Chaktrang AI Trainer ===")
    print(f"Platform: {PLATFORM} | Time limit: {MAX_TIME//3600}h")
    print(f"JSONBin: {'configured' if JSONBIN_KEY!='YOUR_JSONBIN_KEY_HERE' else 'NOT CONFIGURED'}\n")

    net=OukNet()
    cloud_load(net)  # Load latest weights first

    replay=deque(maxlen=5000)
    t0=time.time()
    game_num=0; wins=draws=losses=0
    PUSH_EVERY=50  # push to cloud every N games
    SAVE_FILE='ouk_weights.json'

    while time.time()-t0 < MAX_TIME:
        examples,winner=play_game(net)
        replay.extend(examples)
        game_num+=1; net.games+=1

        if winner==W: wins+=1
        elif winner==BL: losses+=1
        else: draws+=1

        # Train on replay buffer
        if len(replay)>=16:
            batch=random.sample(list(replay),min(64,len(replay)))
            for feat,z in batch: net.backprop(feat,z)
            if len(replay)>1000:
                batch2=random.sample(list(replay),min(64,len(replay)))
                for feat,z in batch2: net.backprop(feat,z)

        if not net.trained and net.games>=5: net.trained=True
        if not net.policyEnabled and net.games>=50: net.policyEnabled=True

        elapsed=time.time()-t0
        rate=game_num/elapsed*3600
        remaining=(MAX_TIME-elapsed)/3600
        print(f"Game {net.games} | W:{wins} L:{losses} D:{draws} | "
              f"Buf:{len(replay)} | {rate:.0f} games/hr | {remaining:.1f}h left")

        # Push to cloud and save locally
        if game_num%PUSH_EVERY==0:
            cloud_save(net)
            with open(SAVE_FILE,'w') as f:
                json.dump({'nnue':net.to_dict()},f,separators=(',',':'))
            print(f"  Saved locally: {SAVE_FILE}")

    # Final save
    cloud_save(net)
    with open(SAVE_FILE,'w') as f:
        json.dump({'nnue':net.to_dict()},f,separators=(',',':'))
    print(f"\nDone! {net.games} total games trained. Weights saved to {SAVE_FILE}")

if __name__=='__main__':
    main()
