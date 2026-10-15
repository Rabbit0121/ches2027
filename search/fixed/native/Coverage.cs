using System;
using System.Collections.Generic;
using System.Threading.Tasks;

public static partial class Engine
{
    private static int CovPop(ulong x)
    {
        x -= (x >> 1) & 0x5555555555555555UL;
        x = (x & 0x3333333333333333UL) + ((x >> 2) & 0x3333333333333333UL);
        return (int)((((x + (x >> 4)) & 0x0f0f0f0f0f0f0f0fUL) * 0x0101010101010101UL) >> 56);
    }

    private static int CovBit(ulong bit)
    {
        int n = 0;
        if ((bit & 0xffffffffUL) == 0) { n += 32; bit >>= 32; }
        if ((bit & 0xffffUL) == 0) { n += 16; bit >>= 16; }
        if ((bit & 0xffUL) == 0) { n += 8; bit >>= 8; }
        if ((bit & 0xfUL) == 0) { n += 4; bit >>= 4; }
        if ((bit & 3UL) == 0) { n += 2; bit >>= 2; }
        if ((bit & 1UL) == 0) n++;
        return n;
    }

    // Inclusion maxima at ONE common feasibility deadline. Never use these
    // maxima as permanent replacements for the arrival-labelled source pool.
    private static List<ulong> CovMaxKeys<T>(Dictionary<ulong,T> source)
    {
        var keys = new List<ulong>(source.Keys);
        keys.Sort(delegate(ulong a, ulong b) {
            int c = CovPop(b).CompareTo(CovPop(a));
            return c != 0 ? c : a.CompareTo(b);
        });
        int words = (keys.Count + 63) / 64;
        var posts = new ulong[64][];
        for (int b = 0; b < 64; b++) posts[b] = new ulong[words];
        var result = new List<ulong>();
        int checks = 0;
        foreach (ulong f in keys)
        {
            if ((++checks & 255) == 0) Check();
            bool dominated = false;
            int usedWords = (result.Count + 63) / 64;
            for (int w = 0; w < usedWords && !dominated; w++)
            {
                ulong candidates = ~0UL;
                int last = result.Count - (w << 6);
                if (last < 64) candidates = (1UL << last) - 1;
                ulong bits = f;
                while (bits != 0 && candidates != 0)
                {
                    ulong bit = bits & (~bits + 1); bits ^= bit;
                    candidates &= posts[CovBit(bit)][w];
                }
                dominated = candidates != 0;
            }
            if (dominated) continue;
            int index = result.Count;
            result.Add(f);
            ulong remaining = f;
            while (remaining != 0)
            {
                ulong bit = remaining & (~remaining + 1); remaining ^= bit;
                posts[CovBit(bit)][index >> 6] |= 1UL << (index & 63);
            }
        }
        return result;
    }

    private static List<Node> CovInputs(Dictionary<ulong,Node> pool,
                                        ulong wanted, bool complement, int g)
    {
        if (g == 6 || g == 7 || g == 14) return new List<Node>(pool.Values);
        ulong keyXor = complement ? wanted : ~wanted;
        bool inverted = g == 0 || g == 2 || g == 3 || g == 8 ||
            g == 9 || g == 10 || g == 11 || g == 15 || g == 16 ||
            g == 17 || g == 18;
        if (inverted) keyXor = ~keyXor;
        var transformed = new Dictionary<ulong,Node>(TruthKeys);
        foreach (Node n in pool.Values) transformed[n.F ^ keyXor] = n;
        var keys = CovMaxKeys(transformed);
        var result = new List<Node>(keys.Count);
        foreach (ulong key in keys) result.Add(transformed[key]);
        return result;
    }

    private static void CovPut(Dictionary<ulong,Node> pool, ulong cover, Node node)
    {
        if (cover == 0) return;
        Node old;
        if (!pool.TryGetValue(cover, out old) || node.T < old.T)
            pool[cover] = node;
    }

