using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Numerics;
using System.Text.Json;

// Independent Cartesian-product oracles for the accelerated set queries.
public static class KernelChecks {
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    public static void Run(string output) {
        Directory.CreateDirectory(output);var rng=new Random(0);int cases=0,sat=0;
        for(int trial=0;trial<120;trial++) {
            int n=trial%12;ulong goal=63,forbid=~goal;var fs=new ulong[n];
            for(int i=0;i<n;i++)fs[i]=(ulong)rng.Next(trial%3==0?64:256);
            bool invert=trial%2!=0;
            string img=Path.Combine(output,"input.bin"),pairs=Path.Combine(output,"pairs.bin"),res=Path.Combine(output,"res.json");
            using(var w=new BinaryWriter(File.Create(img))){w.Write(0);w.Write(n);foreach(ulong f in fs){w.Write(invert?~f:f);w.Write(1);for(int j=0;j<5;j++)w.Write(-1);}}
            var all=new HashSet<ulong>();var large=new HashSet<ulong>();
            for(int i=0;i<n;i++)for(int j=0;j<n;j++){ulong p=fs[i]&fs[j];if((p&forbid)==0){all.Add(p);if(BitOperations.PopCount(p)>=3)large.Add(p);}}
            bool expected=all.Any(a=>all.Any(b=>(a|b)==goal));
            LargePairsJoin.RunVirtual(img,pairs,forbid,3,0,invert);
            var actual=new HashSet<ulong>();
            using(var r=new BinaryReader(File.OpenRead(pairs))){int m=r.ReadInt32();for(int i=0;i<m;i++){ulong f=r.ReadUInt64();r.ReadInt32();int a=r.ReadInt32(),b=r.ReadInt32();Check(a>=0&&a<n&&b>=0&&b<n&&f==(fs[a]&fs[b]),"Invalid pair witness");actual.Add(f);}}
            Check(actual.SetEquals(large),"Incomplete large pair enumeration");
            Residual.RunVirtual(img,pairs,res,forbid,invert);
            using(var report=JsonDocument.Parse(File.ReadAllText(res))){string status=report.RootElement.GetProperty("status").GetString();Check((status=="SAT")==expected,"Residual disagrees with four-input oracle");Check(status=="SAT"||status=="NO_SECOND_PAIR_COMPLETES_ANY_GIVEN_COVER","Unexpected status");}
            if(expected)sat++;
            var safe=fs.Where(f=>(f&~goal)==0).ToArray();
            for(int k=1;k<=4;k++){
                bool Brute(ulong covered,int left){if(left==0)return covered==goal;foreach(ulong f in safe)if(Brute(covered|f,left-1))return true;return false;}
                Check(RootQueries.Cover(safe,goal,k)==Brute(0,k),"Cover mismatch");
            }
            cases++;
        }
        Check(sat>0&&sat<cases,"Regression lacks both SAT and UNSAT cases");
        File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(new{status="PASS",cases,sat,unsat=cases-sat,checks="Large-pair truth sets and witnesses; residual versus full Cartesian products; 1-4 cover; repeated inputs; empty domains; symbolic complement"},new JsonSerializerOptions{WriteIndented=true}));
    }
}
