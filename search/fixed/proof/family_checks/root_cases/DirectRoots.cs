using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;

// Exact queries over a complete common-deadline input universe.
// Complemented values in a De Morgan identity are symbolic, not free gates.
public static class DirectRoots {
    static ulong[] fs; static int[] ts;
    public static void Load(string image) {
        using var r=new BinaryReader(File.OpenRead(image));
        if(r.ReadInt32()!=0)throw new Exception("Incomplete input image");
        int n=r.ReadInt32();fs=new ulong[n];ts=new int[n];
        for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();r.BaseStream.Position+=20;}
        if(r.BaseStream.Position!=r.BaseStream.Length)throw new Exception("Invalid image size");
    }
    public static ulong[] Eligible(int cut) {
        var a=new List<ulong>();for(int i=0;i<fs.Length;i++)if(ts[i]<=cut)a.Add(fs[i]);return a.ToArray();
    }
    public static void Extract(string dest,int cut) {
        using var w=new BinaryWriter(File.Create(dest));w.Write(0);int n=0;
        foreach(int t in ts)if(t<=cut)n++;w.Write(n);
        for(int i=0;i<fs.Length;i++)if(ts[i]<=cut){w.Write(fs[i]);w.Write(ts[i]);for(int j=0;j<5;j++)w.Write(-1);}
    }
    public static void Run(string image,string output,ulong target) {
        Load(image);var rows=new List<object>();
        void Record(string name,bool found,int n,string method) {
            rows.Add(new{root=name,status=found?"SAT":"UNSAT",input_count=n,method});
            File.WriteAllText(output,JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
            Console.WriteLine(name+": "+(found?"SAT":"UNSAT"));
        }
        foreach(var p in new[]{("INV_NOR3",73706,3),("INV_NOR4",43936,4)}) {
            var v=Eligible(p.Item2);Record(p.Item1,RootQueries.Cover(v.Where(f=>(f&~target)==0),target,p.Item3),v.Length,"Exact safe union cover");
        }
        {
            var v=Eligible(60074);ulong want=~target;bool found=false;
            foreach(ulong c in v){bool a=false,b=false;foreach(ulong f in v){a|=((f^want)&~c)==0;b|=((f^want)&c)==0;}if(a&&b){found=true;break;}}
            Record("INV_MUX2",found,v.Length,"All selectors and exact cofactors");
        }
        {
            var v=Eligible(83630);var centers=RootQueries.Maximal(v.Where(f=>(f&~target)==0));bool found=false;
            foreach(ulong c in centers){ulong need=target&~c;var proj=v.Where(f=>(f&need)==need).Select(f=>f&~target).Distinct().ToArray();
                for(int i=0;i<proj.Length&&!found;i++)for(int j=i;j<proj.Length;j++)if((proj[i]&proj[j])==0){found=true;break;}if(found)break;
            }
            Record("INV_AOI21",found,v.Length,"All maximal legal c, required residual ones, exact disjoint projections");
        }
        {
            var v=Eligible(102598);var zeros=RootQueries.Maximal(v.Where(f=>(f&target)==target).Select(f=>~f));bool found=false;int i=0;
            foreach(ulong zero in zeros){ulong forbidden=(~zero)&~target;var proj=new HashSet<ulong>();
                foreach(ulong f in v)if((f&forbidden)==0)proj.Add(f&target);
                if(RootQueries.Cover(proj,target,2)){found=true;break;}
                i++;if(i%20==0)Console.WriteLine($"INV_OAI21 centers={i}/{zeros.Length}");
            }
            Record("INV_OAI21",found,v.Length,"All minimal c containing target, exact two-cover of allowed projections");
        }
    }
}