    private static void CovEmit(Dictionary<ulong,Node> covers, ulong wanted,
                                bool complement, int g, Node a, Node b = null,
                                Node c = null, Node d = null)
    {
        ulong f = Eval(g, a.F, b == null ? 0UL : b.F,
                      c == null ? 0UL : c.F, d == null ? 0UL : d.F);
        ulong cover = complement ? ~f : f;
        if (cover == 0 || (cover & ~wanted) != 0) return;
        int t = a.T;
        if (b != null) t = Math.Max(t,b.T);
        if (c != null) t = Math.Max(t,c.T);
        if (d != null) t = Math.Max(t,d.T);
        t += Cost[g];
        Node previous;
        if (covers.TryGetValue(cover,out previous) && previous.T <= t) return;
        covers[cover] = Make(g,a,b,c,d);
    }

    private sealed class CovPair
    {
        public ulong F;
        public int T;
        public Node A, B;
    }

    // Symbolic grouping only: pair nodes are NOT gates in the emitted netlist.
    private static void CovFour(List<Node> inputs, ulong wanted, bool complement,
                                int g, Dictionary<ulong,Node> covers)
    {
        ulong keyXor = complement ? ~wanted : wanted;
        var pairs = new Dictionary<ulong,CovPair>(TruthKeys);
        long steps = 0;
        for (int a = 0; a < inputs.Count; a++)
        for (int b = a; b < inputs.Count; b++)
        {
            if ((++steps & 4095) == 0) Check();
            Node x = inputs[a], y = inputs[b];
            ulong f = g == 17 ? x.F & y.F : x.F | y.F;
            if (!complement && (f & ~wanted) != ~wanted) continue;
            int t = Math.Max(x.T,y.T);
            ulong key = f ^ keyXor;
            CovPair old;
            if (!pairs.TryGetValue(key,out old) || t < old.T)
                pairs[key] = new CovPair { F=f,T=t,A=x,B=y };
        }
        var keys = CovMaxKeys(pairs);
        var rows = new CovPair[keys.Count];
        for (int i = 0; i < rows.Length; i++) rows[i] = pairs[keys[i]];
        pairs.Clear();
        int words = (rows.Length + 63) / 64;
        var posts = new ulong[64][];
        if (complement)
        {
            for (int b = 0; b < 64; b++) posts[b] = new ulong[words];
            for (int i = 0; i < rows.Length; i++)
            {
                ulong bits = rows[i].F & ~wanted;
                while (bits != 0)
                {
                    ulong bit = bits & (~bits + 1); bits ^= bit;
                    posts[CovBit(bit)][i >> 6] |= 1UL << (i & 63);
                }
            }
        }
        for (int i = 0; i < rows.Length; i++)
        {
            Check();
            for (int w = i >> 6; w < words; w++)
            {
                if ((++steps & 4095) == 0) Check();
                ulong candidates = ~0UL;
                if (w == (i >> 6)) candidates <<= i & 63;
                int left = rows.Length - (w << 6);
                if (left < 64) candidates &= (1UL << left) - 1;
                if (complement)
                {
                    ulong bits = rows[i].F & ~wanted;
                    while (bits != 0 && candidates != 0)
                    {
                        ulong bit = bits & (~bits + 1); bits ^= bit;
                        candidates &= ~posts[CovBit(bit)][w];
                    }
                }
                while (candidates != 0)
                {
                    ulong bit = candidates & (~candidates + 1); candidates ^= bit;
                    int j = (w << 6) + CovBit(bit);
                    CovPair a = rows[i], b = rows[j];
                    CovEmit(covers,wanted,complement,g,a.A,a.B,b.A,b.B);
                }
            }
        }
    }

    // For zero covers of OAI21, fix c and project onto c. Eligibility is
    // a & c & ~wanted == 0; a projection can be replaced by a superset.
    private static void CovOai(List<Node> inputs, ulong wanted,
                               Dictionary<ulong,Node> covers)
    {
        foreach (Node c in inputs)
        {
            Check();
            ulong cy = c.F & wanted, cz = c.F & ~wanted;
            if (cy == 0) continue;
            var projected = new Dictionary<ulong,Node>(TruthKeys);
            foreach (Node a in inputs)
            {
                if ((a.F & cz) != 0) continue;
                ulong p = a.F & cy;
                if (p == 0) continue; // repeat the nonzero other pin instead
                Node old;
                if (!projected.TryGetValue(p,out old) || a.T < old.T) projected[p] = a;
            }
            var keys = CovMaxKeys(projected);
            long steps = 0;
            for (int i = 0; i < keys.Count; i++)
            for (int j = i; j < keys.Count; j++)
            {
                if ((++steps & 4095) == 0) Check();
                CovEmit(covers,wanted,true,9,projected[keys[i]],projected[keys[j]],c);
            }
        }
    }

