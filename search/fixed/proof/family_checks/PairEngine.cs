using System;
using System.IO;
using System.Collections.Generic;
using System.Numerics;
using System.Runtime.InteropServices;
public static class PairEngine {
 sealed class U64Hash:IEqualityComparer<ulong>{public bool Equals(ulong a,ulong b)=>a==b;public int GetHashCode(ulong x){unchecked{x^=x>>30;x*=0xbf58476d1ce4e5b9UL;x^=x>>27;x*=0x94d049bb133111ebUL;x^=x>>31;return (int)x;}}}
 struct Hit { public int T,I,J; public Hit(int t,int i,int j){T=t;I=i;J=j;} }
 public static void Run(string input,string output,ulong target) {
  var watch=System.Diagnostics.Stopwatch.StartNew();
  int n;ulong[] fs;int[] ts;
  using(var r=new BinaryReader(File.OpenRead(input))){n=r.ReadInt32();fs=new ulong[n];ts=new int[n];for(int i=0;i<n;i++){fs[i]=r.ReadUInt64();ts[i]=r.ReadInt32();}}
  ulong forbidden=~target;int words=(n+63)/64;var posts=new ulong[64][];
  for(int b=0;b<64;b++)if(((forbidden>>b)&1)!=0)posts[b]=new ulong[words];
  for(int i=0;i<n;i++){ulong z=forbidden&~fs[i];while(z!=0){int b=BitOperations.TrailingZeroCount(z);posts[b][i>>6]|=1UL<<(i&63);z&=z-1;}}
  var found=new Dictionary<ulong,Hit>(new U64Hash());long count=0;
  for(int i=0;i<n;i++){
   if((fs[i]&target)==0)continue;
   ulong z=fs[i]&forbidden;var bits=new int[BitOperations.PopCount(z)];int at=0;
   while(z!=0){bits[at++]=BitOperations.TrailingZeroCount(z);z&=z-1;}
   for(int w=i>>6;w<words;w++){
    ulong choices=ulong.MaxValue;
    foreach(int b in bits){choices&=posts[b][w];if(choices==0)break;}
    if(w==(i>>6))choices&=ulong.MaxValue<<(i&63);
    while(choices!=0){int j=(w<<6)+BitOperations.TrailingZeroCount(choices);choices&=choices-1;if(j>=n)continue;count++;
     ulong cover=fs[i]&fs[j];if(cover==0)continue;int t=Math.Max(ts[i],ts[j])+27886;
     ref Hit h=ref CollectionsMarshal.GetValueRefOrAddDefault(found,cover,out bool exists);
     if(!exists||t<h.T)h=new Hit(t,i,j);
    }
   }
   if(i%10000==0)Console.WriteLine($"native i={i}/{n} covers={found.Count} seconds={watch.Elapsed.TotalSeconds:F2}");
  }
  using(var w=new BinaryWriter(File.Create(output))){w.Write(found.Count);foreach(var row in found){w.Write(row.Key);w.Write(row.Value.T);w.Write(row.Value.I);w.Write(row.Value.J);}}
  Console.WriteLine($"native complete covers={found.Count} tuples={count} seconds={watch.Elapsed.TotalSeconds:F2}");
 }

}
