using System;
using System.IO;
using System.Collections.Generic;
public static class GlobalTriple {
sealed class H:IEqualityComparer<ulong>{public bool Equals(ulong a,ulong b)=>a==b;public int GetHashCode(ulong x){x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return(int)x;}}
public static void Run(string centers,string input,string output,ulong Y){
var sw=System.Diagnostics.Stopwatch.StartNew();var allowed=new HashSet<ulong>(new H());using(var r=new BinaryReader(File.OpenRead(centers))){int n=r.ReadInt32();for(int i=0;i<n;i++){ulong s=r.ReadUInt64(),q=s;while(true){allowed.Add(q);if(q==0)break;q=(q-1)&s;}}}
ulong[] fs;using(var r=new BinaryReader(File.OpenRead(input))){int n=r.ReadInt32();fs=new ulong[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();r.ReadInt32();}}
var found=new HashSet<ulong>(new H());long triples=0,pairs=0;for(int i=0;i<fs.Length;i++){if(i%100==0)Console.WriteLine($"i={i}/{fs.Length} truths={found.Count} triples={triples} seconds={sw.Elapsed.TotalSeconds:F2}");for(int j=i;j<fs.Length;j++){ulong p=fs[i]|fs[j];pairs++;if(!allowed.Contains(p&Y))continue;for(int k=j;k<fs.Length;k++){triples++;ulong t=p|fs[k];if((t&~Y)!=0&&allowed.Contains(t&Y))found.Add(t);}}}
using(var w=new BinaryWriter(File.Create(output))){w.Write(found.Count);foreach(var f in found)w.Write(f);}File.WriteAllText(output+".json",$"{{\"status\":\"COMPLETE_COMMON_CENTER_NAND3_TRUTHS\",\"inputs\":{fs.Length},\"truths\":{found.Count},\"pairs\":{pairs},\"triples\":{triples},\"seconds\":{sw.Elapsed.TotalSeconds}}}");
}
}