    public static void AddMiddle(Dictionary<ulong,Node> basePool, ulong wanted,
                                  bool complement, int g, Dictionary<ulong,Node> covers)
    {
        Check();
        if (basePool.Count == 0) return;
        var rows = CovInputs(basePool,wanted,complement,g);
        if (g == 17 || g == 15) { CovFour(rows,wanted,complement,g,covers); return; }
        if (g == 9 && complement) { CovOai(rows,wanted,covers); return; }
        int workers = Math.Min(Math.Max(1,ThreadCount),rows.Count);
        if(workers<=1) {CovRange(rows,wanted,complement,g,covers,0,rows.Count);return;}
        var maps=new Dictionary<ulong,Node>[workers];
        for(int i=0;i<workers;i++)maps[i]=new Dictionary<ulong,Node>(TruthKeys);
        System.Threading.Interlocked.Increment(ref ParallelRegions);
        try {
            Parallel.For(0,workers,new ParallelOptions{MaxDegreeOfParallelism=workers},i=>
                CovRange(rows,wanted,complement,g,maps[i],i*rows.Count/workers,(i+1)*rows.Count/workers));
        } finally {
            System.Threading.Interlocked.Decrement(ref ParallelRegions);
            // Preserve valid partial covers on slice interruption too. Shared
            // dictionaries and the adaptive scheduler are mutated only here,
            // after every parallel reader has joined, in source order.
            for(int i=0;i<workers;i++)foreach(var item in maps[i])CovPut(covers,item.Key,item.Value);
        }
    }

    private static void CovRange(List<Node> rows,ulong wanted,bool complement,
                                  int g,Dictionary<ulong,Node> covers,int first,int last)
    {
        int n = rows.Count, arity = Arity[g];
        long steps = 0;
        for (int a = first; a < last; a++)
        {
            Check();
            if (arity == 1) { CovEmit(covers,wanted,complement,g,rows[a]); continue; }
            for (int b = g == 14 ? 0 : a; b < n; b++)
            {
                if ((++steps & 4095) == 0) Check();
                if (arity == 2) { CovEmit(covers,wanted,complement,g,rows[a],rows[b]); continue; }
                int c0 = g == 9 || g == 10 || g == 14 || g == 16 ? 0 : b;
                for (int c = c0; c < n; c++)
                {
                    if ((++steps & 4095) == 0) Check();
                    if (arity == 3) { CovEmit(covers,wanted,complement,g,rows[a],rows[b],rows[c]); continue; }
                    for (int d = c; d < n; d++)
                    {
                        if ((++steps & 4095) == 0) Check();
                        if (g == 16 && (c < a || (c == a && d < b))) continue;
                        CovEmit(covers,wanted,complement,g,rows[a],rows[b],rows[c],rows[d]);
                    }
                }
            }
        }
    }

