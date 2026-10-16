using System;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Collections.Generic;
using System.Text.Json;

public static class RootQueries {
    public sealed class Settings { public string[] names {get;set;} public int[] costs {get;set;} }
    static ulong[] fs; static int[] ts; static Settings config;
    static ulong[] Eligible(int bound) {
        var r=new List<ulong>();
        for(int i=0;i<fs.Length;i++) if(ts[i]<=bound) r.Add(fs[i]);
        return r.ToArray();
    }
    // Inclusion-maximal values. Common deadline, not individual cost minimization.
    public static ulong[] Maximal(IEnumerable<ulong> source) {
        var ordered=source.Distinct().OrderByDescending(x=>BitOperations.PopCount(x));
        var kept=new List<ulong>();
        foreach(ulong x in ordered) {
            bool covered=false;
            foreach(ulong y in kept) if((x&~y)==0) {covered=true;break;}
            if(!covered) kept.Add(x);
        }
        return kept.ToArray();
    }
    public static bool Cover(IEnumerable<ulong> source,ulong goal,int k) {
        if(goal==0) throw new ArgumentException("This query requires a nonzero goal");
        var values=Maximal(source.Where(x=>x!=0));
        if(values.Any(x=>(x&~goal)!=0)) throw new Exception("Unsafe cover");
        var posts=new List<int>[64];
        for(int b=0;b<64;b++) {
            posts[b]=new List<int>();
            for(int i=0;i<values.Length;i++) if(((values[i]>>b)&1)!=0) posts[b].Add(i);
        }
        var failed=new HashSet<(ulong,int)>();
        bool Visit(ulong missing,int left) {
            if(missing==0) return true;
            if(left==0 || failed.Contains((missing,left))) return false;
            int best=-1;
            for(int b=0;b<64;b++) if(((missing>>b)&1)!=0 &&
                (best<0 || posts[b].Count<posts[best].Count)) best=b;
            var seen=new HashSet<ulong>();
            foreach(int i in posts[best]) {
                ulong next=missing&~values[i];
                if(seen.Add(next) && Visit(next,left-1)) return true;
            }
            failed.Add((missing,left));return false;
        }
        return Visit(goal,k);
    }
    // Generate a COMPLETE dominance basis for child f containing required ones.
    // The complete input image covers bound-min_gate_cost. No old basis is read.
    static ulong[] ChildZeroBasis(int bound,ulong target) {
        ulong required=~target;
        var covers=new HashSet<ulong>();
        void Keep(ulong f) {if((f&required)==required) covers.Add(~f);}
        // Paid seed/earlier functions. All raw inputs remain behind their paid gate.
        foreach(ulong f in Eligible(bound-22048)) Keep(f);
        for(int g=0;g<config.names.Length;g++) {
            int fee=config.costs[g];
            var v=Eligible(bound-fee);
            bool inverted=(g==0||g==2||g==3||g==8||g==9||g==10||
                           g==11||g==15||g==16||g==17||g==18);
            if(g!=6 && g!=7 && g!=14) {
                ulong mask=inverted?required:target;
                v=Maximal(v.Select(x=>x^mask)).Select(x=>x^mask).ToArray();
            }
            int n=v.Length;
            void Add(int a,int b=0,int c=0,int d=0) {
                Keep(FullImage.Eval(g,v[a],v[b],v[c],v[d]));
            }
            if(g<=1) {for(int a=0;a<n;a++) Add(a,a,a,a);}
            else if(g<=7) {for(int a=0;a<n;a++)for(int b=a;b<n;b++) Add(a,b);}
            else if(g==9||g==10) {
                for(int a=0;a<n;a++)for(int b=a;b<n;b++)for(int c=0;c<n;c++) Add(a,b,c);
            } else if(g==14) {
                for(int a=0;a<n;a++)for(int b=0;b<n;b++)for(int c=0;c<n;c++) Add(a,b,c);
            } else if(g<15) {
                for(int a=0;a<n;a++)for(int b=a;b<n;b++)for(int c=b;c<n;c++) Add(a,b,c);
            } else if(g==15||g==16) {
                for(int a=0;a<n;a++)for(int b=a;b<n;b++)for(int c=a;c<n;c++)
                    for(int d=(c==a?b:c);d<n;d++) Add(a,b,c,d);
            } else {
                for(int a=0;a<n;a++)for(int b=a;b<n;b++)for(int c=b;c<n;c++)
                    for(int d=c;d<n;d++) Add(a,b,c,d);
            }
            Console.WriteLine($"child-root {config.names[g]} inputs={n} covers={covers.Count}");
        }
        return Maximal(covers);
    }
    public static void Run(string image,string output,string settings,ulong target,bool nand4) {
        config=JsonSerializer.Deserialize<Settings>(File.ReadAllText(settings));
        if(config.names.Length!=21 || config.costs.Min()!=22048)
            throw new Exception("Unexpected gate model");
        using(var r=new BinaryReader(File.OpenRead(image))) {
            if(r.ReadInt32()!=0) throw new Exception("Incomplete image");
            int n=r.ReadInt32();fs=new ulong[n];ts=new int[n];
            for(int i=0;i<n;i++) {fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();
                for(int j=0;j<5;j++)r.ReadInt32();}
            if(r.BaseStream.Position!=r.BaseStream.Length)throw new Exception("Invalid record count");
        }
        var rows=new List<object>();
        void Record(string name,bool found,int count,string method) {
            rows.Add(new {root=name,status=found?"SAT":"UNSAT",input_count=count,method});
            File.WriteAllText(output,JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
            Console.WriteLine(name+": "+(found?"SAT":"UNSAT"));
        }
        foreach(string name in new[]{"XOR2","XNOR2","OR2","NOR3","NOR4","OR3","OR4","AND4","MUX2"}) {
            int g=Array.IndexOf(config.names,name),cut=157297-config.costs[g];
            var v=Eligible(cut);bool found=false;
            if(name=="XOR2"||name=="XNOR2") {
                Array.Sort(v);ulong delta=name=="XOR2"?target:~target;
                foreach(ulong f in v) if(Array.BinarySearch(v,f^delta)>=0) {found=true;break;}
            } else if(name=="MUX2") {
                foreach(ulong c in v) {
                    bool a=false,b=false;
                    foreach(ulong f in v) {a|=((f^target)&~c)==0;b|=((f^target)&c)==0;if(a&&b)break;}
                    if(a&&b) {found=true;break;}
                }
            } else {
                bool and=name=="AND4";
                ulong goal=(name.StartsWith("NOR")||and)?~target:target;
                var safe=v.Select(f=>and?~f:f).Where(f=>(f&~goal)==0);
                found=Cover(safe,goal,int.Parse(name.Substring(name.Length-1)));
            }
            Record(name,found,v.Length,"Complete fresh common-deadline universe; exact pairing/cofactors/cover");
        }
        if(nand4) {
            var basis=ChildZeroBasis(112810,target);
            File.WriteAllText(output+".nand4_basis.json",JsonSerializer.Serialize(new {
                target=target, child_deadline_fs=112810, zero_masks=basis,
                completeness="All 21 child roots over the freshly generated complete input library; common-budget mixed dominance"
            }));
            Record("NAND4",Cover(basis,target,4),basis.Length,
                "Complete fresh all-21-root child image up to mixed dominance; exact 4-cover");
        }
    }
}