    private sealed class CovSolver
    {
        private readonly ulong Wanted;
        private readonly ulong[] Masks;
        private readonly Node[] Nodes;
        private readonly List<int>[] Posts = new List<int>[64];
        private HashSet<(ulong,int)> Failed = new HashSet<(ulong,int)>();
        private readonly int MemoEntries;
        private long Steps;
        public CovSolver(Dictionary<ulong,Node> pool, ulong wanted, int cutoff,int memoEntries=0)
        {
            // Negative memoization is an acceleration only. Forgetting entries
            // redoes exact work, without dropping branches or asserting UNSAT.
            long available=Config.HeapSoftBytes>0?
                Math.Max(64,Config.HeapSoftBytes-GC.GetTotalMemory(false)):
                GC.GetGCMemoryInfo().TotalAvailableMemoryBytes;
            MemoEntries=memoEntries>0?memoEntries:(int)Math.Max(1,Math.Min(int.MaxValue,available/8/64));
            Wanted = wanted;
            var eligible = new Dictionary<ulong,Node>(TruthKeys);
            foreach (var p in pool) if (p.Value.T <= cutoff && p.Key != 0 && (p.Key & ~wanted) == 0) eligible[p.Key]=p.Value;
            var keys = CovMaxKeys(eligible);
            Masks = keys.ToArray(); Nodes = new Node[Masks.Length];
            for (int b=0;b<64;b++) Posts[b]=new List<int>();
            for (int i=0;i<Masks.Length;i++)
            {
                Nodes[i]=eligible[Masks[i]];
                ulong bits=Masks[i];
                while(bits!=0) { ulong bit=bits&(~bits+1);bits^=bit;Posts[CovBit(bit)].Add(i); }
            }
        }
        private void Remember((ulong,int) state) {
            if(Failed.Count>=MemoEntries) {
                Failed=new HashSet<(ulong,int)>();CoverMemoResets++;
            }
            Failed.Add(state);
        }
        private bool Visit(ulong remaining,int left,List<int> selected)
        {
            if ((++Steps & 1023)==0) Check();
            if(remaining==0)return true;
            if(left==0)return false;
            var state=(remaining,left);
            if(Failed.Contains(state))return false;
            List<int> choices=null;
            ulong bits=remaining;
            while(bits!=0)
            {
                ulong bit=bits&(~bits+1);bits^=bit;
                var options=Posts[CovBit(bit)];
                if(options.Count==0){Remember(state);return false;}
                if(choices==null || options.Count<choices.Count)choices=options;
            }
            var ranked=new List<int>(choices);
            if(left==1) {
                foreach(int i in ranked) if((Masks[i]&remaining)==remaining) {
                    selected.Add(i);return true;
                }
                Remember(state);return false;
            }
            ranked.Sort(delegate(int a,int b){return CovPop(Masks[b]&remaining).CompareTo(CovPop(Masks[a]&remaining));});
            var seen=new HashSet<ulong>();
            foreach(int i in ranked)
            {
                ulong residual=remaining & ~Masks[i];
                if(seen.Contains(residual))continue;
                if(seen.Count>=MemoEntries)seen=new HashSet<ulong>();
                seen.Add(residual);
                selected.Add(i);
                if(Visit(residual,left-1,selected))return true;
                selected.RemoveAt(selected.Count-1);
            }
            Remember(state);return false;
        }
        public Node[] Solve(int count)
        {
            Check();
            var selected=new List<int>();
            if(!Visit(Wanted,count,selected) || selected.Count==0)return null;
            var result=new Node[count];
            for(int i=0;i<count;i++)result[i]=Nodes[selected[i<selected.Count?i:0]];
            return result;
        }
    }

    public static Node FindCover(Dictionary<ulong,Node> pool, ulong wanted,
                                  int root, int maxChildTime, Action<Node> onWitness=null)
    {
        Check();
        var times=new SortedSet<int>();
        foreach(var p in pool)if(p.Value.T<=maxChildTime)times.Add(p.Value.T);
        if(times.Count==0)return null;
        var levels=new int[times.Count];times.CopyTo(levels);
        int low=0,high=levels.Length-1,k=Arity[root];
        Node[] answer=new CovSolver(pool,wanted,levels[high]).Solve(k);
        if(answer==null)return null;
        // Report every valid upper bound before a tighter query can time out.
        // The final return still minimizes within this finite candidate pool.
        onWitness?.Invoke(Make(root,answer[0],answer[1],k>=3?answer[2]:null,k>=4?answer[3]:null));
        while(low<high)
        {
            int mid=low+(high-low)/2;
            Node[] trial=new CovSolver(pool,wanted,levels[mid]).Solve(k);
            if(trial==null)low=mid+1;
            else{
                high=mid;answer=trial;
                onWitness?.Invoke(Make(root,answer[0],answer[1],k>=3?answer[2]:null,k>=4?answer[3]:null));
            }
        }
        answer=new CovSolver(pool,wanted,levels[low]).Solve(k);
        return Make(root,answer[0],answer[1],k>=3?answer[2]:null,k>=4?answer[3]:null);
    }
}
